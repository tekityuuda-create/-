import streamlit as st
from ortools.sat.python import cp_model
import pandas as pd
import calendar

st.set_page_config(page_title="世界最高峰 勤務作成AI V27", layout="wide")
st.title("🛡️ 究極の勤務作成エンジン (Ultra-Robust Optimizer)")

# --- サイドバー：基本設定 ---
with st.sidebar:
    st.header("📅 基本設定")
    year = st.number_input("年", value=2025)
    month = st.number_input("月", min_value=1, max_value=12, value=1)
    
    st.header("👤 公休数設定")
    staff_names = [f"スタッフ{i+1}" for i in range(10)]
    target_hols = []
    for i in range(10):
        label = f"スタッフ{i+1} ({'管理者' if i < 2 else '一般'})"
        target_hols.append(st.number_input(label, value=9, key=f"hol_{i}"))

# --- メイン画面：勤務指定 ---
_, num_days = calendar.monthrange(year, month)
days_cols = [f"{d+1}({['月','火','水','木','金','土','日'][calendar.weekday(year,month,d+1)]})" for d in range(num_days)]

st.subheader("📝 勤務指定・申し込み")
request_df = pd.DataFrame("", index=staff_names, columns=days_cols)
edited_request = st.data_editor(request_df, use_container_width=True, key="request_editor")

st.subheader("🚫 不要担務の設定")
roles = ["A", "B", "C", "D", "E"]
exclude_df = pd.DataFrame(False, index=[d+1 for d in range(num_days)], columns=roles)
edited_exclude = st.data_editor(exclude_df, use_container_width=True, key="exclude_editor")

if st.button("🚀 勤務表を生成する"):
    model = cp_model.CpModel()
    # 0:休, 1:A, 2:B, 3:C, 4:D, 5:E, 6:出
    shifts = {}
    for s in range(10):
        for d in range(num_days):
            for i in range(7):
                shifts[(s, d, i)] = model.NewBoolVar(f's{s}d{d}i{i}')

    obj_terms = [] # 加点・減点リスト

    # --- 基本制約 ---
    for d in range(num_days):
        wd = calendar.weekday(year, month, d + 1)
        
        # 1. 1人1日1シフト（絶対）
        for s in range(10):
            model.Add(sum(shifts[(s, d, i)] for i in range(7)) == 1)

        # 2. 役割充足 (A-E)
        for i in range(1, 6):
            is_excluded = edited_exclude.iloc[d, i-1]
            is_sun_c = (wd == 6 and i == 3)
            
            total_on_duty = sum(shifts[(s, d, i)] for s in range(10))
            regular_on_duty = sum(shifts[(s, d, i)] for s in range(2, 10))

            if is_excluded or is_sun_c:
                model.Add(total_on_duty == 0)
            else:
                # ABCDEを必ず誰か1人がやる（超高優先：10億点）
                is_filled = model.NewBoolVar(f'filled_d{d}_i{i}')
                model.Add(total_on_duty == 1).OnlyEnforceIf(is_filled)
                obj_terms.append(is_filled * 1000000000)

                # 一般職で埋める（優先：100万点）
                reg_filled = model.NewBoolVar(f'reg_filled_d{d}_i{i}')
                model.Add(regular_on_duty == 1).OnlyEnforceIf(reg_filled)
                obj_terms.append(reg_filled * 1000000)

    # --- 勤務ルール ---
    for s in range(10):
        for d in range(num_days):
            # A. 申し込みの反映（絶対）
            req = edited_request.iloc[s, d]
            char_to_id = {"休":0, "A":1, "B":2, "C":3, "D":4, "E":5, "出":6}
            if req in char_to_id:
                model.Add(shifts[(s, d, char_to_id[req])] == 1)

            # B. 遅→早禁止（超高優先：1億点）
            if d < num_days - 1:
                for late in [4, 5]:
                    for early in [1, 2, 3]:
                        not_late_early = model.NewBoolVar(f'not_le_s{s}_d{d}_{late}')
                        model.Add(shifts[(s, d, late)] + shifts[(s, d+1, early)] <= 1).OnlyEnforceIf(not_late_early)
                        obj_terms.append(not_late_early * 100000000)

            # C. 5連勤以上の禁止（高優先：5000万点）
            if d < num_days - 4:
                no_5consecutive = model.NewBoolVar(f'no5c_s{s}_d{d}')
                model.Add(sum((1 - shifts[(s, d+k, 0)]) for k in range(5)) <= 4).OnlyEnforceIf(no_5consecutive)
                obj_terms.append(no_5consecutive * 50000000)

        # D. 管理者ルール
        if s < 2:
            for d in range(num_days):
                wd = calendar.weekday(year, month, d + 1)
                if wd >= 5: # 土日休み（優先：500万点）
                    mgr_off = model.NewBoolVar(f'mgr_off_s{s}_d{d}')
                    model.Add(shifts[(s, d, 0)] == 1).OnlyEnforceIf(mgr_off)
                    obj_terms.append(mgr_off * 5000000)
                else: # 平日は原則出勤（優先：500万点）
                    mgr_work = model.NewBoolVar(f'mgr_work_s{s}_d{d}')
                    model.Add(shifts[(s, d, 0)] == 0).OnlyEnforceIf(mgr_work)
                    obj_terms.append(mgr_work * 5000000)
        else:
            # 一般職は「出(6)」にならない
            for d in range(num_days):
                if edited_request.iloc[s, d] != "出":
                    model.Add(shifts[(s, d, 6)] == 0)

    # E. 公休数死守（最優先レベル：2億点）
    for s in range(10):
        actual_hols = sum(shifts[(s, d, 0)] for d in range(num_days))
        h_diff = model.NewIntVar(0, num_days, f'h_diff_s{s}')
        model.AddAbsEquality(h_diff, actual_hols - int(target_hols[s]))
        obj_terms.append(h_diff * -200000000)

    # F. シフトの混合（早遅が適度に混ざるように小加点）
    for s in range(10):
        for d in range(num_days - 1):
            mixed = model.NewBoolVar(f'mixed_s{s}_d{d}')
            # 今日のシフトと明日のシフトが違えば加点
            model.Add(sum(shifts[(s, d, i)] for i in range(1, 7)) != sum(shifts[(s, d+1, i)] for i in range(1, 7))).OnlyEnforceIf(mixed)
            obj_terms.append(mixed * 1000)

    # --- 解決 ---
    model.Maximize(sum(obj_terms))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30.0 # 少し長めに計算
    status = solver.Solve(model)

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        st.success("✨ 勤務表を生成しました！")
        res_data = []
        char_map = {0:"休", 1:"A", 2:"B", 3:"C", 4:"D", 5:"E", 6:"出"}
        for s in range(10):
            row = [char_map[next(i for i in range(7) if solver.Value(shifts[(s, d, i)]) == 1)] for d in range(num_days)]
            res_data.append(row)
        
        result_df = pd.DataFrame(res_data, index=staff_names, columns=days_cols)
        result_df["公休"] = [row.count("休") for row in res_data]
        st.dataframe(result_df.style.applymap(lambda x: 'background-color: #ffcccc' if x=='休' else ('background-color: #e0f0ff' if x=='出' else 'background-color: #ccffcc')), use_container_width=True)
    else:
        st.error("⚠️ 致命的なエラー：計算できませんでした。")
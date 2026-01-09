import streamlit as st
import pandas as pd
import calendar
from ortools.sat.python import cp_model

# 画面設定
st.set_page_config(page_title="世界最高峰 勤務作成AI V34", layout="wide")
st.title("🛡️ 究極の勤務作成エンジン (Flexible Logic Edition)")

# --- サイドバー：基本設定 ---
with st.sidebar:
    st.header("📅 基本設定")
    year = st.number_input("年", value=2025, step=1)
    month = st.number_input("月", min_value=1, max_value=12, value=1, step=1)
    
    st.header("👤 公休数設定")
    staff_names = [f"スタッフ{i+1}" for i in range(10)]
    target_hols = []
    for i in range(10):
        label = f"スタッフ{i+1} ({'管理者' if i < 2 else '一般'})"
        target_hols.append(st.number_input(label, value=9, key=f"hol_{i}"))

# --- カレンダー計算 ---
_, num_days = calendar.monthrange(int(year), int(month))
weekdays_ja = ["月", "火", "水", "木", "金", "土", "日"]
days_cols = [f"{d+1}({weekdays_ja[calendar.weekday(int(year), int(month), d+1)]})" for d in range(num_days)]

# --- メイン画面：勤務指定 ---
st.subheader("📝 勤務指定・申し込み")
st.write("各セルをダブルクリックして「休・出・A-E」を選択してください。")

options = ["", "休", "出", "A", "B", "C", "D", "E"]
request_df = pd.DataFrame("", index=staff_names, columns=days_cols)
# カテゴリー型にしてプルダウン化（古いStreamlit対策）
for col in days_cols:
    request_df[col] = pd.Categorical(request_df[col], categories=options)

edited_request = st.data_editor(request_df, use_container_width=True, key="request_editor")

# --- 不要担務の設定 ---
st.subheader("🚫 不要担務の設定")
roles_list = ["A", "B", "C", "D", "E"]
exclude_df = pd.DataFrame(False, index=[d+1 for d in range(num_days)], columns=roles_list)
edited_exclude = st.data_editor(exclude_df, use_container_width=True, key="exclude_editor")

# --- 計算ロジック ---
if st.button("🚀 勤務表を生成する（究極の柔軟性・モード）"):
    model = cp_model.CpModel()
    # 0:休, 1:A, 2:B, 3:C, 4:D, 5:E, 6:出
    shifts = {}
    for s in range(10):
        for d in range(num_days):
            for i in range(7):
                shifts[(s, d, i)] = model.NewBoolVar(f's{s}d{d}i{i}')

    obj_terms = []

    # --- 日ごとの制約 ---
    for d in range(num_days):
        wd = calendar.weekday(int(year), int(month), d + 1)
        
        # 1. 役割充足（ABCDEを埋める）
        for i in range(1, 6):
            is_excluded = edited_exclude.iloc[d, i-1]
            is_sun_c = (wd == 6 and i == 3)
            total_on_duty = sum(shifts[(s, d, i)] for s in range(10))
            
            if is_excluded or is_sun_c:
                model.Add(total_on_duty == 0)
            else:
                # 担務を埋める（最優先：1億点）
                # 管理者が入ってでも埋めるように重み付け
                is_filled = model.NewBoolVar(f'f_d{d}_i{i}')
                model.Add(total_on_duty == 1).OnlyEnforceIf(is_filled)
                obj_terms.append(is_filled * 100000000)

        for s in range(10):
            # 1人1日1シフト
            model.Add(sum(shifts[(s, d, i)] for i in range(7)) == 1)
            
            # 遅→早禁止（絶対）
            if d < num_days - 1:
                for late in [4, 5]:
                    for early in [1, 2, 3]:
                        model.Add(shifts[(s, d, late)] + shifts[(s, d+1, early)] <= 1)

            # 勤務指定の反映
            req = edited_request.iloc[s, d]
            char_to_id = {"休":0, "A":1, "B":2, "C":3, "D":4, "E":5, "出":6}
            if req in char_to_id:
                model.Add(shifts[(s, d, char_to_id[req])] == 1)

    # --- 個人別・高度な制約 ---
    for s in range(10):
        # 4連勤まで（5連勤以上を絶対禁止）
        for d in range(num_days - 4):
            model.Add(sum((1 - shifts[(s, d+k, 0)]) for k in range(5)) <= 4)

        # 管理者(1-2)の努力目標
        if s < 2:
            for d in range(num_days):
                wd = calendar.weekday(int(year), int(month), d+1)
                # 土日祝休み（努力目標：100万点）
                if wd >= 5: 
                    is_mgr_off = model.NewBoolVar(f'mgr_off_{s}_{d}')
                    model.Add(shifts[(s, d, 0)] == 1).OnlyEnforceIf(is_mgr_off)
                    obj_terms.append(is_mgr_off * 1000000)
                else:
                    # 平日出勤（努力目標：100万点）
                    is_mgr_work = model.NewBoolVar(f'mgr_work_{s}_{d}')
                    model.Add(shifts[(s, d, 0)] == 0).OnlyEnforceIf(is_mgr_work)
                    obj_terms.append(is_mgr_work * 1000000)
        else:
            # 一般職：指定なき「出(6)」禁止
            for d in range(num_days):
                if edited_request.iloc[s, d] != "出":
                    model.Add(shifts[(s, d, 6)] == 0)

        # 【混合ボーナス】早遅のリズム
        for d in range(num_days - 1):
            is_e_today = model.NewBoolVar(f'ie_{s}_{d}')
            model.Add(sum(shifts[(s, d, i)] for i in [1, 2, 3]) == 1).OnlyEnforceIf(is_e_today)
            is_l_tomorrow = model.NewBoolVar(f'ilt_{s}_{d}')
            model.Add(sum(shifts[(s, d+1, i)] for i in [4, 5]) == 1).OnlyEnforceIf(is_l_tomorrow)

            mix_el = model.NewBoolVar(f'mix_{s}_{d}')
            model.AddBoolAnd([is_e_today, is_l_tomorrow]).OnlyEnforceIf(mix_el)
            obj_terms.append(mix_el * 10000)

        # 【重要】公休数（B列）の柔軟な判定
        actual_hols = sum(shifts[(s, d, 0)] for d in range(num_days))
        # 1日程度のズレを許容するための制約
        model.Add(actual_hols >= int(target_hols[s]) - 1)
        model.Add(actual_hols <= int(target_hols[s]) + 1)
        
        # ぴったりだと高得点（1,000万点）
        is_exact_hols = model.NewBoolVar(f'exact_hols_{s}')
        model.Add(actual_hols == int(target_hols[s])).OnlyEnforceIf(is_exact_hols)
        obj_terms.append(is_exact_hols * 10000000)

    model.Maximize(sum(obj_terms))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 20.0 # 20秒制限
    status = solver.Solve(model)

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        st.success("✨ 1日程度の公休ズレを許容し、最適な勤務表を作成しました。")
        res_data = []
        char_map = {0:"休", 1:"A", 2:"B", 3:"C", 4:"D", 5:"E", 6:"出"}
        for s in range(10):
            row = [char_map[next(i for i in range(7) if solver.Value(shifts[(s, d, i)]) == 1)] for d in range(num_days)]
            res_data.append(row)
        
        final_df = pd.DataFrame(res_data, index=staff_names, columns=days_cols)
        final_df["公休計"] = [row.count("休") for row in res_data]
        st.dataframe(final_df.style.applymap(lambda x: 'background-color: #ffcccc' if x=='休' else ('background-color: #e0f0ff' if x=='出' else 'background-color: #ccffcc')), use_container_width=True)
        st.download_button("📥 結果をCSVで保存", final_df.to_csv().encode('utf-8-sig'), f"roster_{year}_{month}.csv")
    else:
        st.error("⚠️ 条件を緩和しても計算できませんでした。公休数を全員8日〜9日程度に調整してください。")

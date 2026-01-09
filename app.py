import streamlit as st
import pandas as pd
import calendar
from ortools.sat.python import cp_model

# 画面設定
st.set_page_config(page_title="世界最高峰 勤務作成AI V31", layout="wide")
st.title("🛡️ 究極の勤務作成エンジン (Pro-Mix Optimizer)")

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

# --- メイン画面：勤務指定（プルダウン形式） ---
st.subheader("📝 勤務指定・申し込み")
st.write("各セルをダブルクリックして「休・出・A-E」を選択してください。")

options = ["", "休", "出", "A", "B", "C", "D", "E"]
request_df = pd.DataFrame("", index=staff_names, columns=days_cols)
for col in days_cols:
    request_df[col] = pd.Categorical(request_df[col], categories=options)

edited_request = st.data_editor(request_df, use_container_width=True, key="request_editor")

# --- 不要担務の設定 ---
st.subheader("🚫 不要担務の設定")
roles_list = ["A", "B", "C", "D", "E"]
exclude_df = pd.DataFrame(False, index=[d+1 for d in range(num_days)], columns=roles_list)
edited_exclude = st.data_editor(exclude_df, use_container_width=True, key="exclude_editor")

# --- 計算ロジック ---
if st.button("🚀 勤務表を生成する（混合バランス重視モード）"):
    model = cp_model.CpModel()
    # 0:休, 1:A, 2:B, 3:C, 4:D, 5:E, 6:出
    shifts = {}
    for s in range(10):
        for d in range(num_days):
            for i in range(7):
                shifts[(s, d, i)] = model.NewBoolVar(f's{s}d{d}i{i}')

    obj_terms = []

    for d in range(num_days):
        wd = calendar.weekday(int(year), int(month), d + 1)
        
        # 1. 担務充足（ABCDEを必ず誰かがやる）
        for i in range(1, 6):
            is_excluded = edited_exclude.iloc[d, i-1]
            is_sun_c = (wd == 6 and i == 3)
            total_on_duty = sum(shifts[(s, d, i)] for s in range(10))
            
            if is_excluded or is_sun_c:
                model.Add(total_on_duty == 0)
            else:
                is_filled = model.NewBoolVar(f'filled_d{d}_i{i}')
                model.Add(total_on_duty == 1).OnlyEnforceIf(is_filled)
                obj_terms.append(is_filled * 10000000)

        for s in range(10):
            # 1日1シフト
            model.Add(sum(shifts[(s, d, i)] for i in range(7)) == 1)
            
            # 遅→早禁止
            if d < num_days - 1:
                for late in [4, 5]: # D, E
                    for early in [1, 2, 3]: # A, B, C
                        model.Add(shifts[(s, d, late)] + shifts[(s, d+1, early)] <= 1)

            # 勤務指定の反映
            req = edited_request.iloc[s, d]
            char_to_id = {"休":0, "A":1, "B":2, "C":3, "D":4, "E":5, "出":6}
            if req in char_to_id:
                model.Add(shifts[(s, d, char_to_id[req])] == 1)

    # 個人別・管理者別の高度な制約
    for s in range(10):
        # 4連勤まで
        for d in range(num_days - 4):
            model.Add(sum((1 - shifts[(s, d+k, 0)]) for k in range(5)) <= 4)

        # 【新導入】シフト混合ロジック
        # 早番(A,B,C)と遅番(D,E)が入れ替わったら加点
        for d in range(num_days - 1):
            is_early_today = model.NewBoolVar(f'is_e_{s}_{d}')
            model.Add(sum(shifts[(s, d, i)] for i in [1, 2, 3]) == 1).OnlyEnforceIf(is_early_today)
            
            is_late_today = model.NewBoolVar(f'is_l_{s}_{d}')
            model.Add(sum(shifts[(s, d, i)] for i in [4, 5]) == 1).OnlyEnforceIf(is_late_today)

            is_early_tomorrow = model.NewBoolVar(f'is_e_{s}_{d+1}')
            model.Add(sum(shifts[(s, d+1, i)] for i in [1, 2, 3]) == 1).OnlyEnforceIf(is_early_tomorrow)

            is_late_tomorrow = model.NewBoolVar(f'is_l_{s}_{d+1}')
            model.Add(sum(shifts[(s, d+1, i)] for i in [4, 5]) == 1).OnlyEnforceIf(is_late_tomorrow)

            # 「今日早番 且つ 明日遅番」ならボーナス
            mix_el = model.NewBoolVar(f'mix_el_{s}_{d}')
            model.AddAll([is_early_today, is_late_tomorrow]).OnlyEnforceIf(mix_el)
            obj_terms.append(mix_el * 5000)

            # 「今日遅番 且つ 明日休み（直後に早番にするための準備）」なら加点
            off_tomorrow = model.NewBoolVar(f'off_tomorrow_{s}_{d}')
            model.Add(shifts[(s, d+1, 0)] == 1).OnlyEnforceIf(off_tomorrow)
            mix_lo = model.NewBoolVar(f'mix_lo_{s}_{d}')
            model.AddAll([is_late_today, off_tomorrow]).OnlyEnforceIf(mix_lo)
            obj_terms.append(mix_lo * 2000)

        # 管理者(1-2)とスタッフ(3-10)
        if s < 2:
            for d in range(num_days):
                if calendar.weekday(int(year), int(month), d+1) >= 5:
                    model.Add(shifts[(s, d, 0)] == 1) # 土日祝休み
                else:
                    model.Add(shifts[(s, d, 0)] == 0) # 平日出勤
        else:
            for d in range(num_days):
                if edited_request.iloc[s, d] != "出":
                    model.Add(shifts[(s, d, 6)] == 0)

        # 公休数死守
        actual_hols = sum(shifts[(s, d, 0)] for d in range(num_days))
        h_diff = model.NewIntVar(0, num_days, f'hd_{s}')
        model.AddAbsEquality(h_diff, actual_hols - int(target_hols[s]))
        obj_terms.append(h_diff * -1000000)

    model.Maximize(sum(obj_terms))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30.0
    status = solver.Solve(model)

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        st.success("✨ シフトの混合バランスを最適化しました！")
        res_data = []
        char_map = {0:"休", 1:"A", 2:"B", 3:"C", 4:"D", 5:"E", 6:"出"}
        for s in range(10):
            row = [char_map[next(i for i in range(7) if solver.Value(shifts[(s, d, i)]) == 1)] for d in range(num_days)]
            res_data.append(row)
        
        final_df = pd.DataFrame(res_data, index=staff_names, columns=days_cols)
        final_df["公休計"] = [row.count("休") for row in res_data]
        st.dataframe(final_df.style.applymap(lambda x: 'background-color: #ffcccc' if x=='休' else ('background-color: #e0f0ff' if x=='出' else 'background-color: #ccffcc')), use_container_width=True)
    else:
        st.error("⚠️ 条件が厳しすぎて作成できませんでした。公休数を減らすか、指定を減らしてみてください。")

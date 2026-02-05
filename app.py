import streamlit as st
import pandas as pd
import calendar
from ortools.sat.python import cp_model

# --- 画面設定 ---
st.set_page_config(page_title="世界最高峰 勤務作成AI 究極版", page_icon="📅", layout="wide")
st.title("🛡️ 究極の勤務作成エンジン (Boundary-Aware Optimizer V44)")

# --- サイドバー：詳細設定 ---
with st.sidebar:
    st.header("⚙️ システム構成")
    num_mgr = st.number_input("管理者の人数", min_value=0, max_value=5, value=2)
    num_regular = st.number_input("一般スタッフの人数", min_value=1, max_value=15, value=8)
    total_staff = num_mgr + num_regular
    
    st.header("📋 勤務区分設定")
    shift_input = st.text_input("勤務略称 (カンマ区切り)", "A,B,C,D,E")
    user_shifts = [s.strip() for s in shift_input.split(",") if s.strip()]
    num_user_shifts = len(user_shifts)
    
    st.subheader("🕑 カテゴリー設定")
    early_shifts = st.multiselect("早番グループ", user_shifts, default=[s for s in user_shifts if s in ["A","B","C"]])
    late_shifts = st.multiselect("遅番グループ", user_shifts, default=[s for s in user_shifts if s in ["D","E"]])
    
    st.header("📅 対象年月")
    year = st.number_input("年", value=2025, step=1)
    month = st.number_input("月", min_value=1, max_value=12, value=1, step=1)
    
    st.header("👤 公休数設定")
    staff_names = [f"スタッフ{i+1}({'管理者' if i < num_mgr else '一般'})" for i in range(total_staff)]
    target_hols = [st.number_input(f"{name} の公休", value=9, key=f"hol_{i}") for i, name in enumerate(staff_names)]

# --- カレンダー計算 ---
_, num_days = calendar.monthrange(int(year), int(month))
weekdays_ja = ["月", "火", "水", "木", "金", "土", "日"]
days_cols = [f"{d+1}({weekdays_ja[calendar.weekday(int(year), int(month), d+1)]})" for d in range(num_days)]
options = ["", "休", "日"] + user_shifts

# --- メイン画面：前月末の状況入力 ---
st.subheader("⏮️ 前月末の勤務状況 (過去4日間)")
st.write("今月の1日目における連勤制限(4日まで)と遅早禁止を判定するために使用します。")
prev_days = ["前月27日", "前月28日", "前月29日", "前月末日"]
prev_df = pd.DataFrame("休", index=staff_names, columns=prev_days)
for col in prev_days:
    prev_df[col] = pd.Categorical(prev_df[col], categories=options)
edited_prev = st.data_editor(prev_df, use_container_width=True, key="prev_editor")

# --- メイン画面：今月の勤務指定 ---
st.subheader("📝 今月の勤務指定・申し込み")
request_df = pd.DataFrame("", index=staff_names, columns=days_cols)
for col in days_cols:
    request_df[col] = pd.Categorical(request_df[col], categories=options)
edited_request = st.data_editor(request_df, use_container_width=True, key="request_editor")

# --- 不要担務の設定 ---
st.subheader("🚫 不要担務の設定")
exclude_df = pd.DataFrame(False, index=[d+1 for d in range(num_days)], columns=user_shifts)
edited_exclude = st.data_editor(exclude_df, use_container_width=True, key="exclude_editor")

# --- 計算ロジック ---
if st.button("🚀 境界条件を考慮して勤務表を生成"):
    model = cp_model.CpModel()
    S_OFF, S_NIKKIN = 0, num_user_shifts + 1
    
    # 文字からIDへの変換辞書
    char_to_id = {"休": S_OFF, "日": S_NIKKIN, "": -1}
    for idx, name in enumerate(user_shifts):
        char_to_id[name] = idx + 1
    
    # 属性IDの準備
    early_ids = [user_shifts.index(s) + 1 for s in early_shifts]
    late_ids = [user_shifts.index(s) + 1 for s in late_shifts]

    # 変数作成
    shifts = {(s, d, i): model.NewBoolVar(f's{s}d{d}i{i}') for s in range(total_staff) for d in range(num_days) for i in range(num_user_shifts + 2)}
    obj_terms = []

    # 前月末データの数値化
    prev_work_matrix = [] # 1:出勤, 0:休み
    prev_last_shift = [] # 最終日のシフトID
    for s in range(total_staff):
        row_work = []
        for d_idx in range(4):
            val = edited_prev.iloc[s, d_idx]
            row_work.append(1 if val != "休" else 0)
            if d_idx == 3: # 最終日
                prev_last_shift.append(char_to_id.get(val, S_OFF))
        prev_work_matrix.append(row_work)

    # --- 各日の制約 ---
    for d in range(num_days):
        wd = calendar.weekday(int(year), int(month), d + 1)
        
        # 1. 役割の充足 (A-E)
        for idx, s_name in enumerate(user_shifts):
            s_id = idx + 1
            is_excluded = edited_exclude.iloc[d, idx]
            is_sun_c = (wd == 6 and s_name == "C")
            total_on_duty = sum(shifts[(s, d, s_id)] for s in range(total_staff))
            
            if is_excluded or is_sun_c:
                model.Add(total_on_duty == 0)
            else:
                filled = model.NewBoolVar(f'f_d{d}_s{s_id}')
                model.Add(total_on_duty == 1).OnlyEnforceIf(filled)
                obj_terms.append(filled * 100000000)

        for s in range(total_staff):
            model.Add(sum(shifts[(s, d, i)] for i in range(num_user_shifts + 2)) == 1)
            
            # 2. 遅→早禁止
            # 今月内の判定
            if d < num_days - 1:
                for l_id in late_ids:
                    for e_id in early_ids:
                        nle = model.NewBoolVar(f'nle_{s}_{d}_{l_id}_{e_id}')
                        model.Add(shifts[(s, d, l_id)] + shifts[(s, d+1, e_id)] <= 1).OnlyEnforceIf(nle)
                        obj_terms.append(nle * 10000000)
            # 月をまたぐ判定 (今月1日目)
            if d == 0:
                if prev_last_shift[s] in late_ids:
                    for e_id in early_ids:
                        model.Add(shifts[(s, 0, e_id)] == 0)

            # 3. 勤務指定の反映
            req = edited_request.iloc[s, d]
            if req in char_to_id and req != "":
                model.Add(shifts[(s, d, char_to_id[req])] == 1)

    # --- 4連勤制限 (5連勤禁止) ---
    for s in range(total_staff):
        # 過去4日分を考慮したリストを作成 [前月27, 28, 29, 30, 1, 2, ...]
        # 1-shifts[(s, d, S_OFF)] は出勤なら1、休みなら0
        is_working_this_month = [ (1 - shifts[(s, d, S_OFF)]) for d in range(num_days) ]
        full_work_history = prev_work_matrix[s] + is_working_this_month
        
        # すべての5日間連続区間において、合計が4以下であること
        for start_d in range(len(full_work_history) - 4):
            n5c = model.NewBoolVar(f'n5c_s{s}_hist{start_d}')
            model.Add(sum(full_work_history[start_d:start_d+5]) <= 4).OnlyEnforceIf(n5c)
            obj_terms.append(n5c * 5000000)

        # 管理者 / 一般職の固有ルール
        if s < num_mgr:
            for d in range(num_days):
                wd = calendar.weekday(int(year), int(month), d+1)
                m_goal = model.NewBoolVar(f'mg_{s}_{d}')
                if wd >= 5: # 土日祝
                    model.Add(shifts[(s, d, S_OFF)] == 1).OnlyEnforceIf(m_goal)
                    obj_terms.append(m_goal * 1000000)
                else: # 平日
                    model.Add(shifts[(s, d, S_OFF)] == 0).OnlyEnforceIf(m_goal)
                    obj_terms.append(m_goal * 1000000)
        else:
            for d in range(num_days):
                if edited_request.iloc[s, d] != "日":
                    model.Add(shifts[(s, d, S_NIKKIN)] == 0)

        # 公休数
        actual_hols = sum(shifts[(s, d, S_OFF)] for d in range(num_days))
        model.Add(actual_hols >= int(target_hols[s]) - 1)
        model.Add(actual_hols <= int(target_hols[s]) + 1)
        is_exact = model.NewBoolVar(f'exact_{s}')
        model.Add(actual_hols == int(target_hols[s])).OnlyEnforceIf(is_exact)
        obj_terms.append(is_exact * 10000000)

    model.Maximize(sum(obj_terms))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 20.0
    status = solver.Solve(model)

    if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        st.success("✨ 前月末からの流れを考慮して勤務表を生成しました！")
        res_data = []
        char_map = {S_OFF: "休", S_NIKKIN: "日"}
        for idx, name in enumerate(user_shifts): char_map[idx + 1] = name
        for s in range(total_staff):
            row = [char_map[next(i for i in range(num_user_shifts + 2) if solver.Value(shifts[(s, d, i)]) == 1)] for d in range(num_days)]
            res_data.append(row)
        
        final_df = pd.DataFrame(res_data, index=staff_names, columns=days_cols)
        final_df["公休計"] = [row.count("休") for row in res_data]
        st.dataframe(final_df.style.applymap(lambda x: 'background-color: #ffcccc' if x=="休" else ('background-color: #e0f0ff' if x=="日" else 'background-color: #ccffcc')), use_container_width=True)
        st.download_button("📥 CSV保存", final_df.to_csv().encode('utf-8-sig'), f"roster_{year}_{month}.csv")
    else: st.error("⚠️ 解が見つかりませんでした。前月末のデータか公休数を見直してください。")

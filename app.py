import streamlit as st
import pandas as pd
import calendar
from ortools.sat.python import cp_model

# --- 画面設定 ---
st.set_page_config(page_title="世界最高峰 勤務作成AI 習熟度対応版", page_icon="📅", layout="wide")
st.title("🛡️ 究極の勤務作成エンジン (Ultra-Stable Skill Optimizer V47)")

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
    staff_names = [f"スタッフ{i+1}" for i in range(total_staff)]
    target_hols = [st.number_input(f"{name} の公休", value=9, key=f"hol_{i}") for i, name in enumerate(staff_names)]

# --- 1. スキルマトリクス設定（プルダウン回避版） ---
st.subheader("🎓 スキル・見習い設定")
st.write("○:単独可（戦力）, △:見習い（ベテランとペア必須）, ×:不可")
skill_options = ["○", "△", "×"]
skill_df = pd.DataFrame("○", index=staff_names, columns=user_shifts)

# 【重要】configを使わずカテゴリー型でプルダウン化
for col in user_shifts:
    skill_df[col] = pd.Categorical(skill_df[col], categories=skill_options)
edited_skill = st.data_editor(skill_df, use_container_width=True, key="skill_editor")

# --- カレンダー計算 ---
_, num_days = calendar.monthrange(int(year), int(month))
weekdays_ja = ["月", "火", "水", "木", "金", "土", "日"]
days_cols = [f"{d+1}({weekdays_ja[calendar.weekday(int(year), int(month), d+1)]})" for d in range(num_days)]
all_options = ["", "休", "日"] + user_shifts

# --- 2. 前月末の状況入力 ---
st.subheader("⏮️ 前月末の勤務状況")
prev_days = ["前月4日前", "前月3日前", "前月2日前", "前月末日"]
prev_df = pd.DataFrame("休", index=staff_names, columns=prev_days)
for col in prev_days:
    prev_df[col] = pd.Categorical(prev_df[col], categories=all_options)
edited_prev = st.data_editor(prev_df, use_container_width=True, key="prev_editor")

# --- 3. 今月の勤務指定 ---
st.subheader("📝 今月の勤務指定")
request_df = pd.DataFrame("", index=staff_names, columns=days_cols)
for col in days_cols:
    request_df[col] = pd.Categorical(request_df[col], categories=all_options)
edited_request = st.data_editor(request_df, use_container_width=True, key="request_editor")

# --- 4. 不要担務の設定 ---
st.subheader("🚫 不要担務の設定")
exclude_df = pd.DataFrame(False, index=[d+1 for d in range(num_days)], columns=user_shifts)
edited_exclude = st.data_editor(exclude_df, use_container_width=True, key="exclude_editor")

# --- 計算ロジック ---
if st.button("🚀 勤務作成開始"):
    model = cp_model.CpModel()
    S_OFF, S_NIKKIN = 0, num_user_shifts + 1
    char_to_id = {"休": S_OFF, "日": S_NIKKIN, "": -1}
    for idx, name in enumerate(user_shifts): char_to_id[name] = idx + 1
    
    early_ids = [user_shifts.index(s) + 1 for s in early_shifts]
    late_ids = [user_shifts.index(s) + 1 for s in late_shifts]

    shifts = {(s, d, i): model.NewBoolVar(f's{s}d{d}i{i}') for s in range(total_staff) for d in range(num_days) for i in range(num_user_shifts + 2)}
    obj_terms = []

    # 前月末データ解析
    prev_work_matrix = [] 
    prev_last_shift = [] 
    for s in range(total_staff):
        row_work = []
        for d_idx in range(4):
            val = edited_prev.iloc[s, d_idx]
            row_work.append(1 if val != "休" else 0)
            if d_idx == 3: prev_last_shift.append(char_to_id.get(val, S_OFF))
        prev_work_matrix.append(row_work)

    # --- 各日の制約 ---
    for d in range(num_days):
        wd = calendar.weekday(int(year), int(month), d + 1)
        
        for idx, s_name in enumerate(user_shifts):
            s_id = idx + 1
            is_excluded = edited_exclude.iloc[d, idx]
            is_sun_c = (wd == 6 and s_name == "C")
            
            # スキルによる役割分担
            skilled_workers = [s for s in range(total_staff) if edited_skill.iloc[s, idx] == "○"]
            trainees = [s for s in range(total_staff) if edited_skill.iloc[s, idx] == "△"]
            
            total_on_duty = sum(shifts[(s, d, s_id)] for s in range(total_staff))

            if is_excluded or is_sun_c:
                model.Add(total_on_duty == 0)
            else:
                # 1. 単独可(○)の人は必ず1人配置
                model.Add(sum(shifts[(s, d, s_id)] for s in skilled_workers) == 1)
                # 2. 見習い(△)は最大1人まで（ベテランとペアになる）
                if trainees:
                    model.Add(sum(shifts[(s, d, s_id)] for s in trainees) <= 1)

        for s in range(total_staff):
            # 1人1シフト
            model.Add(sum(shifts[(s, d, i)] for i in range(num_user_shifts + 2)) == 1)
            
            # スキル「×」の仕事禁止
            for idx, s_name in enumerate(user_shifts):
                if edited_skill.iloc[s, idx] == "×":
                    model.Add(shifts[(s, d, idx+1)] == 0)

            # 遅→早禁止 (今月内)
            if d < num_days - 1:
                for l_id in late_ids:
                    for e_id in early_ids:
                        model.Add(shifts[(s, d, l_id)] + shifts[(s, d+1, e_id)] <= 1)
            # 遅→早禁止 (月またぎ)
            if d == 0 and prev_last_shift[s] in late_ids:
                for e_id in early_ids: model.Add(shifts[(s, 0, e_id)] == 0)

            # 勤務指定
            req = edited_request.iloc[s, d]
            if req in char_to_id and req != "": model.Add(shifts[(s, d, char_to_id[req])] == 1)

    # --- 共通ルール ---
    for s in range(total_staff):
        # 4連勤制限
        this_month_work = [ (1 - shifts[(s, d, S_OFF)]) for d in range(num_days) ]
        full_history = prev_work_matrix[s] + this_month_work
        for start_d in range(len(full_history) - 4):
            model.Add(sum(full_history[start_d:start_d+5]) <= 4)

        # 管理者ルール
        if s < num_mgr:
            for d in range(num_days):
                wd = calendar.weekday(int(year), int(month), d+1)
                m_goal = model.NewBoolVar(f'mg_{s}_{d}')
                if wd >= 5: 
                    model.Add(shifts[(s, d, S_OFF)] == 1).OnlyEnforceIf(m_goal)
                    obj_terms.append(m_goal * 1000000)
                else: 
                    model.Add(shifts[(s, d, S_OFF)] == 0)
        else:
            for d in range(num_days):
                if edited_request.iloc[s, d] != "日": model.Add(shifts[(s, d, S_NIKKIN)] == 0)

        # 公休数死守
        actual_hols = sum(shifts[(s, d, S_OFF)] for d in range(num_days))
        model.Add(actual_hols == int(target_hols[s]))

    model.Maximize(sum(obj_terms))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30.0
    status = solver.Solve(model)

    if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        st.success("✨ 習熟度と見習いペアを考慮した勤務表が完成しました！")
        res_data = []
        char_map = {S_OFF: "休", S_NIKKIN: "日"}
        for idx, name in enumerate(user_shifts): char_map[idx + 1] = name
        for s in range(total_staff):
            row = [char_map[next(i for i in range(num_user_shifts + 2) if solver.Value(shifts[(s, d, i)]) == 1)] for d in range(num_days)]
            res_data.append(row)
        
        final_df = pd.DataFrame(res_data, index=staff_names, columns=days_cols)
        final_df["公休計"] = [row.count("休") for row in res_data]
        
        def style_cells(val):
            if val == "休": return 'background-color: #ffcccc'
            if val == "日": return 'background-color: #e0f0ff'
            if val in user_shifts: return 'background-color: #ccffcc'
            return ''

        st.dataframe(final_df.style.applymap(style_cells), use_container_width=True)
        st.download_button("📥 CSV保存", final_df.to_csv().encode('utf-8-sig'), f"roster_{year}_{month}.csv")
    else: st.error("⚠️ 解が見つかりません。公休数やスキルの設定を調整してください。")

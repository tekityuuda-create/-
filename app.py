import streamlit as st
import pandas as pd
import calendar
from ortools.sat.python import cp_model

# --- 画面設定 ---
st.set_page_config(page_title="世界最高峰 勤務作成AI 究極版", page_icon="🛡️", layout="wide")
st.title("🛡️ 究極の勤務作成エンジン (Logic-Fixed V54)")

# --- サイドバー：詳細設定 ---
with st.sidebar:
    st.header("⚙️ システム構成")
    num_mgr = st.number_input("管理者の人数", min_value=0, max_value=5, value=2)
    num_regular = st.number_input("一般スタッフの人数", min_value=1, max_value=15, value=8)
    total_staff = int(num_mgr + num_regular)
    
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
    target_hols = []
    for i in range(total_staff):
        label = f"{staff_names[i]} ({'管理者' if i < num_mgr else '一般'})"
        val = st.number_input(f"{label} の公休", value=9, key=f"hol_{i}")
        target_hols.append(val)

# --- スキル・見習い設定 ---
st.subheader("🎓 スキル・見習い設定 (○:単独可, △:見習い, ×:不可)")
skill_options = ["○", "△", "×"]
skill_df = pd.DataFrame("○", index=staff_names, columns=user_shifts)
for col in user_shifts:
    skill_df[col] = pd.Categorical(skill_df[col], categories=skill_options)
edited_skill = st.data_editor(skill_df, use_container_width=True, key="skill_editor")

st.subheader("📊 見習い実施回数目標")
trainee_cols = [f"{s}_見習い回数" for s in user_shifts]
target_counts_df = pd.DataFrame(0, index=staff_names, columns=trainee_cols)
edited_trainee_targets = st.data_editor(target_counts_df, use_container_width=True, key="trainee_target_editor")

# --- カレンダー計算 ---
_, num_days = calendar.monthrange(int(year), int(month))
weekdays_ja = ["月", "火", "水", "木", "金", "土", "日"]
days_cols = [f"{d+1}({weekdays_ja[calendar.weekday(int(year), int(month), d+1)]})" for d in range(num_days)]
options = ["", "休", "日"] + user_shifts

# --- 前月末状況入力 ---
st.subheader("⏮️ 前月末の勤務状況 (4日間)")
prev_df = pd.DataFrame("休", index=staff_names, columns=["前月4日前", "前月3日前", "前月2日前", "前月末日"])
for col in prev_df.columns:
    prev_df[col] = pd.Categorical(prev_df[col], categories=options)
edited_prev = st.data_editor(prev_df, use_container_width=True, key="prev_editor")

# --- 今月の指定 ---
st.subheader("📝 今月の勤務指定")
request_df = pd.DataFrame("", index=staff_names, columns=days_cols)
for col in days_cols:
    request_df[col] = pd.Categorical(request_df[col], categories=options)
edited_request = st.data_editor(request_df, use_container_width=True, key="request_editor")

# --- 不要担務 ---
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
    prev_late_matrix = []
    prev_off_matrix = []
    for s in range(total_staff):
        row_w, row_l, row_o = [], [], []
        for d_idx in range(4):
            val = edited_prev.iloc[s, d_idx]
            sid = char_to_id.get(val, -1)
            row_w.append(1 if val != "休" else 0)
            row_l.append(1 if sid in late_ids else 0)
            row_o.append(1 if val == "休" else 0)
        prev_work_matrix.append(row_w)
        prev_late_matrix.append(row_l)
        prev_off_matrix.append(row_o)

    # 1. 役割充足
    for d in range(num_days):
        wd = calendar.weekday(int(year), int(month), d + 1)
        for idx, s_name in enumerate(user_shifts):
            s_id = idx + 1
            is_excluded = edited_exclude.iloc[d, idx]
            is_sun_c = (wd == 6 and s_name == "C")
            
            skilled_sum = sum(shifts[(s, d, s_id)] for s in range(total_staff) if edited_skill.iloc[s, idx] == "○")
            trainee_sum = sum(shifts[(s, d, s_id)] for s in range(total_staff) if edited_skill.iloc[s, idx] == "△")

            if is_excluded or is_sun_c:
                model.Add(skilled_sum + trainee_sum == 0)
            else:
                sk_ok = model.NewBoolVar(f'sk_ok_d{d}_i{idx}')
                model.Add(skilled_sum == 1).OnlyEnforceIf(sk_ok)
                obj_terms.append(sk_ok * 10000000)
                model.Add(trainee_sum <= 1)

    # 2. 個人制約
    for s in range(total_staff):
        # 中間変数：休み判定、早番判定、遅番判定を各日ごとに作る（エラー回避の鍵）
        is_off_this_month = [shifts[(s, d, S_OFF)] for d in range(num_days)]
        is_early_this_month = [model.NewBoolVar(f'ise_{s}_{d}') for d in range(num_days)]
        is_late_this_month = [model.NewBoolVar(f'isl_{s}_{d}') for d in range(num_days)]
        
        for d in range(num_days):
            # 1人1シフト
            model.Add(sum(shifts[(s, d, i)] for i in range(num_user_shifts + 2)) == 1)
            
            # 中間変数の定義（合計を個別の変数に変換）
            model.Add(sum(shifts[(s, d, i)] for i in early_ids) == 1).OnlyEnforceIf(is_early_this_month[d])
            model.Add(sum(shifts[(s, d, i)] for i in early_ids) == 0).OnlyEnforceIf(is_early_this_month[d].Not())
            model.Add(sum(shifts[(s, d, i)] for i in late_ids) == 1).OnlyEnforceIf(is_late_this_month[d])
            model.Add(sum(shifts[(s, d, i)] for i in late_ids) == 0).OnlyEnforceIf(is_late_this_month[d].Not())

            # スキル制限
            for idx, _ in enumerate(user_shifts):
                if edited_skill.iloc[s, idx] == "×": model.Add(shifts[(s, d, idx+1)] == 0)
            
            # 指定反映
            req = edited_request.iloc[s, d]
            if req in char_to_id and req != "": model.Add(shifts[(s, d, char_to_id[req])] == 1)

            # 今月内 遅→早禁止
            if d < num_days - 1:
                for l_id in late_ids:
                    for e_id in early_ids:
                        model.Add(shifts[(s, d, l_id)] + shifts[(s, d+1, e_id)] <= 1)
            
            # 月またぎ 遅→早禁止
            if d == 0 and prev_late_matrix[s][-1] == 1:
                for e_id in early_ids: model.Add(shifts[(s, 0, e_id)] == 0)

        # 4連勤制限
        this_month_work = [(1 - shifts[(s, d, S_OFF)]) for d in range(num_days)]
        history_w = prev_work_matrix[s] + this_month_work
        for start_d in range(len(history_w) - 4):
            model.Add(sum(history_w[start_d:start_d+5]) <= 4)

        # 【究極】連休抑制（中間変数を使ってエラー回避）
        all_off_history = [model.NewBoolVar(f'ao_{s}_{k}') for k in range(4 + num_days)]
        # 前月分
        for k in range(4):
            if prev_off_matrix[s][k] == 1: model.Add(all_off_history[k] == 1)
            else: model.Add(all_off_history[k] == 0)
        # 今月分
        for k in range(num_days):
            model.Add(all_off_history[k+4] == 1).OnlyEnforceIf(is_off_this_month[k])
            model.Add(all_off_history[k+4] == 0).OnlyEnforceIf(is_off_this_month[k].Not())

        for start_d in range(len(all_off_history) - 2):
            is_3off = model.NewBoolVar(f'i3o_{s}_{start_d}')
            model.AddBoolAnd([all_off_history[start_d], all_off_history[start_d+1], all_off_history[start_d+2]]).OnlyEnforceIf(is_3off)
            
            # 指定なし3連休を抑制
            current_month_range = []
            for i in range(3):
                idx = start_d + i - 4
                if 0 <= idx < num_days: current_month_range.append(idx)
            has_req = any(edited_request.iloc[s, idx] == "休" for idx in current_month_range) if current_month_range else False
            if not has_req: obj_terms.append(is_3off * -8000000)

        # 早遅ミックス（修正版：中間変数を使用）
        for d in range(num_days - 1):
            mix_b = model.NewBoolVar(f'mix_{s}_{d}')
            model.AddBoolAnd([is_early_this_month[d], is_late_this_month[d+1]]).OnlyEnforceIf(mix_b)
            obj_terms.append(mix_b * 5000000)

        # 管理者ルール / 公休
        if s < num_mgr:
            for d in range(num_days):
                wd = calendar.weekday(int(year), int(month), d+1)
                m_goal = model.NewBoolVar(f'mg_{s}_{d}')
                if wd >= 5: model.Add(shifts[(s, d, S_OFF)] == 1).OnlyEnforceIf(m_goal)
                else: model.Add(shifts[(s, d, S_OFF)] == 0).OnlyEnforceIf(m_goal)
                obj_terms.append(m_goal * 1000000)
        else:
            for d in range(num_days):
                if edited_request.iloc[s, d] != "日": model.Add(shifts[(s, d, S_NIKKIN)] == 0)

        # 見習い回数目標
        for idx, _ in enumerate(user_shifts):
            target_v = int(edited_trainee_targets.iloc[s, idx])
            if edited_skill.iloc[s, idx] == "△" and target_v > 0:
                model.Add(sum(shifts[(s, d, idx+1)] for d in range(num_days)) == target_v)

        # 公休数死守
        model.Add(sum(is_off_this_month) == int(target_hols[s]))

    model.Maximize(sum(obj_terms))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30.0
    status = solver.Solve(model)

    if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        st.success("✨ 成功しました！連休を分散し、理想的なシフトリズムを実現しました。")
        res_data = []
        char_map = {S_OFF: "休", S_NIKKIN: "日"}
        for idx, name in enumerate(user_shifts): char_map[idx + 1] = name
        for s in range(total_staff):
            row = [char_map[next(i for i in range(num_user_shifts + 2) if solver.Value(shifts[(s, d, i)]) == 1)] for d in range(num_days)]
            res_data.append(row)
        final_df = pd.DataFrame(res_data, index=staff_names, columns=days_cols)
        final_df["公休計"] = [row.count("休") for row in res_data]
        st.dataframe(final_df.style.applymap(lambda x: 'background-color: #ffcccc' if x=="休" else ('background-color: #e0f0ff' if x=="日" else ('background-color: #ffffcc' if x in early_shifts else 'background-color: #ccffcc'))), use_container_width=True)
        st.download_button("📥 CSV保存", final_df.to_csv().encode('utf-8-sig'), "roster.csv")
    else: st.error("⚠️ 解が見つかりません。公休数や見習い回数に無理がないか確認してください。")

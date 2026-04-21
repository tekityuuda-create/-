import streamlit as st
import pandas as pd
import calendar
import json
from ortools.sat.python import cp_model

# --- 画面基本設定 ---
st.set_page_config(page_title="世界最高峰 勤務作成AI 究極版", page_icon="🛡️", layout="wide")

# --- セッション状態の初期化 (データ消失防止) ---
if 'initialized' not in st.session_state:
    st.session_state.initialized = True
    st.session_state.num_mgr = 2
    st.session_state.num_regular = 8
    st.session_state.user_shifts = "A,B,C,D,E"
    st.session_state.early_shifts = ["A", "B", "C"]
    st.session_state.late_shifts = ["D", "E"]

st.title("🛡️ 究極の勤務作成エンジン (Pro-Management V55)")

# --- サイドバー：設定ファイルの保存と読込 ---
with st.sidebar:
    st.header("💾 設定の保存と復元")
    st.write("今の設定を保存しておけば、次回から一瞬で復元できます。")
    
    # ここに現在の全入力データを集約するロジックを後で実行
    
    st.header("📅 対象年月")
    year = st.number_input("年", value=2025, step=1)
    month = st.number_input("月", min_value=1, max_value=12, value=1, step=1)

# --- タブ分けによる直感的な操作 ---
tab1, tab2, tab3 = st.tabs(["⚙️ システム基本設定", "👤 スタッフ・スキル設定", "🚀 勤務表の作成"])

with tab1:
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("👥 人数構成")
        num_mgr = st.number_input("管理者の人数", min_value=0, max_value=5, value=st.session_state.num_mgr)
        num_regular = st.number_input("一般スタッフの人数", min_value=1, max_value=15, value=st.session_state.num_regular)
        total_staff = int(num_mgr + num_regular)
        staff_names = [f"スタッフ{i+1}({'管理者' if i < num_mgr else '一般'})" for i in range(total_staff)]
    
    with col2:
        st.subheader("📋 勤務グループ")
        shift_input = st.text_input("勤務略称 (カンマ区切り)", st.session_state.user_shifts)
        user_shifts_list = [s.strip() for s in shift_input.split(",") if s.strip()]
        
        early_defaults = [s for s in user_shifts_list if s in st.session_state.early_shifts]
        late_defaults = [s for s in user_shifts_list if s in st.session_state.late_shifts]
        
        early_shifts = st.multiselect("早番グループ", user_shifts_list, default=early_defaults)
        late_shifts = st.multiselect("遅番グループ", user_shifts_list, default=late_defaults)

with tab2:
    st.subheader("🎓 スキルと目標回数")
    st.write("○:単独可, △:見習い, ×:不可 / 回数:今月行う見習い回数")
    
    col_s1, col_s2 = st.columns([2, 1])
    with col_s1:
        skill_options = ["○", "△", "×"]
        skill_df = pd.DataFrame("○", index=staff_names, columns=user_shifts_list)
        for col in user_shifts_list:
            skill_df[col] = pd.Categorical(skill_df[col], categories=skill_options)
        edited_skill = st.data_editor(skill_df, use_container_width=True, key="skill_editor")
    
    with col_s2:
        target_hols_df = pd.DataFrame(9, index=staff_names, columns=["公休数"])
        edited_hols = st.data_editor(target_hols_df, use_container_width=True, key="hol_editor")
        
    st.subheader("📊 見習い実施回数の目標")
    trainee_cols = [f"{s}_見習い回数" for s in user_shifts_list]
    target_counts_df = pd.DataFrame(0, index=staff_names, columns=trainee_cols)
    edited_trainee_targets = st.data_editor(target_counts_df, use_container_width=True, key="trainee_target_editor")

with tab3:
    # カレンダー計算
    _, num_days = calendar.monthrange(int(year), int(month))
    weekdays_ja = ["月", "火", "水", "木", "金", "土", "日"]
    days_cols = [f"{d+1}({weekdays_ja[calendar.weekday(int(year), int(month), d+1)]})" for d in range(num_days)]
    options = ["", "休", "日"] + user_shifts_list

    st.subheader("⏮️ 前月末の勤務状況 (過去4日間)")
    prev_days = ["前月4日前", "前月3日前", "前月2日前", "前月末日"]
    prev_df = pd.DataFrame("休", index=staff_names, columns=prev_days)
    for col in prev_days:
        prev_df[col] = pd.Categorical(prev_df[col], categories=options)
    edited_prev = st.data_editor(prev_df, use_container_width=True, key="prev_editor")

    st.subheader("📝 今月の勤務指定 (申し込み)")
    request_df = pd.DataFrame("", index=staff_names, columns=days_cols)
    for col in days_cols:
        request_df[col] = pd.Categorical(request_df[col], categories=options)
    edited_request = st.data_editor(request_df, use_container_width=True, key="request_editor")

    st.subheader("🚫 不要担務の設定")
    exclude_df = pd.DataFrame(False, index=[d+1 for d in range(num_days)], columns=user_shifts_list)
    edited_exclude = st.data_editor(exclude_df, use_container_width=True, key="exclude_editor")

    if st.button("🚀 勤務作成を実行する", type="primary"):
        # --- ここから計算エンジン (V54のロジックを継承) ---
        model = cp_model.CpModel()
        num_user_shifts = len(user_shifts_list)
        S_OFF, S_NIKKIN = 0, num_user_shifts + 1
        char_to_id = {"休": S_OFF, "日": S_NIKKIN, "": -1}
        for idx, name in enumerate(user_shifts_list): char_to_id[name] = idx + 1
        
        early_ids = [user_shifts_list.index(s) + 1 for s in early_shifts]
        late_ids = [user_shifts_list.index(s) + 1 for s in late_shifts]

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

        # 担務充足制約
        for d in range(num_days):
            wd = calendar.weekday(int(year), int(month), d + 1)
            for idx, s_name in enumerate(user_shifts_list):
                s_id = idx + 1
                is_excl = edited_exclude.iloc[d, idx]
                is_sun_c = (wd == 6 and s_name == "C")
                
                skilled_sum = sum(shifts[(s, d, s_id)] for s in range(total_staff) if edited_skill.iloc[s, idx] == "○")
                trainee_sum = sum(shifts[(s, d, s_id)] for s in range(total_staff) if edited_skill.iloc[s, idx] == "△")

                if is_excl or is_sun_c:
                    model.Add(skilled_sum + trainee_sum == 0)
                else:
                    sk_ok = model.NewBoolVar(f'sk_ok_d{d}_i{idx}')
                    model.Add(skilled_sum == 1).OnlyEnforceIf(sk_ok)
                    obj_terms.append(sk_ok * 10000000)
                    model.Add(trainee_sum <= 1)

        # 個人制約
        for s in range(total_staff):
            is_off_m = [shifts[(s, d, S_OFF)] for d in range(num_days)]
            is_early_m = [model.NewBoolVar(f'ie_{s}_{d}') for d in range(num_days)]
            is_late_m = [model.NewBoolVar(f'il_{s}_{d}') for d in range(num_days)]
            
            for d in range(num_days):
                model.Add(sum(shifts[(s, d, i)] for i in range(num_user_shifts + 2)) == 1)
                model.Add(sum(shifts[(s, d, i)] for i in early_ids) == 1).OnlyEnforceIf(is_early_m[d])
                model.Add(sum(shifts[(s, d, i)] for i in early_ids) == 0).OnlyEnforceIf(is_early_m[d].Not())
                model.Add(sum(shifts[(s, d, i)] for i in late_ids) == 1).OnlyEnforceIf(is_late_m[d])
                model.Add(sum(shifts[(s, d, i)] for i in late_ids) == 0).OnlyEnforceIf(is_late_m[d].Not())
                
                req = edited_request.iloc[s, d]
                if req in char_to_id and req != "": model.Add(shifts[(s, d, char_to_id[req])] == 1)
                
                if d < num_days - 1:
                    for li in late_ids:
                        for ei in early_ids: model.Add(shifts[(s, d, li)] + shifts[(s, d+1, ei)] <= 1)
                if d == 0 and prev_late_matrix[s][-1] == 1:
                    for ei in early_ids: model.Add(shifts[(s, 0, ei)] == 0)

            # 4連勤、連休抑制、早遅ミックス、公休
            history_w = prev_work_matrix[s] + [(1 - shifts[(s, d, S_OFF)]) for d in range(num_days)]
            for start_d in range(len(history_w) - 4):
                model.Add(sum(history_w[start_d:start_d+5]) <= 4)

            # 連休抑制 (3連休以上)
            all_o_hist = [model.NewBoolVar(f'ao_{s}_{k}') for k in range(4 + num_days)]
            for k in range(4): model.Add(all_o_hist[k] == prev_off_matrix[s][k])
            for k in range(num_days):
                model.Add(all_o_hist[k+4] == 1).OnlyEnforceIf(is_off_m[k])
                model.Add(all_o_hist[k+4] == 0).OnlyEnforceIf(is_off_m[k].Not())
            for start_d in range(len(all_o_hist) - 2):
                is_3o = model.NewBoolVar(f'i3o_{s}_{start_d}')
                model.AddBoolAnd([all_o_hist[start_d], all_o_hist[start_d+1], all_o_hist[start_d+2]]).OnlyEnforceIf(is_3o)
                # 指定なしの3連休を重罰
                obj_terms.append(is_3o * -8000000)

            for d in range(num_days - 1):
                mix_b = model.NewBoolVar(f'mix_{s}_{d}')
                model.AddBoolAnd([is_early_m[d], is_late_m[d+1]]).OnlyEnforceIf(mix_b)
                obj_terms.append(mix_b * 5000000)

            if s < num_mgr:
                for d in range(num_days):
                    wd = calendar.weekday(int(year), int(month), d+1)
                    m_g = model.NewBoolVar(f'mg_{s}_{d}')
                    if wd >= 5: model.Add(shifts[(s, d, S_OFF)] == 1).OnlyEnforceIf(m_g)
                    else: model.Add(shifts[(s, d, S_OFF)] == 0).OnlyEnforceIf(m_g)
                    obj_terms.append(m_g * 1000000)
            else:
                for d in range(num_days):
                    if edited_request.iloc[s, d] != "日": model.Add(shifts[(s, d, S_NIKKIN)] == 0)

            model.Add(sum(is_off_m) == int(edited_hols.iloc[s, 0]))

        model.Maximize(sum(obj_terms))
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 30.0
        status = solver.Solve(model)

        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            st.success("✨ 勤務表が完成しました！")
            res_data = []
            char_map = {S_OFF: "休", S_NIKKIN: "日"}
            for idx, name in enumerate(user_shifts_list): char_map[idx + 1] = name
            for s in range(total_staff):
                row = [char_map[next(i for i in range(num_user_shifts + 2) if solver.Value(shifts[(s, d, i)]) == 1)] for d in range(num_days)]
                res_data.append(row)
            
            final_df = pd.DataFrame(res_data, index=staff_names, columns=days_cols)
            st.dataframe(final_df.style.applymap(lambda x: 'background-color: #ffcccc' if x=="休" else ('background-color: #e0f0ff' if x=="日" else ('background-color: #ffffcc' if x in early_shifts else 'background-color: #ccffcc'))), use_container_width=True)
            st.download_button("📥 結果をCSV保存", final_df.to_csv().encode('utf-8-sig'), f"roster_{year}_{month}.csv")
        else:
            st.error("⚠️ 解が見つかりません。公休数や見習い設定を調整してください。")

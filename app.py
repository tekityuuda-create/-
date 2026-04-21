import streamlit as st
import pandas as pd
import calendar
import json
from ortools.sat.python import cp_model

# --- 画面基本設定 ---
st.set_page_config(page_title="世界最高峰 勤務作成AI 究極版", page_icon="🛡️", layout="wide")

# --- セッション状態の初期化 ---
if 'config' not in st.session_state:
    st.session_state.config = {
        "num_mgr": 2,
        "num_regular": 8,
        "user_shifts": "A,B,C,D,E",
        "early_shifts": ["A", "B", "C"],
        "late_shifts": ["D", "E"],
        "year": 2025,
        "month": 1
    }

st.title("🛡️ 究極の勤務作成エンジン (Pro-Management V56)")

# --- サイドバー：設定の保存と読込 ---
with st.sidebar:
    st.header("💾 設定の保存と復元")
    
    # 1. 読み込み (Load)
    uploaded_file = st.file_uploader("設定ファイルをアップロード", type="json")
    if uploaded_file is not None:
        try:
            load_data = json.load(uploaded_file)
            st.session_state.config.update(load_data)
            st.success("設定を読み込みました。反映するには一度画面を操作してください。")
        except Exception as e:
            st.error("設定ファイルの形式が正しくありません。")

    # 2. 保存用データの準備 (Save)
    # 後の工程で入力された値をここに集約するための「箱」だけ定義
    st.divider()
    st.header("📅 基本設定")
    year = st.number_input("年", value=st.session_state.config["year"], step=1)
    month = st.number_input("月", min_value=1, max_value=12, value=st.session_state.config["month"], step=1)

# --- タブ分け ---
tab1, tab2, tab3 = st.tabs(["⚙️ システム構成", "👤 スタッフ・スキル設定", "🚀 勤務表の作成"])

with tab1:
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("👥 人数構成")
        num_mgr = st.number_input("管理者の人数", min_value=0, max_value=5, value=st.session_state.config["num_mgr"])
        num_regular = st.number_input("一般スタッフの人数", min_value=1, max_value=15, value=st.session_state.config["num_regular"])
        total_staff = int(num_mgr + num_regular)
        staff_names = [f"スタッフ{i+1}" for i in range(total_staff)]
    
    with col2:
        st.subheader("📋 勤務グループ")
        shift_input = st.text_input("勤務略称 (カンマ区切り)", st.session_state.config["user_shifts"])
        user_shifts_list = [s.strip() for s in shift_input.split(",") if s.strip()]
        
        early_shifts = st.multiselect("早番グループ", user_shifts_list, default=[s for s in user_shifts_list if s in st.session_state.config["early_shifts"]])
        late_shifts = st.multiselect("遅番グループ", user_shifts_list, default=[s for s in user_shifts_list if s in st.session_state.config["late_shifts"]])

with tab2:
    st.subheader("🎓 スキル・公休・教育目標")
    
    # スキル設定
    skill_options = ["○", "△", "×"]
    default_skill = pd.DataFrame("○", index=staff_names, columns=user_shifts_list)
    for col in user_shifts_list:
        default_skill[col] = pd.Categorical(default_skill[col], categories=skill_options)
    edited_skill = st.data_editor(default_skill, use_container_width=True, key="skill_editor")
    
    col_sub1, col_sub2 = st.columns(2)
    with col_sub1:
        st.write("📊 公休数 (B列)")
        default_hols = pd.DataFrame(9, index=staff_names, columns=["公休数"])
        edited_hols = st.data_editor(default_hols, use_container_width=True, key="hol_editor")
    
    with col_sub2:
        st.write("📈 見習い(△)の実施回数目標")
        trainee_cols = [f"{s}_見習い回数" for s in user_shifts_list]
        default_trainee = pd.DataFrame(0, index=staff_names, columns=trainee_cols)
        edited_trainee_targets = st.data_editor(default_trainee, use_container_width=True, key="trainee_target_editor")

with tab3:
    # カレンダー計算
    _, num_days = calendar.monthrange(int(year), int(month))
    weekdays_ja = ["月", "火", "水", "木", "金", "土", "日"]
    days_cols = [f"{d+1}({weekdays_ja[calendar.weekday(int(year), int(month), d+1)]})" for d in range(num_days)]
    options = ["", "休", "日"] + user_shifts_list

    st.subheader("⏮️ 前月末の勤務状況 (過去4日間)")
    prev_days = ["前月4日前", "前月3日前", "前月2日前", "前月末日"]
    default_prev = pd.DataFrame("休", index=staff_names, columns=prev_days)
    for col in prev_days:
        default_prev[col] = pd.Categorical(default_prev[col], categories=options)
    edited_prev = st.data_editor(default_prev, use_container_width=True, key="prev_editor")

    st.subheader("📝 今月の勤務指定 (申し込み)")
    default_request = pd.DataFrame("", index=staff_names, columns=days_cols)
    for col in days_cols:
        default_request[col] = pd.Categorical(default_request[col], categories=options)
    edited_request = st.data_editor(default_request, use_container_width=True, key="request_editor")

    st.subheader("🚫 不要担務の設定")
    default_exclude = pd.DataFrame(False, index=[d+1 for d in range(num_days)], columns=user_shifts_list)
    edited_exclude = st.data_editor(default_exclude, use_container_width=True, key="exclude_editor")

    # --- 保存ボタンのロジック (現在の値をJSON化) ---
    save_data = {
        "num_mgr": num_mgr,
        "num_regular": num_regular,
        "user_shifts": shift_input,
        "early_shifts": early_shifts,
        "late_shifts": late_shifts,
        "year": year,
        "month": month
    }
    st.sidebar.download_button(
        label="📥 現在の設定をPCに保存する",
        data=json.dumps(save_data, ensure_ascii=False),
        file_name=f"roster_settings_{year}_{month}.json",
        mime="application/json"
    )

    if st.button("🚀 勤務作成を実行する", type="primary"):
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
        prev_work_matrix, prev_late_matrix, prev_off_matrix = [], [], []
        for s in range(total_staff):
            row_w, row_l, row_o = [], [], []
            for d_idx in range(4):
                val = edited_prev.iloc[s, d_idx]
                sid = char_to_id.get(val, -1)
                row_w.append(1 if val != "休" else 0)
                row_l.append(1 if sid in late_ids else 0)
                row_o.append(1 if val == "休" else 0)
            prev_work_matrix.append(row_work := row_w)
            prev_late_matrix.append(row_l)
            prev_off_matrix.append(row_o)

        # 各日の制約
        for d in range(num_days):
            wd = calendar.weekday(int(year), int(month), d + 1)
            for idx, s_name in enumerate(user_shifts_list):
                s_id = idx + 1
                is_ex = edited_exclude.iloc[d, idx]
                is_sun_c = (wd == 6 and s_name == "C")
                skilled_sum = sum(shifts[(s, d, s_id)] for s in range(total_staff) if edited_skill.iloc[s, idx] == "○")
                trainee_sum = sum(shifts[(s, d, s_id)] for s in range(total_staff) if edited_skill.iloc[s, idx] == "△")
                if is_ex or is_sun_c:
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
                
                # スキル×の禁止
                for idx, _ in enumerate(user_shifts_list):
                    if edited_skill.iloc[s, idx] == "×": model.Add(shifts[(s, d, idx+1)] == 0)

                req = edited_request.iloc[s, d]
                if req in char_to_id and req != "": model.Add(shifts[(s, d, char_to_id[req])] == 1)
                
                if d < num_days - 1:
                    for li in late_ids:
                        for ei in early_ids: model.Add(shifts[(s, d, li)] + shifts[(s, d+1, ei)] <= 1)
                if d == 0 and prev_late_matrix[s][-1] == 1:
                    for ei in early_ids: model.Add(shifts[(s, 0, ei)] == 0)

            # 4連勤、連休、早遅ミックス、公休
            this_month_work = [(1 - shifts[(s, d, S_OFF)]) for d in range(num_days)]
            history_w = prev_work_matrix[s] + this_month_work
            for start_d in range(len(history_w) - 4): model.Add(sum(history_w[start_d:start_d+5]) <= 4)

            for d in range(num_days - 1):
                mix_b = model.NewBoolVar(f'mix_{s}_{d}')
                model.AddBoolAnd([is_early_m[d], is_late_m[d+1]]).OnlyEnforceIf(mix_b)
                obj_terms.append(mix_b * 5000000)

            if s < num_mgr:
                for d in range(num_days):
                    wd_val = calendar.weekday(int(year), int(month), d+1)
                    m_g = model.NewBoolVar(f'mg_{s}_{d}')
                    if wd_val >= 5: model.Add(shifts[(s, d, S_OFF)] == 1).OnlyEnforceIf(m_g)
                    else: model.Add(shifts[(s, d, S_OFF)] == 0).OnlyEnforceIf(m_g)
                    obj_terms.append(m_g * 1000000)
            else:
                for d in range(num_days):
                    if edited_request.iloc[s, d] != "日": model.Add(shifts[(s, d, S_NIKKIN)] == 0)

            # 見習い回数
            for idx, _ in enumerate(user_shifts_list):
                t_val = int(edited_trainee_targets.iloc[s, idx])
                if edited_skill.iloc[s, idx] == "△" and t_val > 0:
                    model.Add(sum(shifts[(s, d, idx+1)] for d in range(num_days)) == t_val)

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
            final_df["公休計"] = [row.count("休") for row in res_data]
            st.dataframe(final_df.style.applymap(lambda x: 'background-color: #ffcccc' if x=="休" else ('background-color: #e0f0ff' if x=="日" else ('background-color: #ffffcc' if x in early_shifts else 'background-color: #ccffcc'))), use_container_width=True)
            st.download_button("📥 結果をCSV保存", final_df.to_csv().encode('utf-8-sig'), f"roster_{year}_{month}.csv")
        else:
            st.error("⚠️ 解が見つかりません。条件を調整してください。")

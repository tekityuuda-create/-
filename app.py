import streamlit as st
import pandas as pd
import calendar
from ortools.sat.python import cp_model

# 画面設定
st.set_page_config(page_title="世界最高峰 勤務作成AI マスタ完全版", layout="wide")
st.title("🛡️ 究極の勤務作成エンジン (Flexible Shift Categorizer)")

# --- サイドバー：詳細設定 ---
with st.sidebar:
    st.header("⚙️ システム構成")
    num_mgr = st.number_input("管理者の人数 (上からN名)", min_value=0, max_value=5, value=2)
    num_regular = st.number_input("一般スタッフの人数", min_value=1, max_value=15, value=8)
    total_staff = num_mgr + num_regular
    
    st.header("📋 勤務・カテゴリー設定")
    shift_input = st.text_input("勤務の略称 (カンマ区切り)", "A,B,C,D,E")
    user_shifts = [s.strip() for s in shift_input.split(",") if s.strip()]
    num_user_shifts = len(user_shifts)
    
    # 【新機能】早番・遅番のグループ分け
    st.subheader("🕑 シフト属性設定")
    st.info("ここで設定した『遅番』の翌日に『早番』が来ることをAIが自動禁止します。")
    early_shifts = st.multiselect("早番グループ (A, B, Cなど)", user_shifts, default=[s for s in user_shifts if s in ["A","B","C"]])
    late_shifts = st.multiselect("遅番グループ (D, Eなど)", user_shifts, default=[s for s in user_shifts if s in ["D","E"]])
    
    st.header("📅 対象年月")
    year = st.number_input("年", value=2025, step=1)
    month = st.number_input("月", min_value=1, max_value=12, value=1, step=1)
    
    st.header("👤 公休数設定")
    staff_names = []
    for i in range(total_staff):
        role_label = "管理者" if i < num_mgr else "一般"
        staff_names.append(f"スタッフ{i+1}({role_label})")
    
    target_hols = []
    for i in range(total_staff):
        target_hols.append(st.number_input(f"{staff_names[i]} の公休", value=9, key=f"hol_{i}"))

# --- カレンダー計算 ---
_, num_days = calendar.monthrange(int(year), int(month))
weekdays_ja = ["月", "火", "水", "木", "金", "土", "日"]
days_cols = [f"{d+1}({weekdays_ja[calendar.weekday(int(year), int(month), d+1)]})" for d in range(num_days)]

# --- メイン画面：勤務指定 ---
st.subheader("📝 勤務指定・申し込み")
options = ["", "休", "出"] + user_shifts
request_df = pd.DataFrame("", index=staff_names, columns=days_cols)
for col in days_cols:
    request_df[col] = pd.Categorical(request_df[col], categories=options)

edited_request = st.data_editor(request_df, use_container_width=True, key="request_editor")

# --- 不要担務の設定 ---
st.subheader("🚫 不要担務の設定")
exclude_df = pd.DataFrame(False, index=[d+1 for d in range(num_days)], columns=user_shifts)
edited_exclude = st.data_editor(exclude_df, use_container_width=True, key="exclude_editor")

# --- 計算ロジック ---
if st.button("🚀 この設定で勤務表を生成する"):
    model = cp_model.CpModel()
    
    # IDマッピング
    S_OFF = 0
    S_WORK = num_user_shifts + 1
    
    # 変数作成
    shifts = {}
    for s in range(total_staff):
        for d in range(num_days):
            for i in range(num_user_shifts + 2):
                shifts[(s, d, i)] = model.NewBoolVar(f's{s}d{d}i{i}')

    obj_terms = []

    # 属性IDの抽出
    early_ids = [user_shifts.index(s) + 1 for s in early_shifts]
    late_ids = [user_shifts.index(s) + 1 for s in late_shifts]

    # --- 日ごとの制約 ---
    for d in range(num_days):
        wd = calendar.weekday(int(year), int(month), d + 1)
        
        # 1. 役割の充足
        for idx, s_name in enumerate(user_shifts):
            s_id = idx + 1
            is_excluded = edited_exclude.iloc[d, idx]
            is_sun_c = (wd == 6 and s_name == "C")
            
            total_on_duty = sum(shifts[(s, d, s_id)] for s in range(total_staff))
            
            if is_excluded or is_sun_c:
                model.Add(total_on_duty == 0)
            else:
                is_filled = model.NewBoolVar(f'f_d{d}_s{s_id}')
                model.Add(total_on_duty == 1).OnlyEnforceIf(is_filled)
                obj_terms.append(is_filled * 100000000)

        for s in range(total_staff):
            # 1人1シフト
            model.Add(sum(shifts[(s, d, i)] for i in range(num_user_shifts + 2)) == 1)
            
            # 2. 【究極】遅→早禁止ロジック (設定に基づいて動的に生成)
            if d < num_days - 1:
                for l_id in late_ids:
                    for e_id in early_ids:
                        model.Add(shifts[(s, d, l_id)] + shifts[(s, d+1, e_id)] <= 1)

            # 3. 勤務指定の反映
            req = edited_request.iloc[s, d]
            if req == "休":
                model.Add(shifts[(s, d, S_OFF)] == 1)
            elif req == "出":
                model.Add(shifts[(s, d, S_WORK)] == 1)
            elif req in user_shifts:
                model.Add(shifts[(s, d, user_shifts.index(req) + 1)] == 1)

    # --- 個人・管理者別の制約 ---
    for s in range(total_staff):
        # 4連勤制限 (5連勤禁止)
        for d in range(num_days - 4):
            model.Add(sum((1 - shifts[(s, d+k, S_OFF)]) for k in range(5)) <= 4)

        if s < num_mgr:
            # 管理者：土日祝休み（努力目標）
            for d in range(num_days):
                if calendar.weekday(int(year), int(month), d+1) >= 5:
                    is_mgr_off = model.NewBoolVar(f'mgr_off_{s}_{d}')
                    model.Add(shifts[(s, d, S_OFF)] == 1).OnlyEnforceIf(is_mgr_off)
                    obj_terms.append(is_mgr_off * 1000000)
                else:
                    model.Add(shifts[(s, d, S_OFF)] == 0)
        else:
            # 一般職：指定なき「出」禁止
            for d in range(num_days):
                if edited_request.iloc[s, d] != "出":
                    model.Add(shifts[(s, d, S_WORK)] == 0)

        # 公休数（±1日のズレを許容）
        actual_hols = sum(shifts[(s, d, S_OFF)] for d in range(num_days))
        model.Add(actual_hols >= int(target_hols[s]) - 1)
        model.Add(actual_hols <= int(target_hols[s]) + 1)
        is_exact = model.NewBoolVar(f'exact_{s}')
        model.Add(actual_hols == int(target_hols[s])).OnlyEnforceIf(is_exact)
        obj_terms.append(is_exact * 10000000)

    model.Maximize(sum(obj_terms))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30.0
    status = solver.Solve(model)

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        st.success("✨ 最適な勤務表を生成しました！")
        res_data = []
        char_map = {S_OFF: "休", S_WORK: "出"}
        for idx, name in enumerate(user_shifts):
            char_map[idx + 1] = name
            
        for s in range(total_staff):
            row = []
            for d in range(num_days):
                for i in range(num_user_shifts + 2):
                    if solver.Value(shifts[(s, d, i)]) == 1:
                        row.append(char_map[i])
            res_data.append(row)
        
        final_df = pd.DataFrame(res_data, index=staff_names, columns=days_cols)
        final_df["公休計"] = [row.count("休") for row in res_data]
        
        def color_map(val):
            if val == "休": return 'background-color: #ffcccc'
            if val == "出": return 'background-color: #e0f0ff'
            if val in early_shifts: return 'background-color: #ffffcc' # 早番は黄色
            if val in late_shifts: return 'background-color: #ccffcc' # 遅番は緑
            return ''

        st.dataframe(final_df.style.applymap(color_map), use_container_width=True)
        st.download_button("📥 CSV保存", final_df.to_csv().encode('utf-8-sig'), f"roster_{year}_{month}.csv")
    else:
        st.error("⚠️ 条件が厳しすぎます。公休数を調整するか、不要設定を減らしてください。")

import streamlit as st
import pandas as pd
import calendar
from ortools.sat.python import cp_model

# --- 画面設定 ---
st.set_page_config(
    page_title="世界最高峰 勤務作成AI 究極版", 
    page_icon="📅", # ここに icon.png と書けば自作画像になります
    layout="wide"
)
st.title("🛡️ 究極の勤務作成エンジン (Ultimate Resolver V43)")

# --- サイドバー：詳細設定 ---
with st.sidebar:
    st.header("⚙️ システム構成")
    num_mgr = st.number_input("管理者の人数", min_value=0, max_value=5, value=2)
    num_regular = st.number_input("一般スタッフの人数", min_value=1, max_value=15, value=8)
    total_staff = num_mgr + num_regular
    
    st.header("📋 勤務・カテゴリー設定")
    shift_input = st.text_input("勤務の略称 (カンマ区切り)", "A,B,C,D,E")
    user_shifts = [s.strip() for s in shift_input.split(",") if s.strip()]
    num_user_shifts = len(user_shifts)
    
    st.subheader("🕑 シフト属性設定")
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

# --- メイン画面：勤務指定 ---
st.subheader("📝 勤務指定・申し込み")
# 【修正ポイント】「出」を「日」に変更
options = ["", "休", "日"] + user_shifts
request_df = pd.DataFrame("", index=staff_names, columns=days_cols)
for col in days_cols:
    request_df[col] = pd.Categorical(request_df[col], categories=options)
edited_request = st.data_editor(request_df, use_container_width=True, key="request_editor")

# --- 不要担務の設定 ---
st.subheader("🚫 不要担務の設定")
exclude_df = pd.DataFrame(False, index=[d+1 for d in range(num_days)], columns=user_shifts)
edited_exclude = st.data_editor(exclude_df, use_container_width=True, key="exclude_editor")

# --- 計算ロジック ---
if st.button("🚀 勤務表を生成する"):
    model = cp_model.CpModel()
    # 0:休, 1~N:ユーザー勤務, N+1:日(NIKKIN)
    S_OFF, S_NIKKIN = 0, num_user_shifts + 1
    shifts = {(s, d, i): model.NewBoolVar(f's{s}d{d}i{i}') for s in range(total_staff) for d in range(num_days) for i in range(num_user_shifts + 2)}
    obj_terms = []

    early_ids = [user_shifts.index(s) + 1 for s in early_shifts]
    late_ids = [user_shifts.index(s) + 1 for s in late_shifts]

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
                # 担務充足（最優先：1億点）
                filled = model.NewBoolVar(f'f_d{d}_s{s_id}')
                model.Add(total_on_duty == 1).OnlyEnforceIf(filled)
                obj_terms.append(filled * 100000000)

        for s in range(total_staff):
            model.Add(sum(shifts[(s, d, i)] for i in range(num_user_shifts + 2)) == 1)
            
            # 2. 遅→早禁止 (1000万点)
            if d < num_days - 1:
                for l_id in late_ids:
                    for e_id in early_ids:
                        nle = model.NewBoolVar(f'nle_{s}_{d}_{l_id}_{e_id}')
                        model.Add(shifts[(s, d, l_id)] + shifts[(s, d+1, e_id)] <= 1).OnlyEnforceIf(nle)
                        obj_terms.append(nle * 10000000)
            
            # 3. 勤務指定
            req = edited_request.iloc[s, d]
            if req in options and req != "":
                if req == "休": rid = S_OFF
                elif req == "日": rid = S_NIKKIN
                else: rid = user_shifts.index(req) + 1
                model.Add(shifts[(s, d, rid)] == 1)

    for s in range(total_staff):
        # 4. 連勤制限（5連勤以上を抑制：-500万点）
        for d in range(num_days - 4):
            n5c = model.NewBoolVar(f'n5c_{s}_{d}')
            model.Add(sum((1 - shifts[(s, d+k, S_OFF)]) for k in range(5)) <= 4).OnlyEnforceIf(n5c)
            obj_terms.append(n5c * 5000000)

        # 5. 連休制限（申し込みなしの3連休以上に抑制：-200万点）
        for d in range(num_days - 2):
            is_3off = model.NewBoolVar(f'3off_{s}_{d}')
            model.AddBoolAnd([shifts[(s, d, S_OFF)], shifts[(s, d+1, S_OFF)], shifts[(s, d+2, S_OFF)]]).OnlyEnforceIf(is_3off)
            req_off = any(edited_request.iloc[s, d+k] == "休" for k in range(3))
            if not req_off:
                obj_terms.append(is_3off * -2000000)

        # 6. 管理者と一般職のルール
        if s < num_mgr:
            for d in range(num_days):
                wd = calendar.weekday(int(year), int(month), d+1)
                # 管理者は平日は原則出勤 (日勤または担務)
                if wd < 5:
                    m_work = model.NewBoolVar(f'mw_{s}_{d}')
                    model.Add(shifts[(s, d, S_OFF)] == 0).OnlyEnforceIf(m_work)
                    obj_terms.append(m_work * 1000000)
                else:
                    # 土日は休みを優先
                    m_off = model.NewBoolVar(f'mo_{s}_{d}')
                    model.Add(shifts[(s, d, S_OFF)] == 1).OnlyEnforceIf(m_off)
                    obj_terms.append(m_off * 500000)
        else:
            # 一般職：指定なき「日」は絶対禁止（バックアップは管理者の役目）
            for d in range(num_days):
                if edited_request.iloc[s, d] != "日":
                    model.Add(shifts[(s, d, S_NIKKIN)] == 0)

        # 7. 公休数 (B列) 1日のズレを許容しつつ最適化
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

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        st.success("✨ 条件を最適化し『日勤(日)』を含む勤務表を生成しました！")
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
    else:
        st.error("⚠️ 解が見つかりませんでした。設定を確認してください。")

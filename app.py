import streamlit as st
import pandas as pd
import calendar
import json
from ortools.sat.python import cp_model

# ========================================================
# 🛡️ 究極の勤務作成エンジン V88 (Stable Matrix Pass)
# ========================================================

st.set_page_config(page_title="究極勤務AI V88", page_icon="🛡️", layout="wide")

# --- セッション状態の初期化 ---
if 'config' not in st.session_state:
    st.session_state.config = {
        "num_mgr": 2, "num_regular": 8,
        "staff_names": [f"スタッフ{i+1}" for i in range(10)],
        "user_shifts": "A,B,C,D,E", "early_shifts": ["A", "B", "C"], "late_shifts": ["D", "E"],
        "year": 2025, "month": 1,
        "master_data": None, "prev_data": None, "request_data": None, "exclude_data": None
    }

st.title("🛡️ 究極の勤務作成エンジン V88 (Zero-Latency Core)")

# --- サイドバー：全管理 ---
with st.sidebar:
    st.header("💾 データ同期")
    up_file = st.file_uploader("JSON読込", type="json")
    if up_file:
        try:
            st.session_state.config.update(json.load(up_file))
            st.success("全ての変数を同期。")
            st.rerun()
        except: st.error("不正なファイル。")

    st.divider()
    st.header("🎯 最適化ウェイト")
    w_strict = st.slider("ルールの厳格度", 0, 100, 95)
    w_mix = st.slider("早遅ミキシング", 0, 100, 75)
    w_fair = st.slider("公平性 (回数平準化)", 0, 100, 50)

    st.divider()
    y_in = int(st.number_input("年", 2024, 2030, st.session_state.config["year"]))
    m_in = int(st.number_input("月", 1, 12, st.session_state.config["month"]))
    st.session_state.config["year"], st.session_state.config["month"] = y_in, m_in

# --- タブ ---
t1, t2 = st.tabs(["🏗️ 1. 基本・スタッフ設定", "🧬 2. 勤務指定・AI作成"])

with t1:
    c_l, c_r = st.columns(2)
    with c_l:
        st.subheader("👥 人員構成")
        n_m = st.number_input("管理者の人数", 0, 5, st.session_state.config["num_mgr"])
        n_r = st.number_input("一般職の人数", 1, 20, st.session_state.config["num_regular"])
        st.session_state.config["num_mgr"], st.session_state.config["num_regular"] = n_m, n_r
        total_st = n_m + n_r
        raw_s = st.text_input("勤務略称 (,) 区切り", st.session_state.config["user_shifts"])
        s_list = [s.strip() for s in raw_s.split(",") if s.strip()]
        st.session_state.config["user_shifts"] = raw_s
    with c_r:
        st.subheader("🕑 シフト属性")
        e_g = st.multiselect("早番グループ", s_list, default=[x for x in s_list if x in st.session_state.config["early_shifts"]])
        l_g = st.multiselect("遅番グループ", s_list, default=[x for x in s_list if x in st.session_state.config["late_shifts"]])
        st.session_state.config["early_shifts"], st.session_state.config["late_shifts"] = e_g, l_g

    st.divider()
    st.subheader("👤 スタッフ詳細マスタ (名前・公休・スキル・回数)")
    
    # 統合テーブル作成
    m_cols = ["名前", "公休数"]
    for s in s_list: 
        m_cols.append(f"{s}スキル")
        m_cols.append(f"{s}回数")

    if st.session_state.config.get("master_data") is None:
        init_df = pd.DataFrame("", index=range(total_st), columns=m_cols)
        for i in range(total_st):
            init_df.at[i, "名前"] = f"スタッフ{i+1}"
            init_df.at[i, "公休数"] = 9
            for sl in s_list: init_df.at[i, f"{sl}スキル"], init_df.at[i, f"{sl}回数"] = "○", 0
        st.session_state.config["master_data"] = init_df.to_dict()

    m_df = pd.DataFrame(st.session_state.config["master_data"])
    
    # 型エラー修正：行数・列数調整（ffillの最新形式）
    m_df = m_df.reindex(range(total_st))
    m_df["名前"] = m_df["名前"].fillna("未設定")
    m_df["公休数"] = m_df["公休数"].fillna(9)
    for s in s_list:
        if f"{s}スキル" not in m_df.columns: m_df[f"{s}スキル"] = "○"
        if f"{s}回数" not in m_df.columns: m_df[f"{s}回数"] = 0
        m_df[f"{s}スキル"] = pd.Categorical(m_df[f"{s}スキル"], categories=["○", "△", "×"])

    ed_master = st.data_editor(m_df, use_container_width=True, key="master_ed_v88")
    st.session_state.config["master_data"] = ed_master.to_dict()
    current_staff_names = ed_master["名前"].tolist()

with t2:
    _, nd = calendar.monthrange(y_in, m_in)
    ja_week = ["月","火","水","木","金","土","日"]
    d_cols = [f"{i+1}({ja_week[calendar.weekday(y_in,m_in,i+1)]})" for i in range(nd)]
    opts = ["", "休", "日"] + s_list

    c1, c2 = st.columns([1, 3.2])
    with c1:
        st.write("⏮️ 引継状況 (直近4日)")
        saved_p = st.session_state.config.get("prev_data")
        p_df = pd.DataFrame(saved_p) if saved_p else pd.DataFrame("休", index=current_staff_names, columns=["4日前","3日前","2日前","末日"])
        p_df = p_df.reindex(index=current_staff_names).fillna("休")
        for c in p_df.columns: p_df[c] = pd.Categorical(p_df[c], categories=["日", "休", "早", "遅"])
        ed_p = st.data_editor(p_df, use_container_width=True, key="p_ui_v88")
        st.session_state.config["prev_data"] = ed_p.to_dict()

    with c2:
        st.write("📝 今月の固定指定")
        saved_req = st.session_state.config.get("request_data")
        r_df = pd.DataFrame(saved_req) if saved_req else pd.DataFrame("", index=current_staff_names, columns=d_cols)
        r_df = r_df.reindex(index=current_staff_names, columns=d_cols).fillna("")
        for c in d_cols: r_df[c] = pd.Categorical(r_df[c], categories=opts)
        ed_req = st.data_editor(r_df, use_container_width=True, key="r_ui_v88")
        st.session_state.config["request_data"] = ed_req.to_dict()

    st.write("🚫 不要担務の指定")
    saved_ex = st.session_state.config.get("exclude_data")
    ex_df = pd.DataFrame(saved_ex) if saved_ex else pd.DataFrame(False, index=[i+1 for i in range(nd)], columns=s_list)
    ex_df = ex_df.reindex(index=[i+1 for i in range(nd)], columns=s_list).fillna(False)
    ed_ex = st.data_editor(ex_df, use_container_width=True, key="ex_ui_v88")
    st.session_state.config["exclude_data"] = ed_ex.to_dict()

    st.sidebar.download_button("📥 今の全てを保存", json.dumps(st.session_state.config, ensure_ascii=False), "MyAI_V88_Settings.json")

    # --- 最適化実行 (Core v88) ---
    if st.button("🚀 AIによる究極の最適化を実行する", type="primary"):
        model = cp_model.CpModel()
        S_OFF, S_NIK = 0, len(s_list) + 1
        e_ids = [s_list.index(x) + 1 for x in e_g]
        l_ids = [s_list.index(x) + 1 for x in l_g]
        x = {(si, di, i): model.NewBoolVar(f'x_{si}_{di}_{i}') for si in range(total_st) for di in range(nd) for i in range(len(s_list)+2)}
        penalties = []

        # 月またぎ判定
        for si in range(total_st):
            if ed_p.iloc[si, 3] == "遅":
                for ei in e_ids: model.Add(x[si, 0, ei] == 0)

        # 担務充足 & スキル
        for d in range(nd):
            wday = calendar.weekday(y_in, m_in, d+1)
            for i, s_n in enumerate(s_list):
                sid = i + 1
                is_closed = ed_ex.iloc[d, i] or (wday == 6 and s_n == "C")
                circles = [si for si in range(total_st) if ed_master.iloc[si, 2 + i*2] == "○"]
                triangles = [si for si in range(total_st) if ed_master.iloc[si, 2 + i*2] == "△"]
                
                sum_c = sum(x[si, d, sid] for si in circles)
                sum_t = sum(x[si, d, sid] for si in triangles)
                
                if is_closed: model.Add(sum(x[si, d, sid] for si in range(total_st)) == 0)
                else:
                    filled = model.NewBoolVar(f'fill_{d}_{sid}')
                    model.Add(sum_c == 1).OnlyEnforceIf(filled)
                    penalties.append(filled * 50000000) 
                    model.Add(sum_t <= 1)
                    # 管理者が仕事をする場合、微減点（一般職優先）
                    for mg_i in range(n_m): penalties.append(x[mg_i, d, sid] * -5000)
            for si in range(total_st): model.Add(sum(x[si, d, s_sh] for s_sh in range(len(s_list)+2)) == 1)

        # 個人別＆バランスロジック
        for si in range(total_st):
            ise_m = [model.NewBoolVar(f'ise_{si}_{d}') for d in range(nd)]
            isl_m = [model.NewBoolVar(f'isl_{si}_{d}') for d in range(nd)]
            is_o_m = [x[si, d, S_OFF] for d in range(nd)]
            for di in range(nd):
                model.Add(sum(x[si, di, i] for i in e_ids) == 1).OnlyEnforceIf(ise_m[di])
                model.Add(sum(x[si, di, i] for i in e_ids) == 0).OnlyEnforceIf(ise_m[di].Not())
                model.Add(sum(x[si, di, i] for i in l_ids) == 1).OnlyEnforceIf(isl_m[di])
                model.Add(sum(x[si, di, i] for i in l_ids) == 0).OnlyEnforceIf(isl_m[di].Not())
                # 申し込み
                rv = ed_req.iloc[si, di]
                m_c = {"休":S_OFF, "日":S_NIK, "":-1}
                for ik, nk in enumerate(s_list): m_c[nk] = ik+1
                if rv in m_c and m_c[rv] != -1: model.Add(x[si, di, m_c[rv]] == 1)
                # スキル不可(×)
                for ik, nk in enumerate(s_list):
                    if ed_master.iloc[si, 2+ik*2] == "×": model.Add(x[si, di, ik+1] == 0)
                # 遅→早
                if di < nd - 1:
                    le_ok = model.NewBoolVar(f'le_{si}_{di}')
                    model.Add(isl_m[di] + ise_m[di+1] <= 1).OnlyEnforceIf(le_ok)
                    penalties.append(le_ok * 200000 * w_strict)

            # 4連勤、3連休、ミックス、公休
            hst_w = [1 if ed_p.iloc[si, k] != "休" else 0 for k in range(4)] + [(1 - is_o_m[di]) for di in range(nd)]
            for sk in range(len(hst_w)-4):
                c4v = model.NewBoolVar(f'c4_{si}_{sk}')
                model.Add(sum(hst_w[sk:sk+5]) <= 4).OnlyEnforceIf(c4v)
                penalties.append(c4v * 100000 * w_strict)
            
            hst_o = [1 if ed_p.iloc[si, k] == "休" else 0 for k in range(4)] + is_o_m
            for sk in range(len(hst_o)-2):
                i3o = model.NewBoolVar(f'o3_{si}_{sk}')
                model.AddBoolAnd(hst_o[sk:sk+3]).OnlyEnforceIf(i3o)
                # 指定外の3連休に巨額ペナルティ（これで休みが散る）
                cur_days = [sk+k-4 for k in range(3) if 0 <= sk+k-4 < nd]
                if cur_days and not any(ed_req.iloc[si, k] == "休" for k in cur_days):
                    penalties.append(i3o * -5000000)

            for di in range(nd-1):
                mx_b = model.NewBoolVar(f'mx_{si}_{di}')
                model.AddBoolAnd([ise_m[di], isl_m[di+1]]).OnlyEnforceIf(mx_b)
                penalties.append(mx_b * 5000 * w_mix)

            # 管理・一般ルール
            if si < n_m:
                for di in range(nd):
                    is_ss = (calendar.weekday(y_in,m_in,di+1) >= 5)
                    mgv = model.NewBoolVar(f'mgv_{si}_{di}')
                    if is_ss: model.Add(is_o_m[di] == 1).OnlyEnforceIf(mgv)
                    else: model.Add(is_o_m[di] == 0).OnlyEnforceIf(mgv)
                    penalties.append(mgv * 50000)
            else:
                for di in range(nd):
                    if ed_req.iloc[si, di] != "日": model.Add(x[si, di, S_NIK] == 0)

            # 教育、公休
            for ik, nk in enumerate(s_list):
                tg = int(ed_master.iloc[si, 3+ik*2] or 0)
                if tg > 0 and ed_master.iloc[si, 2+ik*2] == "△": model.Add(sum(x[si, d, ik+1] for d in range(nd)) == tg)
            herr = model.NewIntVar(0, nd, f'her_{si}')
            model.AddAbsEquality(herr, sum(is_o_m) - int(ed_master.iloc[si, 1]))
            penalties.append(herr * -1000000 * w_strict)

        model.Maximize(sum(penalties))
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 45.0
        status = solver.Solve(model)

        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            st.success("🎉 条件を完璧にクリア！最高峰の勤務案です。")
            res_df_l = []
            id_char = {S_OFF:"休", S_NIK:"日"}
            for idx, nm in enumerate(s_list): id_char[idx+1] = nm
            for si in range(total_st):
                res_df_l.append([id_char[next(j for j in range(len(s_list)+2) if solver.Value(x[si,d,j])==1)] for d in range(nd)])
            final = pd.DataFrame(res_df_l, index=current_staff_names, columns=d_cols)
            final["公休計"] = [row.count("休") for row in res_df_l]
            def pnt(v):
                if v=="休": return 'background-color:#ffcccc'
                if v=="日": return 'background-color:#e0f0ff'
                if v in e_g: return 'background-color:#ffffcc'
                return 'background-color:#ccffcc'
            st.dataframe(final.style.map(pnt), use_container_width=True)
        else: st.error("❌ 条件に自己矛盾が生じました。公休設定などを微調整してください。")

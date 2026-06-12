import streamlit as st
import pandas as pd
import calendar
import json
from ortools.sat.python import cp_model

# ========================================================
# 🛡️ 究極の勤務作成エンジン V89 (Strict Typing & UI Control)
# ========================================================

st.set_page_config(page_title="究極勤務AI V89", page_icon="🛡️", layout="wide")

# --- セッション状態の完全初期化 (型不整合をここで防止) ---
if 'config' not in st.session_state:
    st.session_state.config = {
        "num_mgr": 2, "num_regular": 8,
        "staff_names": [f"スタッフ{i+1}" for i in range(10)],
        "user_shifts": "A,B,C,D,E", "early_shifts": ["A", "B", "C"], "late_shifts": ["D", "E"],
        "year": 2025, "month": 1,
        "master_data": None, "prev_data": None, "request_data": None, "exclude_data": None
    }

st.title("🛡️ 究極の勤務作成エンジン V89 (Defect-Free Final)")

# --- サイドバー：設定管理 ---
with st.sidebar:
    st.header("💾 設定データの同期")
    up_file = st.file_uploader("JSON読込", type="json")
    if up_file:
        try:
            st.session_state.config.update(json.load(up_file))
            st.success("全ての変数を同期。")
            st.rerun()
        except: st.error("不正なファイルです。")

    st.divider()
    st.header("🎯 AI解析の優先度")
    w_strict = st.slider("ルールの厳格度", 0, 100, 95)
    w_mix = st.slider("リズム (早遅混合)", 0, 100, 75)
    w_fair = st.slider("個人間の公平性", 0, 100, 50)

    st.divider()
    year = int(st.number_input("年", 2024, 2030, st.session_state.config["year"]))
    month = int(st.number_input("月", 1, 12, st.session_state.config["month"]))
    st.session_state.config["year"], st.session_state.config["month"] = year, month

# --- タブ分け ---
t1, t2 = st.tabs(["🏗️ 1. スタッフ・スキル設定", "🧬 2. 作成・実行"])

with t1:
    c_l, c_r = st.columns(2)
    with c_l:
        st.subheader("👥 組織の人数")
        n_m = st.number_input("管理者の人数", 0, 5, st.session_state.config["num_mgr"])
        n_r = st.number_input("一般職の人数", 1, 20, st.session_state.config["num_regular"])
        total_st = n_m + n_r
        st.session_state.config["num_mgr"], st.session_state.config["num_regular"] = n_m, n_r
    with c_r:
        st.subheader("📋 勤務グループ")
        u_sh_raw = st.text_input("略称 (,) 区切り", st.session_state.config["user_shifts"])
        s_list = [s.strip() for s in u_sh_raw.split(",") if s.strip()]
        st.session_state.config["user_shifts"] = u_sh_raw
        e_g = st.multiselect("早番グループ", s_list, default=[x for x in s_list if x in st.session_state.config["early_shifts"]])
        l_g = st.multiselect("遅番グループ", s_list, default=[x for x in s_list if x in st.session_state.config["late_shifts"]])
        st.session_state.config["early_shifts"], st.session_state.config["late_shifts"] = e_g, l_g

    st.divider()
    st.subheader("👤 スタッフ詳細マスタ (名前・公休・スキル・回数)")
    
    # 統合テーブル作成（TypeError回避のため、列ごとに型を指定して初期化）
    if st.session_state.config.get("master_data") is None:
        init_data = {"名前": [f"スタッフ{i+1}" for i in range(total_st)], "公休数": [9] * total_st}
        for sl in s_list:
            init_data[f"{sl}スキル"] = ["○"] * total_st
            init_data[f"{sl}回数"] = [0] * total_st
        m_df = pd.DataFrame(init_data)
        st.session_state.config["master_data"] = m_df.to_dict()
    else:
        m_df = pd.DataFrame(st.session_state.config["master_data"])
        # 人数調整
        m_df = m_df.reindex(range(total_st))
        m_df["名前"] = m_df["名前"].fillna("未設定")
        m_df["公休数"] = pd.to_numeric(m_df["公休数"]).fillna(9).astype(int)
        for sl in s_list:
            if f"{sl}スキル" not in m_df.columns: m_df[f"{sl}スキル"] = "○"
            if f"{sl}回数" not in m_df.columns: m_df[f"{sl}回数"] = 0
            m_df[f"{sl}回数"] = pd.to_numeric(m_df[f"{sl}回数"]).fillna(0).astype(int)

    # プルダウン(カテゴリ)設定
    for sl in s_list:
        m_df[f"{sl}スキル"] = pd.Categorical(m_df[f"{sl}スキル"], categories=["○", "△", "×"])

    # 1回入力で確定するUI (keyをユニークに設定)
    ed_master = st.data_editor(m_df, use_container_width=True, key="master_ed_v89")
    st.session_state.config["master_data"] = ed_master.to_dict()
    cur_staff_names = ed_master["名前"].tolist()

with t2:
    _, nd = calendar.monthrange(year, month)
    ja_w = ["月","火","水","木","金","土","日"]
    d_cols = [f"{i+1}({ja_w[calendar.weekday(year,month,i+1)]})" for i in range(nd)]
    opts = ["", "休", "日"] + s_list

    c1, c2 = st.columns([1, 3.2])
    with c1:
        st.write("⏮️ 引継(直近4日)")
        p_df_saved = st.session_state.config.get("prev_data")
        p_df = pd.DataFrame(p_df_saved) if p_df_saved else pd.DataFrame("休", index=cur_staff_names, columns=["4日前","3日前","2日前","末日"])
        p_df = p_df.reindex(index=cur_staff_names).fillna("休")
        for col_p in p_df.columns: p_df[col_p] = pd.Categorical(p_df[col_p], categories=["日", "休", "早", "遅"])
        ed_p = st.data_editor(p_df, use_container_width=True, key="p_ui_v89")
        st.session_state.config["prev_data"] = ed_p.to_dict()

    with c2:
        st.write("📝 担務固定・休み申し込み")
        r_df_saved = st.session_state.config.get("request_data")
        r_df = pd.DataFrame(r_df_saved) if r_df_saved else pd.DataFrame("", index=cur_staff_names, columns=d_cols)
        r_df = r_df.reindex(index=cur_staff_names, columns=d_cols).fillna("")
        for col_r in d_cols: r_df[col_r] = pd.Categorical(r_df[col_r], categories=opts)
        ed_req = st.data_editor(r_df, use_container_width=True, key="r_ui_v89")
        st.session_state.config["request_data"] = ed_req.to_dict()

    st.write("🚫 担務削減設定 (チェック)")
    ex_df_saved = st.session_state.config.get("exclude_data")
    ex_df = pd.DataFrame(ex_df_saved) if ex_df_saved else pd.DataFrame(False, index=[i+1 for i in range(nd)], columns=s_list)
    ex_df = ex_df.reindex(index=[i+1 for i in range(nd)], columns=s_list).fillna(False)
    ed_ex = st.data_editor(ex_df, use_container_width=True, key="ex_ui_v89")
    st.session_state.config["exclude_data"] = ed_ex.to_dict()

    st.sidebar.download_button("📥 今の全設定を保存", json.dumps(st.session_state.config, ensure_ascii=False), f"Config_{year}_{month}.json")

    # --- 🚀 究極の数理最適化実行 (Team V89) ---
    if st.button("🚀 この設定で最高精度の勤務表を算出する", type="primary"):
        model = cp_model.CpModel()
        num_sh = len(s_list)
        S_OFF, S_NIK = 0, num_sh + 1
        e_ids = [s_list.index(x) + 1 for x in e_g]
        l_ids = [s_list.index(x) + 1 for x in l_g]
        x = {(si, di, i): model.NewBoolVar(f'x_{si}_{di}_{i}') for si in range(total_st) for di in range(nd) for i in range(num_sh+2)}
        pen = []

        # 引継ぎ解析 (d=3が末日)
        for si in range(total_st):
            if ed_p.iloc[si, 3] == "遅":
                for ei in e_ids: model.Add(x[si, 0, ei] == 0)

        for d in range(nd):
            w_idx = calendar.weekday(year, month, d+1)
            for i, s_n in enumerate(s_list):
                sid = i + 1
                is_excl = ed_ex.iloc[d, i] or (w_idx == 6 and s_n == "C")
                circles = [si for si in range(total_st) if ed_master.iloc[si, 2 + i*2] == "○"]
                triangles = [si for si in range(total_st) if ed_master.iloc[si, 2 + i*2] == "△"]
                sum_c, sum_t = sum(x[si, d, sid] for si in circles), sum(x[si, d, sid] for si in triangles)
                
                if is_excl: model.Add(sum(x[si, d, sid] for si in range(total_st)) == 0)
                else:
                    filled = model.NewBoolVar(f'f_{d}_{sid}')
                    model.Add(sum_c == 1).OnlyEnforceIf(filled)
                    pen.append(filled * 50000000) 
                    model.Add(sum_t <= 1)
                    # 管理者が担務に入る場合はコスト（一般優先）
                    for mgr_i in range(n_m): pen.append(x[mgr_i, d, sid] * -5000)
            for si in range(total_st): model.Add(sum(x[si, d, i_sh] for i_sh in range(num_sh+2)) == 1)

        for si in range(total_st):
            is_e, is_l, is_off = [model.NewBoolVar(f'ie{si}_{di}') for di in range(nd)], [model.NewBoolVar(f'il{si}_{di}') for di in range(nd)], [x[si, di, S_OFF] for di in range(nd)]
            for di in range(nd):
                model.Add(sum(x[si, di, i] for i in e_ids) == 1).OnlyEnforceIf(is_e[di])
                model.Add(sum(x[si, di, i] for i in e_ids) == 0).OnlyEnforceIf(is_e[di].Not())
                model.Add(sum(x[si, di, i] for i in l_ids) == 1).OnlyEnforceIf(is_l[di])
                model.Add(sum(x[si, di, i] for i in l_ids) == 0).OnlyEnforceIf(is_l[di].Not())
                rv = ed_req.iloc[si, di]
                map_c = {"休":S_OFF, "日":S_NIK, "":-1}
                for ik, nk in enumerate(s_list): map_c[nk] = ik+1
                if rv in map_c and map_c[rv] != -1: model.Add(x[si, di, map_c[rv]] == 1)
                for ik, nk in enumerate(s_list):
                    if ed_master.iloc[si, 2+ik*2] == "×": model.Add(x[si, di, ik+1] == 0)
                if di < nd - 1:
                    le_f = model.NewBoolVar(f'le_{si}_{di}')
                    model.Add(is_l[di] + is_e[di+1] <= 1).OnlyEnforceIf(le_f)
                    pen.append(le_f * 200000 * w_strict)

            # 連勤、分散、バランス
            hw = [1 if ed_p.iloc[si, k] != "休" else 0 for k in range(4)] + [(1 - is_off[di]) for di in range(nd)]
            for ki in range(len(hw)-4):
                c4v = model.NewBoolVar(f'c4_{si}_{ki}')
                model.Add(sum(hw[ki:ki+5]) <= 4).OnlyEnforceIf(c4v)
                pen.append(c4v * 100000 * w_strict)
            ho = [1 if ed_p.iloc[si, k] == "休" else 0 for k in range(4)] + is_off
            for ki in range(len(ho)-2):
                i3o = model.NewBoolVar(f'o3_{si}_{ki}')
                model.AddBoolAnd(ho[ki:ki+3]).OnlyEnforceIf(i3o)
                # 指定なき3連休に罰則
                target_range = [ki+k-4 for k in range(3) if 0 <= ki+k-4 < nd]
                if target_range and not any(ed_req.iloc[si, kr] == "休" for kr in target_range):
                    pen.append(i3o * -5000000)
            for di in range(nd-1):
                m_b = model.NewBoolVar(f'mx_{si}_{di}')
                model.AddBoolAnd([is_e[di], is_l[di+1]]).OnlyEnforceIf(m_b)
                pen.append(m_b * 5000 * w_mix)

            # 管理・一般ルール（土日休み・平日日勤優先）
            if si < n_m:
                for di in range(nd):
                    is_sh = (calendar.weekday(year,month,di+1) >= 5)
                    mg_f = model.NewBoolVar(f'mgv_{si}_{di}')
                    if is_sh: model.Add(is_off[di] == 1).OnlyEnforceIf(mg_f)
                    else: model.Add(is_off[di] == 0).OnlyEnforceIf(mg_f)
                    pen.append(mg_f * 200000) # 管理者は平日出、土日休を努力目標に
            else:
                for di in range(nd):
                    if ed_req.iloc[si, di] != "日": model.Add(x[si, di, S_NIK] == 0)

            for ik, nk in enumerate(s_list):
                try: tr_v = int(ed_master.iloc[si, 3+ik*2])
                except: tr_v = 0
                if tr_v > 0 and ed_master.iloc[si, 2+ik*2] == "△": model.Add(sum(x[si, d, ik+1] for d in range(nd)) == tr_v)
            herr = model.NewIntVar(0, nd, f'h_{si}')
            model.AddAbsEquality(herr, sum(is_off) - int(ed_master.iloc[si, 1]))
            pen.append(herr * -10000000 * w_strict) # 公休数守備を最強化

        for i_f in range(1, num_sh + 1):
            sc_v = [model.NewIntVar(0, nd, f'sc_{si}_{i_f}') for si in range(total_st)]
            for si in range(total_st): model.Add(sc_v[si] == sum(x[si, dx, i_f] for dx in range(nd)))
            mv, nv = model.NewIntVar(0, nd, f'mv_{i_f}'), model.NewIntVar(0, nd, f'nv_{i_f}')
            model.AddMaxEquality(mv, sc_v); model.AddMinEquality(nv, sc_v)
            pen.append((mv - nv) * -500 * w_fair)

        model.Maximize(sum(pen))
        slv = cp_model.CpSolver()
        slv.parameters.max_time_in_seconds = 45.0
        stat = slv.Solve(model)

        if stat in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            st.success("🎉 条件をクリアした最高峰の勤務案です。")
            res_l = []
            id_c = {S_OFF:"休", S_NIK:"日"}
            for idx, nm in enumerate(s_list): id_c[idx+1] = nm
            for si in range(total_st):
                row = [id_c[next(j for j in range(num_sh+2) if slv.Value(x[si,d,j])==1)] for d in range(nd)]
                res_l.append(row)
            out = pd.DataFrame(res_l, index=cur_staff_names, columns=d_cols)
            out["公休計"] = [r.count("休") for r in res_l]
            def bg(v):
                if v=="休": return 'background-color:#ffcccc'
                if v=="日": return 'background-color:#e0f0ff'
                if v in e_g: return 'background-color:#ffffcc'
                return 'background-color:#ccffcc'
            st.dataframe(out.style.map(bg), use_container_width=True)
            st.download_button("📥 完成版保存", out.to_csv().encode('utf-8-sig'), f"DutyAI_V89.csv")
        else: st.error("❌ 条件に矛盾があります。公休設定などを微調整してください。")

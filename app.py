import streamlit as st
import pandas as pd
import calendar
import json
from ortools.sat.python import cp_model

# ========================================================
# 🛡️ 究極の勤務作成エンジン V90 (Mathematical Perfection)
# ========================================================

# 1. ページ構成（リロード耐性のための最速実行）
st.set_page_config(page_title="究極勤務AI V90", page_icon="🛡️", layout="wide")

# 2. セッションの完全初期化（二重入力を防ぐ不動の設計）
if 'master' not in st.session_state:
    st.session_state.master = pd.DataFrame({
        "名前": [f"スタッフ{i+1}" for i in range(10)],
        "公休数": [9] * 10,
        "Aスキル": ["○"] * 10, "Bスキル": ["○"] * 10, "Cスキル": ["○"] * 10,
        "Dスキル": ["○"] * 10, "Eスキル": ["○"] * 10,
        "A回数": [0] * 10, "B回数": [0] * 10, "C回数": [0] * 10, "D回数": [0] * 10, "E回数": [0] * 10
    })

if 'prev' not in st.session_state:
    st.session_state.prev = pd.DataFrame("休", index=range(10), columns=["4日前", "3日前", "2日前", "末日"])

if 'config' not in st.session_state:
    st.session_state.config = {"year": 2025, "month": 1, "raw_s": "A,B,C,D,E", "early": ["A","B","C"], "late": ["D","E"]}

st.title("🛡️ 究極の勤務作成エンジン V90 (Total Reliability)")

# --- サイドバー：全管理 ---
with st.sidebar:
    st.header("💾 設定の保存と復元")
    up_file = st.file_uploader("設定読込", type="json")
    if up_file:
        try:
            load = json.load(up_file)
            st.session_state.master = pd.DataFrame(load["master"])
            st.session_state.prev = pd.DataFrame(load["prev"])
            st.session_state.config.update(load["config"])
            st.success("全ての変数を同期しました。")
            st.rerun()
        except: st.error("不正なファイルです。")

    st.divider()
    st.header("🎯 解析優先戦略")
    w_strict = st.slider("ルールの厳格度", 0, 100, 95)
    w_mix = st.slider("リズム (早遅混合)", 0, 100, 75)
    w_fair = st.slider("担務公平性 (回数)", 0, 100, 50)

    st.divider()
    year = int(st.number_input("年", 2024, 2030, st.session_state.config["year"]))
    month = int(st.number_input("月", 1, 12, st.session_state.config["month"]))
    st.session_state.config["year"], st.session_state.config["month"] = year, month

# --- タブ分け ---
t1, t2 = st.tabs(["🏗️ 名簿・スキル設定", "🧬 勤務指定・AI作成"])

with t1:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("👥 人数構成")
        num_m = st.number_input("管理者の人数", 0, 5, 2)
        num_r = st.number_input("一般職の人数", 1, 20, 8)
        total_staff = num_m + num_r
    with c2:
        st.subheader("📋 シフト構成")
        raw_sh = st.text_input("勤務略称 (,) 区切り", st.session_state.config["raw_s"])
        s_list = [s.strip() for s in raw_sh.split(",") if s.strip()]
        e_gr = st.multiselect("早番グループ", s_list, default=[x for x in s_list if x in st.session_state.config["early"]])
        l_gr = st.multiselect("遅番グループ", s_list, default=[x for x in s_list if x in st.session_state.config["late"]])
        st.session_state.config.update({"raw_s": raw_sh, "early": e_gr, "late": l_gr})

    st.divider()
    st.subheader("👤 スタッフ詳細マスタ (名前・公休・習熟度)")
    
    # 安定版DataFrameビルド
    m_df = st.session_state.master.reindex(range(total_staff)).fillna(method='ffill').fillna(0)
    for i in range(total_staff):
        if m_df.at[i, "名前"] == 0 or not m_df.at[i, "名前"]: m_df.at[i, "名前"] = f"スタッフ{i+1}"
    
    # スキル列の強制カテゴリ化
    for s_name in s_list:
        sk_col = f"{s_name}スキル"
        if sk_col not in m_df.columns: m_df[sk_col] = "○"
        if f"{s_name}回数" not in m_df.columns: m_df[f"{s_name}回数"] = 0
        m_df[sk_col] = pd.Categorical(m_df[sk_col], categories=["○", "△", "×"])

    # ここが解決の核：データエディタの結果をその場でsession_stateに上書き
    ed_master = st.data_editor(m_df, use_container_width=True, key="m_editor_v90")
    st.session_state.master = ed_master
    staff_names_list = ed_master["名前"].tolist()

with t2:
    _, nd = calendar.monthrange(year, month)
    ja_w = ["月","火","水","木","金","土","日"]
    d_cols = [f"{i+1}({ja_w[calendar.weekday(year,month,i+1)]})" for i in range(nd)]
    opts = ["", "休", "日"] + s_list

    st.subheader("🗓️ 打ち込み・AI作成実行")
    cp, cr = st.columns([1, 3.2])
    with cp:
        st.write("引継(直近4日)")
        p_df = st.session_state.prev.reindex(range(total_staff)).fillna("休")
        p_df.index = staff_names_list
        for col_p in p_df.columns: p_df[col_p] = pd.Categorical(p_df[col_p], categories=["日", "休", "早", "遅"])
        ed_p = st.data_editor(p_df, use_container_width=True, key="p_editor_v90")
        st.session_state.prev = ed_p.reset_index(drop=True)

    with cr:
        st.write("固定指定・休み申し込み")
        if 'req' not in st.session_state or st.session_state.req.shape[1] != nd:
            st.session_state.req = pd.DataFrame("", index=range(total_staff), columns=d_cols)
        
        r_df = st.session_state.req.reindex(range(total_staff)).fillna("")
        r_df.index = staff_names_list
        for col_r in r_df.columns: r_df[col_r] = pd.Categorical(r_df[col_r], categories=opts)
        ed_r = st.data_editor(r_df, use_container_width=True, key="r_editor_v90")
        st.session_state.req = ed_r.reset_index(drop=True)

    st.write("不要設定 (祝日Cなど)")
    if 'ex' not in st.session_state: st.session_state.ex = pd.DataFrame(False, index=[i+1 for i in range(nd)], columns=s_list)
    ed_ex = st.data_editor(st.session_state.ex.reindex(index=[i+1 for i in range(nd)], columns=s_list).fillna(False), use_container_width=True, key="x_editor_v90")
    st.session_state.ex = ed_ex

    total_data_backup = {"master": ed_master.to_dict(), "prev": st.session_state.prev.to_dict(), "config": st.session_state.config}
    st.sidebar.download_button("📥 今の全てを保存", json.dumps(total_data_backup, ensure_ascii=False), "My_Schedule_Settings.json")

    # --- 🚀 究極の数理最適化実行 (Absolute Final Engine) ---
    if st.button("🚀 この条件で最高精度の勤務表を算出", type="primary"):
        model = cp_model.CpModel()
        S_OFF, S_NIK = 0, len(s_list) + 1
        E_IDS = [s_list.index(x) + 1 for x in e_gr]
        L_IDS = [s_list.index(x) + 1 for x in l_gr]
        x = {(si, di, i): model.NewBoolVar(f'v_{si}_{di}_{i}') for si in range(total_staff) for di in range(nd) for i in range(len(s_list)+2)}
        pen = []

        # 月またぎ判定
        for si in range(total_staff):
            if ed_p.iloc[si, 3] == "遅":
                for ei in E_IDS: model.Add(x[si, 0, ei] == 0)

        # 担務充足・スキル
        for d in range(nd):
            w_idx = calendar.weekday(year, month, d+1)
            for i, s_n in enumerate(s_list):
                sid = i + 1
                is_excl = ed_ex.iloc[d, i] or (w_idx == 6 and s_n == "C")
                circles = [si for si in range(total_staff) if ed_master.iloc[si, 2 + i*2] == "○"]
                triangles = [si for si in range(total_staff) if ed_master.iloc[si, 2 + i*2] == "△"]
                sum_c = sum(x[si, d, sid] for si in circles)
                sum_t = sum(x[si, d, sid] for si in triangles)
                
                if is_excl: model.Add(sum(x[si, d, sid] for si in range(total_staff)) == 0)
                else:
                    filled = model.NewBoolVar(f'f_{d}_{sid}')
                    model.Add(sum_c == 1).OnlyEnforceIf(filled)
                    pen.append(filled * 100000000) 
                    model.Add(sum_t <= 1)
                    for mgr_i in range(num_m): pen.append(x[mgr_i, d, sid] * -1000)
            for si in range(total_staff): model.Add(sum(x[si, d, i_sh] for i_sh in range(len(s_list)+2)) == 1)

        # 各個人のルール
        for si in range(total_staff):
            is_e, is_l, is_off = [model.NewBoolVar(f'ie{si}_{di}') for di in range(nd)], [model.NewBoolVar(f'il{si}_{di}') for di in range(nd)], [x[si, di, S_OFF] for di in range(nd)]
            for di in range(nd):
                model.Add(sum(x[si, di, i] for i in E_IDS) == 1).OnlyEnforceIf(is_e[di])
                model.Add(sum(x[si, di, i] for i in E_IDS) == 0).OnlyEnforceIf(is_e[di].Not())
                model.Add(sum(x[si, di, i] for i in L_IDS) == 1).OnlyEnforceIf(is_l[di])
                model.Add(sum(x[si, di, i] for i in L_IDS) == 0).OnlyEnforceIf(is_l[di].Not())
                # 指定反映
                rv = ed_r.iloc[si, di]
                m_c = {"休":S_OFF, "日":S_NIK, "":-1}
                for ik, nk in enumerate(s_list): m_c[nk] = ik+1
                if rv in m_c and m_c[rv] != -1: model.Add(x[si, di, m_c[rv]] == 1)
                # 禁止シフト
                for ik, nk in enumerate(s_list):
                    if ed_master.iloc[si, 2+ik*2] == "×": model.Add(x[si, di, ik+1] == 0)
                if di < nd - 1:
                    le_f = model.NewBoolVar(f'le_{si}_{di}')
                    model.Add(is_l[di] + is_e[di+1] <= 1).OnlyEnforceIf(le_f)
                    pen.append(le_f * 500000 * w_strict)

            # 4連勤・3連休抑制・リズム
            hw = [1 if ed_p.iloc[si, k] != "休" else 0 for k in range(4)] + [(1 - is_off[di]) for di in range(nd)]
            for ki in range(len(hw)-4):
                c4v = model.NewBoolVar(f'c4_{si}_{ki}')
                model.Add(sum(hw[ki:ki+5]) <= 4).OnlyEnforceIf(c4v)
                pen.append(c4v * 200000 * w_strict)
            ho = [1 if ed_p.iloc[si, k] == "休" else 0 for k in range(4)] + is_off
            for ki in range(len(ho)-2):
                i3o = model.NewBoolVar(f'o3_{si}_{ki}')
                model.AddBoolAnd(ho[ki:ki+3]).OnlyEnforceIf(i3o)
                c_range = [ki+k-4 for k in range(3) if 0 <= ki+k-4 < nd]
                if c_range and not any(ed_r.iloc[si, kr] == "休" for kr in c_range):
                    pen.append(i3o * -5000000)
            for di in range(nd-1):
                m_b = model.NewBoolVar(f'mx_{si}_{di}')
                model.AddBoolAnd([is_e[di], is_l[di+1]]).OnlyEnforceIf(m_b)
                pen.append(m_b * 5000 * w_mix)

            # 管理・一般職権限
            if si < num_m:
                for di in range(nd):
                    is_ss = (calendar.weekday(year,month,di+1) >= 5)
                    mg_f = model.NewBoolVar(f'mgv_{si}_{di}')
                    if is_ss: model.Add(is_off[di] == 1).OnlyEnforceIf(mg_f)
                    else: model.Add(is_off[di] == 0).OnlyEnforceIf(mg_f)
                    pen.append(mg_f * 2000000) # 土日休みをさらに強化
            else:
                for di in range(nd):
                    if ed_r.iloc[si, di] != "日": model.Add(x[si, di, S_NIK] == 0)

            # 教育・公休
            for ik, nk in enumerate(s_list):
                try: tr_v = int(ed_master.iloc[si, 3+ik*2])
                except: tr_v = 0
                if tr_v > 0 and ed_master.iloc[si, 2+ik*2] == "△": model.Add(sum(x[si, d, ik+1] for d in range(nd)) == tr_v)
            herr = model.NewIntVar(0, nd, f'h_{si}')
            model.AddAbsEquality(herr, sum(is_off) - int(ed_master.iloc[si, 1]))
            pen.append(herr * -10000000 * w_strict)

        # 平準化
        for i_f in range(1, num_sh := len(s_list) + 1):
            sc_v = [model.NewIntVar(0, nd, f'sc_{si}_{i_f}') for si in range(total_staff)]
            for si in range(total_staff): model.Add(sc_v[si] == sum(x[si, dx, i_f] for dx in range(nd)))
            mv, nv = model.NewIntVar(0, nd, f'mv_{i_f}'), model.NewIntVar(0, nd, f'nv_{i_f}')
            model.AddMaxEquality(mv, sc_v); model.AddMinEquality(nv, sc_v)
            pen.append((mv - nv) * -1000 * w_fair)

        model.Maximize(sum(pen))
        slv = cp_model.CpSolver()
        slv.parameters.max_time_in_seconds = 45.0
        status = slv.Solve(model)

        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            st.success("✨ 成功。最高品質の勤務表を抽出しました。")
            res_rows = []
            id_c = {S_OFF:"休", S_NIK:"日"}
            for i, n in enumerate(s_list): id_c[i+1] = n
            for si in range(total_staff):
                res_rows.append([id_c[next(j for j in range(len(s_list)+2) if slv.Value(x[si,d,j])==1)] for d in range(nd)])
            out = pd.DataFrame(res_rows, index=staff_names_list, columns=d_cols)
            out["公休計"] = [r.count("休") for r in res_rows]
            st.dataframe(out.style.map(lambda v: 'background-color:#ffcccc' if v=="休" else ('background-color:#e0f0ff' if v=="日" else ('background-color:#ffffcc' if v in e_gr else 'background-color:#ccffcc'))), use_container_width=True)
            st.download_button("📥 保存(CSV)", out.to_csv().encode('utf-8-sig'), f"AI_Duty_{year}_{month}.csv")
        else: st.error("❌ 条件が競合しました。公休数などを調整してください。")

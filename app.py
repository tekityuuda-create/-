import streamlit as st
import pandas as pd
import calendar
import json
from ortools.sat.python import cp_model

# ========================================================
# 🛡️ 究極の勤務作成エンジン V87 (Supreme Integration Edition)
# ========================================================

st.set_page_config(page_title="AI勤務作成 V87", page_icon="🛡️", layout="wide")

# 1. セッション情報の完全初期化（二重入力・データ消失を根底から防止）
if 'config' not in st.session_state:
    st.session_state.config = {
        "num_mgr": 2, "num_regular": 8,
        "staff_names": [f"スタッフ{i+1}" for i in range(10)],
        "user_shifts": "A,B,C,D,E", "early_shifts": ["A", "B", "C"], "late_shifts": ["D", "E"],
        "year": 2025, "month": 1,
        "master_data": None, "prev_data": None, "request_data": None, "exclude_data": None
    }

st.title("🛡️ 究極の勤務作成エンジン V87 (Supreme Stability)")

# --- サイドバー：全データ管理 ---
with st.sidebar:
    st.header("💾 データバックアップ")
    up_file = st.file_uploader("設定ファイルを読込(.json)", type="json")
    if up_file:
        try:
            st.session_state.config.update(json.load(up_file))
            st.success("全ての変数を同期しました。")
            st.rerun()
        except: st.error("不正なファイル形式です。")

    st.divider()
    st.header("🎯 AI解析優先度")
    w_strictness = st.slider("ルールの厳格度", 0, 100, 95)
    w_rhythm = st.slider("リズム (早遅の混合)", 0, 100, 75)
    w_fairness = st.slider("公平性 (回数均等化)", 0, 100, 50)

    st.divider()
    year = int(st.number_input("年", 2024, 2030, st.session_state.config["year"]))
    month = int(st.number_input("月", 1, 12, st.session_state.config["month"]))
    st.session_state.config["year"], st.session_state.config["month"] = year, month

# --- 2. タブ設計 ---
t1, t2 = st.tabs(["🏗️ 1. 名簿・スキル・教育設定", "🧬 2. 勤務表の作成・実行"])

with t1:
    col_l, col_r = st.columns(2)
    with col_l:
        st.subheader("👥 人員と勤務グループ")
        nm_m = st.number_input("管理者の人数 (上からN名)", 0, 5, st.session_state.config["num_mgr"])
        nm_r = st.number_input("一般職の人数", 1, 20, st.session_state.config["num_regular"])
        st.session_state.config["num_mgr"], st.session_state.config["num_regular"] = nm_m, nm_r
        total = nm_m + nm_r

        raw_sh = st.text_input("勤務略称 (,) 区切り", st.session_state.config["user_shifts"])
        s_list = [s.strip() for s in raw_sh.split(",") if s.strip()]
        st.session_state.config["user_shifts"] = raw_sh
    with col_r:
        st.subheader("🕑 リズム分類")
        e_gr = st.multiselect("早番グループ", s_list, default=[x for x in s_list if x in st.session_state.config["early_shifts"]])
        l_gr = st.multiselect("遅番グループ", s_list, default=[x for x in s_list if x in st.session_state.config["late_shifts"]])
        st.session_state.config["early_shifts"], st.session_state.config["late_shifts"] = e_gr, l_gr

    st.divider()
    st.subheader("👤 統合スタッフマスタ (名前・公休・スキル・見習い回数)")
    st.write("○:単独可, △:見習い, ×:不可 / 『回数』は今月の見習い実施目標数")

    # マスタ表の構築
    m_cols = ["名前", "公休数"]
    for s in s_list: m_cols.append(f"{s}スキル"); m_cols.append(f"{s}回数")
    
    if st.session_state.config.get("master_data") is None:
        m_df = pd.DataFrame("", index=range(total), columns=m_cols)
        m_df["名前"] = [f"スタッフ{i+1}" for i in range(total)]
        m_df["公休数"] = 9
        for s in s_list: m_df[f"{s}スキル"], m_df[f"{s}回数"] = "○", 0
    else:
        m_df = pd.DataFrame(st.session_state.config["master_data"]).reindex(range(total)).fillna(method='ffill')

    # プルダウンを強制定義
    for s in s_list:
        m_df[f"{s}スキル"] = pd.Categorical(m_df[f"{s}スキル"], categories=["○", "△", "×"])
    
    ed_master = st.data_editor(m_df, use_container_width=True, key="master_editor_persistent")
    st.session_state.config["master_data"] = ed_master.to_dict() # メモリ即時セーブ
    staff_list = ed_master["名前"].tolist()

with t2:
    _, num_d = calendar.monthrange(year, month)
    ja_w = ["月","火","水","木","金","土","日"]
    d_cols = [f"{i+1}({ja_w[calendar.weekday(year,month,i+1)]})" for i in range(num_d)]
    opts = ["", "休", "日"] + s_list

    c1, c2 = st.columns([1, 3])
    with c1:
        st.write("⏮️ 前月引継ぎ (4日間)")
        p_df = pd.DataFrame(st.session_state.config["prev_data"]) if st.session_state.config.get("prev_data") else pd.DataFrame("休", index=staff_list, columns=["4日前","3日前","2日前","末日"])
        p_df = p_df.reindex(index=staff_list).fillna("休")
        for c in p_df.columns: p_df[c] = pd.Categorical(p_df[c], categories=["日", "休", "早", "遅"])
        ed_p = st.data_editor(p_df, use_container_width=True, key="p_ui")
        st.session_state.config["prev_data"] = ed_p.to_dict()

    with c2:
        st.write("📝 今月の固定指定 (申し込み)")
        r_df = pd.DataFrame(st.session_state.config["request_data"]) if st.session_state.config.get("request_data") else pd.DataFrame("", index=staff_list, columns=d_cols)
        r_df = r_df.reindex(index=staff_list, columns=d_cols).fillna("")
        for c in r_df.columns: r_df[c] = pd.Categorical(r_df[c], categories=opts)
        ed_r = st.data_editor(r_df, use_container_width=True, key="r_ui")
        st.session_state.config["request_data"] = ed_r.to_dict()

    st.write("🚫 不要担務の設定")
    x_df = pd.DataFrame(st.session_state.config["exclude_data"]) if st.session_state.config.get("exclude_data") else pd.DataFrame(False, index=[i+1 for i in range(num_d)], columns=s_list)
    x_df = x_df.reindex(columns=s_list).fillna(False)
    ed_x = st.data_editor(x_df, use_container_width=True, key="x_ui")
    st.session_state.config["exclude_data"] = ed_x.to_dict()

    st.sidebar.download_button("📥 今の設定をファイル保存", json.dumps(st.session_state.config, ensure_ascii=False), "AI_Duty_Backup.json")

    # --- 🚀 究極の数理最適化 (Final Solver Core) ---
    if st.button("🚀 この設定で最高峰の勤務表を生成", type="primary"):
        model = cp_model.CpModel()
        S_OFF, S_NIK = 0, len(s_list) + 1
        e_ids = [s_list.index(x) + 1 for x in e_gr]
        l_ids = [s_list.index(x) + 1 for x in l_gr]
        
        # 変数 x[スタッフ, 日, シフト]
        x_v = {(si, di, i): model.NewBoolVar(f'x_{si}_{di}_{i}') for si in range(total) for di in range(num_d) for i in range(len(s_list)+2)}
        obj = []

        # A. 担務充足・スキル・見習い
        for d in range(num_d):
            wday = calendar.weekday(year, month, d+1)
            for i, s_n in enumerate(s_list):
                sid = i + 1
                is_excl = ed_x.iloc[d, i] or (wday == 6 and s_n == "C")
                skilled_ids = [si for si in range(total) if ed_master.iloc[si, 2 + i*2] == "○"]
                trainee_ids = [si for si in range(total) if ed_master.iloc[si, 2 + i*2] == "△"]
                
                sum_s = sum(x_v[si, d, sid] for si in skilled_ids)
                sum_t = sum(x_v[si, d, sid] for si in trainee_ids)
                
                if is_excl: model.Add(sum(x_v[si, d, sid] for si in range(total)) == 0)
                else:
                    filled = model.NewBoolVar(f'fill_{d}_{sid}')
                    model.Add(sum_s == 1).OnlyEnforceIf(filled)
                    obj.append(filled * 10000000) # 絶対目標
                    model.Add(sum_t <= 1) # 見習い配置
            # 1日1回
            for si in range(total): model.Add(sum(x_v[si, d, shift_i] for shift_id in range(len(s_list)+2)) == 1)

        # B. 個人ルール
        for si in range(total):
            f_e = [model.NewBoolVar(f'f_e_{si}_{di}') for di in range(num_d)]
            f_l = [model.NewBoolVar(f'f_l_{si}_{di}') for di in range(num_d)]
            f_off = [x_v[si, di, S_OFF] for di in range(num_d)]
            
            for di in range(num_d):
                # 判定用フラグ接続
                model.Add(sum(x_v[si, di, i] for i in e_ids) == 1).OnlyEnforceIf(f_early := f_e[di])
                model.Add(sum(x_v[si, di, i] for i in e_ids) == 0).OnlyEnforceIf(f_early.Not())
                model.Add(sum(x_v[si, di, i] for i in l_ids) == 1).OnlyEnforceIf(f_late := f_l[di])
                model.Add(sum(x_v[si, di, i] for i in l_ids) == 0).OnlyEnforceIf(f_late.Not())

                req_v = ed_r.iloc[si, di]
                c_mp = {"休":S_OFF, "日":S_NIK, "": -1}
                for i_s, n_s in enumerate(s_list): c_mp[n_s] = i_s + 1
                if req_v in c_mp and c_mp[req_v] != -1: model.Add(x_v[si, di, c_mp[req_v]] == 1)

                # スキル不可(×)
                for i_s, n_s in enumerate(s_list):
                    if ed_master.iloc[si, 2 + i_s*2] == "×": model.Add(x_v[si, di, i_s + 1] == 0)

                # 遅早
                if di < num_d - 1:
                    ok_le = model.NewBoolVar(f'le_{si}_{di}')
                    model.Add(f_late + f_e[di+1] <= 1).OnlyEnforceIf(ok_le)
                    obj.append(ok_le * 20000 * w_strictness)
                if di == 0 and (ed_p.iloc[si, 3] == "遅" or ed_p.iloc[si, 3] in l_gr): model.Add(f_e[0] == 0)

            # 連勤制限
            hst_w = [1 if ed_p.iloc[si, k] != "休" else 0 for k in range(4)] + [(1 - f_off[di]) for di in range(num_d)]
            for sk in range(len(hst_w)-4):
                c4v = model.NewBoolVar(f'c4_{si}_{sk}')
                model.Add(sum(hst_w[sk:sk+5]) <= 4).OnlyEnforceIf(c4v)
                obj.append(c4v * 10000 * w_strictness)

            # ミキシング
            for di in range(num_d - 1):
                mx_b = model.NewBoolVar(f'mxb_{si}_{di}')
                model.AddBoolAnd([f_e[di], f_l[di+1]]).OnlyEnforceIf(mx_b)
                obj.append(mx_b * 1000 * w_rhythm)

            # 管理・一般
            if si < nm_m:
                for di in range(num_d):
                    wday_v = calendar.weekday(year, month, di+1)
                    mg_f = model.NewBoolVar(f'mg_{si}_{di}')
                    if wday_v >= 5: model.Add(f_off[di] == 1).OnlyEnforceIf(mg_f)
                    else: model.Add(f_off[di] == 0).OnlyEnforceIf(mg_f)
                    obj.append(mg_f * 5000)
            else:
                for di in range(num_d):
                    if ed_r.iloc[si, di] != "日": model.Add(x_v[si, di, S_NIK] == 0)

            # 教育ノルマ死守
            for i, n_n in enumerate(s_list):
                try: count_goal = int(ed_master.iloc[si, 3 + i*2] or 0)
                except: count_goal = 0
                if count_goal > 0 and ed_master.iloc[si, 2 + i*2] == "△":
                    model.Add(sum(x_v[si, d, i+1] for d in range(num_d)) == count_goal)

            # 公休厳守 (B列)
            t_hol = int(ed_master.iloc[si, 1])
            err_var = model.NewIntVar(0, num_d, f'h_err_{si}')
            model.AddAbsEquality(err_var, sum(f_off) - t_hol)
            obj.append(err_var * -5000 * w_strictness)

        # C. 担務均等化 (公平性)
        for ishift in range(1, len(s_list)+1):
            counts = [model.NewIntVar(0, num_d, f'cnt_{ps}_{ishift}') for ps in range(total)]
            for ps in range(total): model.Add(counts[ps] == sum(x_v[ps, dx, ishift] for dx in range(num_d)))
            max_v, min_v = model.NewIntVar(0, num_d, f'mx_{ishift}'), model.NewIntVar(0, num_d, f'mn_{ishift}')
            model.AddMaxEquality(max_v, counts); model.AddMinEquality(min_v, counts)
            obj.append((max_v - min_v) * -500 * w_fairness)

        model.Maximize(sum(obj))
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 45.0
        status = solver.Solve(model)

        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            st.success("🎉 条件を充足しました。最高水準のバランスで出力します。")
            res_rows = []
            id_to_char = {S_OFF:"休", S_NIK:"日"}
            for i, n in enumerate(s_list): id_to_char[i+1] = n
            for si in range(total):
                res_rows.append([id_to_char[next(j for j in range(num_s_types+2) if solver.Value(x_v[si, d, j])==1)] for d in range(num_d)])
            out_df = pd.DataFrame(res_rows, index=staff_list, columns=d_cols)
            out_df["公休計"] = [row.count("休") for row in res_rows]
            def pnt(v):
                if v == "休": return 'background-color: #ffcccc'
                if v == "日": return 'background-color: #e0f0ff'
                if v in e_gr: return 'background-color: #ffffcc'
                return 'background-color: #ccffcc'
            st.dataframe(out_df.style.map(pnt), use_container_width=True)
            st.download_button("📥 完成したCSVを保存", out_df.to_csv().encode('utf-8-sig'), f"roster.csv")
        else: st.error("設定が競合しています。管理者の数や担務の削りを確認してください。")

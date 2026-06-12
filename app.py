import streamlit as st
import pandas as pd
import calendar
import json
from ortools.sat.python import cp_model

# --- 1. グローバルUI設定 ---
st.set_page_config(page_title="究極勤務AI：V82 Stable UI", page_icon="🛡️", layout="wide")

# セッションの初期化（二重入力防止用）
if 'config' not in st.session_state:
    st.session_state.config = {
        "num_mgr": 2, "num_regular": 8,
        "staff_names": [f"スタッフ{i+1}" for i in range(10)],
        "user_shifts": "A,B,C,D,E", "early_shifts": ["A", "B", "C"], "late_shifts": ["D", "E"],
        "year": 2025, "month": 1, "saved_tables": {}
    }

st.title("🛡️ 究極の勤務作成エンジン V82 (UI Persistence V82)")

# --- 2. サイドバー：データ管理と優先戦略 ---
with st.sidebar:
    st.header("💾 設定の読込・保存")
    up_file = st.file_uploader("設定ファイルを読み込む", type="json")
    if up_file:
        try:
            st.session_state.config.update(json.load(up_file))
            st.rerun() # リロードを一度だけ強制して全体に反映
        except: st.error("エラー：不適切なファイルです。")

    st.divider()
    st.header("🎯 AI解析の優先度")
    w_strictness = st.slider("ルールの厳格度", 0, 100, 95)
    w_rhythm = st.slider("早遅ミキシング (リズム)", 0, 100, 70)
    w_fairness = st.slider("担務の公平性 (回数)", 0, 100, 50)

    st.divider()
    year = int(st.number_input("年", 2024, 2030, st.session_state.config["year"]))
    month = int(st.number_input("月", 1, 12, st.session_state.config["month"]))
    # 更新があればsessionに反映
    st.session_state.config["year"] = year
    st.session_state.config["month"] = month

# --- 3. タブ設計 ---
tab_st, tab_skl, tab_roster = st.tabs(["🏗️ 1. 構成設定", "⚖️ 2. 公休・スキル設定", "🧬 3. 勤務作成実行"])

# --- 汎用関数: 保存/メモリからデータを読み出す（二重入力対策済み） ---
def get_safe_df(key, d_df, categories=None):
    tables = st.session_state.config.get("saved_tables", {})
    df = pd.DataFrame(tables.get(key)) if key in tables else d_df
    # indexとcolumnsを現在の設定に合わせて矯正
    df = df.reindex(index=d_df.index, columns=d_df.columns).fillna(d_df)
    if categories:
        for col in df.columns:
            df[col] = pd.Categorical(df[col], categories=categories)
    return df

with tab_st:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("👥 スタッフ設定")
        nm_mgr = st.number_input("管理者の数", 0, 5, st.session_state.config["num_mgr"])
        nm_reg = st.number_input("一般職の数", 1, 20, st.session_state.config["num_regular"])
        tot = int(nm_mgr + nm_reg)
        st.session_state.config["num_mgr"] = nm_mgr
        st.session_state.config["num_regular"] = nm_reg
        
        c_names = st.session_state.config.get("staff_names", [])
        if len(c_names) < tot: c_names.extend([f"スタッフ{i+1}" for i in range(len(c_names), tot)])
        staff_base = c_names[:tot]
        n_ed = st.data_editor(pd.DataFrame({"名前": staff_base}), use_container_width=True, key="name_edit_ui")
        staff_list = n_ed["名前"].tolist()
        st.session_state.config["staff_names"] = staff_list

    with c2:
        st.subheader("📋 勤務グループ")
        u_sh_raw = st.text_input("勤務略称 (,) 区切り", st.session_state.config["user_shifts"])
        st.session_state.config["user_shifts"] = u_sh_raw
        s_list = [s.strip() for s in u_sh_raw.split(",") if s.strip()]
        
        # マルチセレクトに現在値を紐づけてリロード耐性を持たせる
        e_gr = st.multiselect("早番グループ", s_list, default=[x for x in s_list if x in st.session_state.config["early_shifts"]], key="egr_ui")
        l_gr = st.multiselect("遅番グループ", s_list, default=[x for x in s_list if x in st.session_state.config["late_shifts"]], key="lgr_ui")
        st.session_state.config["early_shifts"] = e_gr
        st.session_state.config["late_shifts"] = l_gr

with tab_skl:
    st.subheader("⚖️ 公休数と担務適性")
    s_df = get_safe_df("skill", pd.DataFrame("○", index=staff_list, columns=s_list), ["○","△","×"])
    ed_skill = st.data_editor(s_df, use_container_width=True, key="skill_ui")
    
    col_cc1, col_c2 = st.columns(2)
    with col_cc1:
        h_df = get_safe_df("hols", pd.DataFrame(9, index=staff_list, columns=["公休数"]))
        ed_hols = st.data_editor(h_df, use_container_width=True, key="hols_ui")
    with col_c2:
        tr_cols = [f"{s}_回数" for s in s_list]
        t_df = get_safe_df("trainee", pd.DataFrame(0, index=staff_list, columns=tr_cols))
        ed_trainee = st.data_editor(t_df, use_container_width=True, key="tr_ui")

with tab_roster:
    _, n_days = calendar.monthrange(year, month)
    ja_wd = ["月","火","水","木","金","土","日"]
    days_cols = [f"{d+1}({ja_wd[calendar.weekday(year,month,d+1)]})" for d in range(n_days)]
    options = ["", "休", "日"] + s_list

    st.subheader("📝 引継ぎ状況 & 指定の入力")
    c_p, c_r = st.columns([1, 3])
    with c_p:
        p_df = get_safe_df("prev", pd.DataFrame("休", index=staff_list, columns=["4日前","3日前","2日前","末日"]), ["日","休","早","遅"])
        ed_prev = st.data_editor(p_df, use_container_width=True, key="prev_ui")
    with c_r:
        r_df = get_safe_df("request", pd.DataFrame("", index=staff_list, columns=days_cols), options)
        ed_req = st.data_editor(r_df, use_container_width=True, key="req_ui")

    ed_ex = st.data_editor(get_safe_df("exclude", pd.DataFrame(False, index=[d+1 for d in range(n_days)], columns=s_list)), use_container_width=True, key="excl_ui")

    # セッション/保存データ全パッキング
    st.session_state.config["saved_tables"] = {
        "skill": ed_skill.to_dict(), "hols": ed_hols.to_dict(), "trainee": ed_trainee.to_dict(),
        "prev": ed_prev.to_dict(), "request": ed_req.to_dict(), "exclude": ed_ex.to_dict()
    }
    st.sidebar.download_button("📥 今の設定をファイル保存", json.dumps(st.session_state.config, ensure_ascii=False), "勤務AI_config.json")

    # --- 最適化演算ロジック (V81 完全継承) ---
    if st.button("🚀 勤務表をAIで生成する (高速解析)", type="primary"):
        model = cp_model.CpModel()
        S_OFF, S_NIK = 0, len(s_list) + 1
        E_IDS = [s_list.index(x) + 1 for x in e_gr]
        L_IDS = [s_list.index(x) + 1 for x in l_gr]
        
        # [s, d, i] Boolean変数の配置
        x = {(si, di, i): model.NewBoolVar(f'x_{si}_{di}_{i}') for si in range(tot) for di in range(n_days) for i in range(len(s_list)+2)}
        score_objs = []

        # 月またぎ制約（末日遅番なら今月1日早番禁止）
        for si in range(tot):
            if ed_prev.iloc[si, 3] == "遅":
                for ei in E_IDS: model.Add(x[si, 0, ei] == 0)

        # 担務充足と制約の数理定義
        for di in range(n_days):
            wd_n = calendar.weekday(year, month, di+1)
            for i, s_name in enumerate(s_list):
                sid = i + 1
                is_excl = ed_ex.iloc[di, i] or (wd_n == 6 and s_name == "C")
                eligible_workers = [si for si in range(tot) if ed_skill.iloc[si, i] == "○"]
                trainees = [si for si in range(tot) if ed_skill.iloc[si, i] == "△"]
                
                sum_el = sum(x[si, di, sid] for si in eligible_workers)
                sum_tr = sum(x[si, di, sid] for si in trainees)
                
                if is_excl:
                    model.Add(sum(x[si, di, sid] for si in range(tot)) == 0)
                else:
                    filled_f = model.NewBoolVar(f'jf_{di}_{sid}')
                    model.Add(sum_el == 1).OnlyEnforceIf(filled_f)
                    score_objs.append(filled_f * 5000000) # 仕事最優先
                    model.Add(sum_tr <= 1)

            # 1人1日1回
            for si in range(tot): model.Add(sum(x[si, di, shift_i] for shift_i in range(len(s_list)+2)) == 1)

        # 各個人の働き方の質と公平性
        for si in range(tot):
            is_early_m = [model.NewBoolVar(f'ise_{si}_{di}') for di in range(n_days)]
            is_late_m = [model.NewBoolVar(f'isl_{si}_{di}') for di in range(n_days)]
            is_off_m = [x[si, di, S_OFF] for di in range(n_days)]
            
            for di in range(n_days):
                # フラグ変数を合計式と等価にする (TypeError防止)
                model.Add(sum(x[si, di, i] for i in E_IDS) == 1).OnlyEnforceIf(is_early_m[di])
                model.Add(sum(x[si, di, i] for i in E_IDS) == 0).OnlyEnforceIf(is_early_m[di].Not())
                model.Add(sum(x[si, di, i] for i in L_IDS) == 1).OnlyEnforceIf(is_late_m[di])
                model.Add(sum(x[si, di, i] for i in L_IDS) == 0).OnlyEnforceIf(is_late_m[di].Not())

                # 指定反映
                r_val = ed_req.iloc[si, di]
                r_id = {"休":S_OFF, "日":S_NIK}.get(r_val, s_list.index(r_val)+1 if r_val in s_list else -1)
                if r_id != -1: model.Add(x[si, di, r_id] == 1)

                if di < n_days - 1:
                    le_ok = model.NewBoolVar(f'le_{si}_{di}')
                    model.Add(is_late_m[di] + is_early_m[di+1] <= 1).OnlyEnforceIf(le_ok)
                    score_objs.append(le_ok * 20000 * w_strictness)

            # 連勤(4日まで)
            work_hist = [1 if ed_prev.iloc[si, k] != "休" else 0 for k in range(4)] + [(1 - is_off_m[di]) for di in range(n_days)]
            for start_k in range(len(work_hist) - 4):
                c4_f = model.NewBoolVar(f'c4_{si}_{start_k}')
                model.Add(sum(work_hist[start_k:start_k+5]) <= 4).OnlyEnforceIf(c4_f)
                score_objs.append(c4_f * 5000 * w_strictness)

            # 休みが孤立しないボーナス（単発休みではなく連休へ）よりも分散要望により3連休抑制
            off_hist = [1 if ed_prev.iloc[si, k] == "休" else 0 for k in range(4)] + is_off_m
            for sk in range(len(off_hist) - 2):
                is3o = model.NewBoolVar(f'o3_{si}_{sk}')
                model.AddBoolAnd(off_hist[sk:sk+3]).OnlyEnforceIf(is3o)
                # 意図しない3連休は強く回避
                curr_days = [sk+k-4 for k in range(3) if 0 <= sk+k-4 < n_days]
                if curr_days and not any(ed_req.iloc[si, idx_k] == "休" for idx_k in curr_days):
                    score_objs.append(is3o * -50000)

            # リズム：早→遅ミックスへのボーナス
            for di in range(n_days - 1):
                mxb = model.NewBoolVar(f'mx_{si}_{di}')
                model.AddBoolAnd([is_early_m[di], is_late_m[di+1]]).OnlyEnforceIf(mxb)
                score_objs.append(mxb * 1000 * w_rhythm)

            # 雇用区分管理
            if si < nm_mgr:
                for di in range(n_days):
                    is_mgr_v = model.NewBoolVar(f'mgo_{si}_{di}')
                    is_shol = (calendar.weekday(year, month, di+1) >= 5)
                    if is_shol: model.Add(is_off_m[di] == 1).OnlyEnforceIf(is_mgr_v)
                    else: model.Add(is_off_m[di] == 0).OnlyEnforceIf(is_mgr_v)
                    score_objs.append(is_mgr_v * 1000)
            else:
                for di in range(n_days):
                    if ed_req.iloc[si, di] != "日": model.Add(x[si, di, S_NIK] == 0)

            # 公休厳守 (B列の死守)
            t_hol = int(ed_hols.iloc[si, 0])
            err_var = model.NewIntVar(0, n_days, f'h_err_{si}')
            model.AddAbsEquality(err_var, sum(is_off_m) - t_hol)
            score_objs.append(err_var * -5000 * w_strictness)

        # 担務配分の均一化
        for shift_id_fair in range(1, len(s_list)+1):
            staff_cs = [model.NewIntVar(0, n_days, f'c{p_si}_{shift_id_fair}') for p_si in range(tot)]
            for p_si in range(tot): model.Add(staff_cs[p_si] == sum(x[p_si, d_fair, shift_id_fair] for d_fair in range(n_days)))
            mx_v, mi_v = model.NewIntVar(0, n_days, f'mx_{shift_id_fair}'), model.NewIntVar(0, n_days, f'mi_{shift_id_fair}')
            model.AddMaxEquality(mx_v, staff_cs); model.AddMinEquality(mi_v, staff_cs)
            score_objs.append((mx_v - mi_v) * -500 * w_fairness)

        model.Maximize(sum(score_objs))
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 45.0
        status = solver.Solve(model)

        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            st.success("🎉 条件を充足しました。最高水準のバランスで出力します。")
            res_rows = []
            id_to_char = {S_OFF:"休", S_NIK:"日"}
            for i, n in enumerate(s_list): id_to_char[i+1] = n
            for si in range(tot):
                res_rows.append([id_to_char[next(j for j in range(len(s_list)+2) if solver.Value(x[si, di, j])==1)] for di in range(n_days)])
            out_df = pd.DataFrame(res_rows, index=staff_list, columns=days_cols)
            out_df["公休計"] = [row.count("休") for row in res_rows]
            def paint(v):
                if v == "休": return 'background-color: #ffcccc'
                if v == "日": return 'background-color: #e0f0ff'
                if v in e_gr: return 'background-color: #ffffcc'
                return 'background-color: #ccffcc'
            st.dataframe(out_df.style.map(paint), use_container_width=True)
            st.download_button("📥 完成版をダウンロード(CSV)", out_df.to_csv().encode('utf-8-sig'), f"roster_{year}_{month}.csv")
        else: st.error("❌ 条件に自己矛盾が生じ、答えがありません。公休設定などを確認してください。")

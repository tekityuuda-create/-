import streamlit as st
import pandas as pd
import calendar
import json
from ortools.sat.python import cp_model

# --- 1. グローバルUI設定 ---
st.set_page_config(page_title="究極勤務AI：V83 Final UI", page_icon="🛡️", layout="wide")

# ==========================================
# セッション状態の強固な管理 (二重入力・点滅防止)
# ==========================================
if 'config' not in st.session_state:
    st.session_state.config = {
        "num_mgr": 2, "num_regular": 8,
        "staff_names": [f"スタッフ{i+1}" for i in range(10)],
        "user_shifts": "A,B,C,D,E", "early_shifts": ["A", "B", "C"], "late_shifts": ["D", "E"],
        "year": 2025, "month": 1, "saved_tables": {}
    }

def update_table_in_state(key, new_df):
    """入力があった瞬間にセッション情報を更新する"""
    st.session_state.config["saved_tables"][key] = new_df.to_dict()

def get_stable_df(key, base_df, categories=None):
    """セッションから安定したDataFrameを生成し、型を矯正する"""
    saved = st.session_state.config["saved_tables"].get(key)
    df = pd.DataFrame(saved) if saved else base_df
    # indexとcolumnsの同期 (スタッフ追加/シフト変更対応)
    df = df.reindex(index=base_df.index, columns=base_df.columns).fillna(base_df)
    if categories:
        for c in df.columns: df[c] = pd.Categorical(df[c], categories=categories)
    return df

st.title("🛡️ 究極の勤務作成エンジン V83 (Input Stability Passed)")

# --- 2. サイドバー：同期管理 ---
with st.sidebar:
    st.header("💾 設定データの同期")
    up_file = st.file_uploader("JSONファイルをアップロード", type="json")
    if up_file:
        try:
            st.session_state.config.update(json.load(up_file))
            st.rerun() # 読み込み時は一度強制リロードして安定させる
        except: st.error("エラー：不適切なファイルです。")

    st.divider()
    st.header("🎯 AIの思考バランス")
    w_strictness = st.slider("ルールの厳格度", 0, 100, 95)
    w_rhythm = st.slider("シフトの混合（早遅）", 0, 100, 70)
    w_fairness = st.slider("個人間の公平性", 0, 100, 50)

    st.divider()
    year = int(st.number_input("対象年", 2024, 2030, st.session_state.config["year"]))
    month = int(st.number_input("対象月", 1, 12, st.session_state.config["month"]))
    st.session_state.config["year"], st.session_state.config["month"] = year, month

# --- 3. メインタブ構成 ---
t1, t2, t3 = st.tabs(["🏗️ 1. 基本設定・名簿", "⚖️ 2. スキル・回数設定", "🧬 3. 指定入力・実行"])

# --- データの準備 (リロードによるリセットを阻止) ---
with t1:
    col_l, col_r = st.columns(2)
    with col_l:
        st.subheader("👥 人員配置")
        nm_mgr = st.number_input("管理者の人数", 0, 5, st.session_state.config["num_mgr"])
        nm_reg = st.number_input("一般職の人数", 1, 20, st.session_state.config["num_regular"])
        total = int(nm_mgr + nm_reg)
        st.session_state.config["num_mgr"], st.session_state.config["num_regular"] = nm_mgr, nm_reg
        
        c_names = st.session_state.config["staff_names"]
        if len(c_names) < total: c_names.extend([f"スタッフ{i+1}" for i in range(len(c_names), total)])
        staff_base_names = c_names[:total]
        n_ed = st.data_editor(pd.DataFrame({"名前": staff_base_names}), use_container_width=True, key="name_ui")
        staff_list = n_ed["名前"].tolist()
        st.session_state.config["staff_names"] = staff_list
        
    with col_r:
        st.subheader("📋 シフト構成")
        raw_s = st.text_input("シフトの略称 (カンマ区切り)", st.session_state.config["user_shifts"])
        st.session_state.config["user_shifts"] = raw_s
        s_list = [s.strip() for s in raw_s.split(",") if s.strip()]
        
        e_gr = st.multiselect("早番として扱う", s_list, default=[x for x in s_list if x in st.session_state.config["early_shifts"]])
        l_gr = st.multiselect("遅番として扱う", s_list, default=[x for x in s_list if x in st.session_state.config["late_shifts"]])
        st.session_state.config["early_shifts"], st.session_state.config["late_shifts"] = e_gr, l_gr

# スタッフ確定後の動的テーブル取得
with t2:
    st.subheader("🎓 専門適性とノルマ")
    sk_base = pd.DataFrame("○", index=staff_list, columns=s_list)
    ed_skill = st.data_editor(get_stable_df("skill", sk_base, ["○","△","×"]), use_container_width=True, key="skill_ui")
    update_table_in_state("skill", ed_skill)
    
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        st.write("📊 公休数 (B列)")
        hol_base = pd.DataFrame(9, index=staff_list, columns=["公休数"])
        ed_hols = st.data_editor(get_stable_df("hols", hol_base), use_container_width=True, key="hols_ui")
        update_table_in_state("hols", ed_hols)
    with col_c2:
        st.write("📈 見習い回数の指定")
        tr_base = pd.DataFrame(0, index=staff_list, columns=[f"{s}_回数" for s in s_list])
        ed_trainee = st.data_editor(get_stable_df("trainee", tr_base), use_container_width=True, key="tr_ui")
        update_table_in_state("trainee", ed_trainee)

with t3:
    _, n_days = calendar.monthrange(year, month)
    d_cols = [f"{d+1}({['月','火','水','木','金','土','日'][calendar.weekday(year,month,d+1)]})" for d in range(n_days)]
    st.subheader("🗓️ シフト情報の打ち込み")

    col_pre, col_req = st.columns([1, 2.5])
    with col_pre:
        st.write("前月引継 (4日間)")
        p_base = pd.DataFrame("休", index=staff_list, columns=["4日前","3日前","2日前","末日"])
        ed_prev = st.data_editor(get_stable_df("prev", p_base, ["日","休","早","遅"]), use_container_width=True, key="prev_ui")
        update_table_in_state("prev", ed_prev)
    with col_req:
        st.write("今月の申し込み・固定")
        opts = ["", "休", "日"] + s_list
        req_base = pd.DataFrame("", index=staff_list, columns=d_cols)
        ed_req = st.data_editor(get_stable_df("request", req_base, opts), use_container_width=True, key="req_ui")
        update_table_in_state("request", ed_req)

    st.write("特定の担務を行わない日")
    ex_base = pd.DataFrame(False, index=[d+1 for d in range(n_days)], columns=s_list)
    ed_excl = st.data_editor(get_stable_df("exclude", ex_base), use_container_width=True, key="excl_ui")
    update_table_in_state("exclude", ed_excl)

    # 最終的な保存データの全同期
    st.sidebar.download_button("📥 今の全ての設定をJSONで保存", json.dumps(st.session_state.config, ensure_ascii=False), f"Config_{year}_{month}.json")

    # --- 究極の数理最適化ロジック (V81 継承強化) ---
    if st.button("🚀 勤務表をAIで自動生成する", type="primary"):
        model = cp_model.CpModel()
        num_t = len(s_list)
        S_OFF, S_NIKKIN = 0, num_t + 1
        e_ids = [s_list.index(x) + 1 for x in e_gr]
        l_ids = [s_list.index(x) + 1 for x in l_gr]
        
        # 変数定義 x[スタッフ, 日, シフト]
        x = {(si, di, i): model.NewBoolVar(f'x_{si}_{di}_{i}') for si in range(total) for di in range(n_days) for i in range(num_t+2)}
        score = []

        # 引継ぎ解析 (月またぎ)
        for si in range(total):
            if ed_prev.iloc[si, 3] == "遅":
                for ei in e_ids: model.Add(x[si, 0, ei] == 0)

        for d_i in range(n_days):
            wd_n = calendar.weekday(year, month, d_i+1)
            # A. 担務の充足
            for i, s_n in enumerate(s_list):
                sid = i + 1
                is_excl = ed_excl.iloc[d_i, i] or (wd_n == 6 and s_n == "C")
                eligible = [si for si in range(total) if ed_skill.iloc[si, i] == "○"]
                trainees = [si for si in range(total) if ed_skill.iloc[si, i] == "△"]
                s_sum = sum(x[si, d_i, sid] for si in eligible)
                t_sum = sum(x[si, d_i, sid] for si in trainees)
                
                if is_excl: model.Add(sum(x[si, d_i, sid] for si in range(total)) == 0)
                else:
                    filled_f = model.NewBoolVar(f'f_{d_i}_{sid}')
                    model.Add(s_sum == 1).OnlyEnforceIf(filled_f)
                    score.append(filled_f * 5000000) 
                    model.Add(t_sum <= 1)
            # 1日1回
            for si in range(total): model.Add(sum(x[si, d_i, si_idx] for si_shift in range(num_t+2)) == 1)

        # B. 個人別ルール
        for si in range(total):
            ise_m = [model.NewBoolVar(f'ise_{si}_{d}') for d in range(n_days)]
            isl_m = [model.NewBoolVar(f'isl_{si}_{d}') for d in range(n_days)]
            iso_m = [x[si, d, S_OFF] for d in range(n_days)]
            
            for d in range(n_days):
                # 型の強制同期
                model.Add(sum(x[si, d, i] for i in e_ids) == 1).OnlyEnforceIf(ise_m[d])
                model.Add(sum(x[si, d, i] for i in e_ids) == 0).OnlyEnforceIf(ise_m[d].Not())
                model.Add(sum(x[si, d, i] for i in l_ids) == 1).OnlyEnforceIf(isl_m[d])
                model.Add(sum(x[si, d, i] for i in l_ids) == 0).OnlyEnforceIf(isl_m[d].Not())

                r_val = ed_req.iloc[si, d]
                c_map = {"休":S_OFF, "日":S_NIKKIN, "":-1}
                for i_k, n_k in enumerate(s_list): c_map[n_k] = i_k+1
                if r_val in c_map and c_map[r_val] != -1: model.Add(x[si, d, c_map[r_val]] == 1)
                
                if d < n_days - 1:
                    le_ok = model.NewBoolVar(f'le_{si}_{d}')
                    model.Add(isl_m[d] + ise_m[d+1] <= 1).OnlyEnforceIf(le_ok)
                    score.append(le_ok * 20000 * w_strictness)

            # 連勤制限、分散休み、管理者
            h_w = [1 if ed_prev.iloc[si, k] != "休" else 0 for k in range(4)] + [(1 - x[si, d, S_OFF]) for d in range(n_days)]
            for sk in range(len(h_w)-4):
                c4 = model.NewBoolVar(f'c4_{si}_{sk}')
                model.Add(sum(h_w[sk:sk+5]) <= 4).OnlyEnforceIf(c4)
                score.append(c4 * 5000 * w_strictness)
                
            for d in range(n_days - 1):
                mx_f = model.NewBoolVar(f'mxf_{si}_{d}')
                model.AddBoolAnd([ise_m[d], isl_m[d+1]]).OnlyEnforceIf(mx_f)
                score.append(mx_f * 2000 * w_rhythm)

            if si < nm_mgr:
                for d in range(n_days):
                    is_sh = (calendar.weekday(year, month, d+1) >= 5)
                    mg_v = model.NewBoolVar(f'mgv_{si}_{d}')
                    if is_sh: model.Add(x[si, d, S_OFF] == 1).OnlyEnforceIf(mg_v)
                    else: model.Add(x[si, d, S_OFF] == 0).OnlyEnforceIf(mg_v)
                    score.append(mg_v * 5000)
            else:
                for d in range(n_days):
                    if ed_req.iloc[si, d] != "日": model.Add(x[si, d, S_NIKKIN] == 0)

            t_h = int(ed_hols.iloc[si, 0])
            err = model.NewIntVar(0, n_days, f'her_{si}')
            model.AddAbsEquality(err, sum(iso_m) - t_h)
            score.append(err * -5000 * w_strictness)

        # C. 平準化
        for ish in range(1, num_t+1):
            counts = [model.NewIntVar(0, n_days, f'cnt_{p_si}_{ish}') for p_si in range(total)]
            for p_si in range(total): model.Add(counts[p_si] == sum(x[p_si, d, ish] for d in range(n_days)))
            mx, mn = model.NewIntVar(0, n_days, f'mx_{ish}'), model.NewIntVar(0, n_days, f'mn_{ish}')
            model.AddMaxEquality(mx, counts); model.AddMinEquality(mn, counts)
            score.append((mx - mn) * -500 * w_fairness)

        model.Maximize(sum(score))
        slv = cp_model.CpSolver()
        slv.parameters.max_time_in_seconds = 45.0
        status = slv.Solve(model)

        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            st.success("🎉 条件を最適化しました。")
            res_df_list = []
            id_to_c = {S_OFF:"休", S_NIKKIN:"日"}
            for i, n in enumerate(s_list): id_to_c[i+1] = n
            for si in range(total):
                res_df_list.append([id_to_c[next(j for j in range(num_t+2) if slv.Value(x[si, d, j])==1)] for d in range(n_days)])
            out = pd.DataFrame(res_df_list, index=staff_list, columns=d_cols)
            out["公休計"] = [row.count("休") for row in res_df_list]
            st.dataframe(out.style.map(lambda v: 'background-color: #ffcccc' if v=="休" else ('background-color: #e0f0ff' if v=="日" else ('background-color: #ffffcc' if v in e_gr else 'background-color: #ccffcc'))), use_container_width=True)
            st.download_button("📥 最終版ダウンロード(CSV)", out.to_csv().encode('utf-8-sig'), "Duty_Roster.csv")
        else: st.error("❌ 致命的な矛盾。公休数や4連勤制限の設定を見直してください。")

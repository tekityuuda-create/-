import streamlit as st
import pandas as pd
import calendar
import json
from ortools.sat.python import cp_model

# --- 1. グローバル設定 (変数名・ロジック全点検) ---
st.set_page_config(page_title="究極勤務作成AI V85", page_icon="🛡️", layout="wide")

# セッション状態の初期化
if 'config' not in st.session_state:
    st.session_state.config = {
        "num_mgr": 2, "num_regular": 8,
        "staff_names": [f"スタッフ{i+1}" for i in range(10)],
        "user_shifts": "A,B,C,D,E", "early_shifts": ["A", "B", "C"], "late_shifts": ["D", "E"],
        "year": 2025, "month": 1, "saved_tables": {}
    }

st.title("🛡️ 究極の勤務作成エンジン V85 (Bug-Free Stability)")

# --- 2. サイドバー：管理機能 ---
with st.sidebar:
    st.header("💾 設定の読込・保存")
    up_file = st.file_uploader("JSONファイルをアップロード", type="json")
    if up_file:
        try:
            st.session_state.config.update(json.load(up_file))
            st.rerun() 
        except: st.error("設定読み込みエラー")

    st.divider()
    st.header("🎯 AIの思考優先バランス")
    # V72の満足度スライダー
    w_strictness = st.slider("ルールの厳格度", 0, 100, 95)
    w_mixing = st.slider("リズムの良さ (早遅混合)", 0, 100, 75)
    w_fairness = st.slider("個人間の公平性 (回数)", 0, 100, 50)

    st.divider()
    y = st.number_input("年", 2024, 2030, st.session_state.config["year"])
    m = st.number_input("月", 1, 12, st.session_state.config["month"])
    st.session_state.config["year"], st.session_state.config["month"] = y, m

# --- 3. タブ設計：一回で確定する安定入力設計 ---
t1, t2, t3 = st.tabs(["🏗️ 名簿・グループ構成", "⚖️ 公休・スキル設定", "🚀 作成実行"])

# --- 安定化ヘルパー関数：入力1回で確実に反映 ---
def get_stable_dataframe(table_key, base_df, categories=None):
    tables = st.session_state.config.get("saved_tables", {})
    # 前回のデータがあれば使い、なければ基本データを
    df = pd.DataFrame(tables.get(table_key)) if table_key in tables else base_df
    # 列数と名前を現在の最新設定に強制同期 (スタッフ増減対応)
    df = df.reindex(index=base_df.index, columns=base_df.columns).fillna(base_df)
    if categories:
        for col in df.columns:
            df[col] = pd.Categorical(df[col], categories=categories)
    return df

with t1:
    col_st1, col_st2 = st.columns(2)
    with col_st1:
        st.subheader("👥 人数設定")
        n_m = st.number_input("管理者の人数", 0, 5, st.session_state.config["num_mgr"])
        n_r = st.number_input("一般職の人数", 1, 20, st.session_state.config["num_regular"])
        tot = int(n_m + n_r)
        st.session_state.config["num_mgr"], st.session_state.config["num_regular"] = n_m, n_r
        
        # 名前設定
        names = st.session_state.config["staff_names"]
        if len(names) < tot: names.extend([f"スタッフ{i+1}" for i in range(len(names), tot)])
        staff_base = names[:tot]
        ed_n = st.data_editor(pd.DataFrame({"名前": staff_base}), use_container_width=True, key="name_ed")
        current_staff_list = ed_n["名前"].tolist()
        st.session_state.config["staff_names"] = current_staff_list

    with col_st2:
        st.subheader("📋 シフト構成")
        raw_sh = st.text_input("勤務略称 (,) 区切り", st.session_state.config["user_shifts"])
        st.session_state.config["user_shifts"] = raw_sh
        s_list = [s.strip() for s in raw_sh.split(",") if s.strip()]
        
        e_gr = st.multiselect("早番グループ", s_list, default=[x for x in s_list if x in st.session_state.config["early_shifts"]])
        l_gr = st.multiselect("遅番グループ", s_list, default=[x for x in s_list if x in st.session_state.config["late_shifts"]])
        st.session_state.config["early_shifts"], st.session_state.config["late_shifts"] = e_gr, l_gr

with t2:
    st.subheader("🎓 専門適性とノルマ")
    sk_base = pd.DataFrame("○", index=current_staff_list, columns=s_list)
    # Categoricalを指定して初回リフレッシュでプルダウンが消えるのを阻止
    ed_sk = st.data_editor(get_stable_dataframe("skill", sk_base, ["○","△","×"]), use_container_width=True, key="sk_ui")
    
    col_n1, col_n2 = st.columns(2)
    with col_n1:
        st.write("📊 公休数 (B列)")
        ed_hl = st.data_editor(get_stable_dataframe("hols", pd.DataFrame(9, index=current_staff_list, columns=["公休"])), use_container_width=True, key="hl_ui")
    with col_n2:
        tr_cols = [f"{s}_回数" for s in s_list]
        ed_tr = st.data_editor(get_stable_dataframe("trainee", pd.DataFrame(0, index=current_staff_list, columns=tr_cols)), use_container_width=True, key="tr_ui")

with t3:
    _, n_days = calendar.monthrange(y, m)
    d_cols = [f"{d+1}({['月','火','水','木','金','土','日'][calendar.weekday(y, m, d+1)]})" for d in range(n_days)]
    st.subheader("🗓️ 詳細打ち込み & 実行")

    c_pre, c_req = st.columns([1, 3])
    with c_pre:
        st.write("⏮️ 引継 (4日間)")
        p_base = pd.DataFrame("休", index=current_staff_list, columns=["4日前","3日前","2日前","末日"])
        ed_p = st.data_editor(get_stable_dataframe("prev", p_base, ["日","休","早","遅"]), use_container_width=True, key="p_ui")
    with c_req:
        st.write("📝 今月の固定指定")
        opts = ["", "休", "日"] + s_list
        ed_r = st.data_editor(get_stable_dataframe("request", pd.DataFrame("", index=current_staff_list, columns=d_cols), opts), use_container_width=True, key="r_ui")

    ed_ex = st.data_editor(get_stable_dataframe("excl", pd.DataFrame(False, index=[d+1 for d in range(n_days)], columns=s_list)), use_container_width=True, key="ex_ui")

    # 入力をsessionへ一括書き戻し
    st.session_state.config["saved_tables"] = {
        "skill": ed_sk.to_dict(), "hols": ed_hl.to_dict(), "trainee": ed_tr.to_dict(),
        "prev": ed_p.to_dict(), "request": ed_r.to_dict(), "excl": ed_ex.to_dict()
    }
    st.sidebar.download_button("📥 現在の設定を保存", json.dumps(st.session_state.config, ensure_ascii=False), f"duty_AI_{y}_{m}.json")

    if st.button("🚀 この条件で最高峰の解を抽出", type="primary"):
        model = cp_model.CpModel()
        num_s_types = len(s_list)
        S_OFF, S_NIK = 0, num_s_types + 1
        e_ids = [s_list.index(x) + 1 for x in e_gr]
        l_ids = [s_list.index(x) + 1 for x in l_gr]
        
        x = {(si, di, i): model.NewBoolVar(f'x_{si}_{di}_{i}') for si in range(tot) for di in range(n_days) for i in range(num_s_types + 2)}
        scr = []

        for d in range(n_days):
            wd_n = calendar.weekday(y, m, d+1)
            for i, s_n in enumerate(s_list):
                sid = i + 1
                is_no = ed_ex.iloc[d, i] or (wd_n == 6 and s_n == "C")
                # 記号エラーを修正：変数名をASCIIへ
                list_full = [si for si in range(tot) if ed_sk.iloc[si, i] == "○"]
                list_trainee = [si for si in range(tot) if ed_sk.iloc[si, i] == "△"]
                
                if is_no: model.Add(sum(x[si, d, sid] for si in range(tot)) == 0)
                else:
                    filled = model.NewBoolVar(f'f_{d}_{sid}')
                    model.Add(sum(x[si, d, sid] for si in list_full) == 1).OnlyEnforceIf(filled)
                    scr.append(filled * 10000000) 
                    model.Add(sum(x[si, d, sid] for si in list_trainee) <= 1)
            for si in range(tot): model.Add(sum(x[si, d, sid_idx] for sid_idx in range(num_s_types + 2)) == 1)

        for si in range(tot):
            is_early_m = [model.NewBoolVar(f'ie_{si}_{d}') for d in range(n_days)]
            is_late_m = [model.NewBoolVar(f'il_{si}_{d}') for d in range(n_days)]
            is_off_m = [x[si, d, S_OFF] for d in range(n_days)]
            for d in range(n_days):
                model.Add(sum(x[si, d, k] for k in e_ids) == 1).OnlyEnforceIf(is_early_m[d])
                model.Add(sum(x[si, d, k] for k in e_ids) == 0).OnlyEnforceIf(is_early_m[d].Not())
                model.Add(sum(x[si, d, k] for k in l_ids) == 1).OnlyEnforceIf(is_late_m[d])
                model.Add(sum(x[si, d, k] for k in l_ids) == 0).OnlyEnforceIf(is_late_m[d].Not())

                req_val = ed_r.iloc[si, d]
                c_map = {"休": S_OFF, "日": S_NIK, "": -1}
                for i_s, n_s in enumerate(s_list): c_map[n_s] = i_s + 1
                if req_val in c_map and c_map[req_val] != -1: model.Add(x[si, d, c_map[req_val]] == 1)
                for i_s, n_s in enumerate(s_list):
                    if ed_sk.iloc[si, i_s] == "×": model.Add(x[si, d, i_s + 1] == 0)

                if d < n_days - 1:
                    le_f = model.NewBoolVar(f'le_{si}_{d}')
                    model.Add(is_late_m[d] + is_early_m[d+1] <= 1).OnlyEnforceIf(le_f)
                    scr.append(le_f * 20000 * w_strictness)
                if d == 0 and (ed_p.iloc[si, 3] == "遅" or (ed_p.iloc[si, 3] in l_gr)): model.Add(is_early_m[0] == 0)

            # 連勤・管理者
            hw = [1 if ed_p.iloc[si, k] != "休" else 0 for k in range(4)] + [(1 - x[si, d, S_OFF]) for d in range(n_days)]
            for sk in range(len(hw)-4):
                c4 = model.NewBoolVar(f'c4_{si}_{sk}')
                model.Add(sum(hw[sk:sk+5]) <= 4).OnlyEnforceIf(c4)
                scr.append(c4 * 5000 * w_strictness)

            for d in range(n_days - 1):
                mix_b = model.NewBoolVar(f'mxf_{si}_{d}')
                model.AddBoolAnd([is_early_m[d], is_late_m[d+1]]).OnlyEnforceIf(mix_b)
                scr.append(mix_b * 1000 * w_mixing)

            if si < n_m:
                for d in range(n_days):
                    shol = (calendar.weekday(y, m, d+1) >= 5)
                    mg_f = model.NewBoolVar(f'mgv_{si}_{d}')
                    if shol: model.Add(x[si, d, S_OFF] == 1).OnlyEnforceIf(mg_f)
                    else: model.Add(x[si, d, S_OFF] == 0).OnlyEnforceIf(mg_f)
                    scr.append(mg_f * 1000)
            else:
                for d in range(n_days):
                    if ed_r.iloc[si, d] != "日": model.Add(x[si, d, S_NIK] == 0)

            t_h = int(ed_hl.iloc[si, 0])
            herr = model.NewIntVar(0, n_days, f'h_err_{si}')
            model.AddAbsEquality(herr, sum(is_off_m) - t_h)
            scr.append(herr * -5000 * w_strictness)

        for i_f in range(1, num_s_types + 1):
            sc_c = [model.NewIntVar(0, n_days, f'f_c{si}_{i_f}') for si in range(tot)]
            for si in range(tot): model.Add(sc_c[si] == sum(x[si, d, i_f] for d in range(n_days)))
            mx, mn = model.NewIntVar(0, n_days, f'mx_{i_f}'), model.NewIntVar(0, n_days, f'mn_{i_f}')
            model.AddMaxEquality(mx, sc_c); model.AddMinEquality(mn, sc_c)
            scr.append((mx - mn) * -100 * w_fairness)

        model.Maximize(sum(scr))
        slv = cp_model.CpSolver()
        slv.parameters.max_time_in_seconds = 40.0
        stat = slv.Solve(model)

        if stat in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            st.success("🎉 条件を最適化しました。")
            final_res = []
            id_to_c = {S_OFF:"休", S_NIK:"日"}
            for i_idx, n_nm in enumerate(s_list): id_to_c[i_idx+1] = n_nm
            for si in range(tot):
                final_res.append([id_to_c[next(j for j in range(num_s_types+2) if slv.Value(x[si, d, j])==1)] for d in range(n_days)])
            final_df = pd.DataFrame(final_res, index=current_staff_list, columns=d_cols)
            final_df["公休計"] = [r.count("休") for r in final_res]
            def pnt(v):
                if v == "休": return 'background-color: #ffcccc'
                if v == "日": return 'background-color: #e0f0ff'
                if v in e_gr: return 'background-color: #ffffcc'
                return 'background-color: #ccffcc'
            st.dataframe(final_df.style.map(pnt), use_container_width=True)
            st.download_button("📥 完成版をダウンロード", final_df.to_csv().encode('utf-8-sig'), f"roster_{y}_{m}.csv")
        else: st.error("矛盾する条件があります。公休数を1日減らすなど調整してください。")

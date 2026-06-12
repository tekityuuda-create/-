import streamlit as st
import pandas as pd
import calendar
import json
from ortools.sat.python import cp_model

# --- 1. グローバル設定 (不動のV84コア) ---
st.set_page_config(page_title="究極勤務作成AI V84", page_icon="🛡️", layout="wide")

# セッション状態の強固な初期化
if 'init' not in st.session_state:
    st.session_state.init = True
    st.session_state.master_data = pd.DataFrame(
        {"名前": [f"スタッフ{i+1}" for i in range(10)], "公休数": [9] * 10, 
         "Aスキル":["○"]*10, "Bスキル":["○"]*10, "Cスキル":["○"]*10, "Dスキル":["○"]*10, "Eスキル":["○"]*10,
         "A回数":[0]*10, "B回数":[0]*10, "C回数":[0]*10, "D回数":[0]*10, "E回数":[0]*10}
    )
    st.session_state.prev_data = pd.DataFrame("休", index=range(10), columns=["4日前","3日前","2日前","末日"])
    st.session_state.user_shifts = "A,B,C,D,E"
    st.session_state.early_shifts = ["A", "B", "C"]
    st.session_state.late_shifts = ["D", "E"]
    st.session_state.year = 2025
    st.session_state.month = 1
    # 申し込みデータは後でカレンダーに合わせて動的に作成

st.title("🛡️ 究極の勤務作成エンジン V84 (Zero-Latency Sync)")

# --- 2. サイドバー：AI性格と年月設定 ---
with st.sidebar:
    st.header("💾 設定のバックアップ")
    up_file = st.file_uploader("JSON読込", type="json")
    if up_file:
        try:
            load = json.load(up_file)
            st.session_state.master_data = pd.DataFrame(load["master"])
            st.session_state.prev_data = pd.DataFrame(load["prev"])
            st.session_state.user_shifts = load["shifts"]
            st.rerun()
        except: st.error("ファイルエラー")

    st.divider()
    st.header("🎯 AIの優先戦略 (V72コンセプト)")
    w_strict = st.slider("ルールの厳格度 (4連勤/遅早など)", 0, 100, 95)
    w_rhythm = st.slider("リズム重視 (早遅を交互に)", 0, 100, 75)
    w_fair = st.slider("公平性の重視 (回数の平準化)", 0, 100, 50)
    
    st.divider()
    y = st.number_input("年", 2024, 2030, st.session_state.year)
    m = st.number_input("月", 1, 12, st.session_state.month)
    st.session_state.year, st.session_state.month = y, m

# --- 3. タブ構成：操作の最短動線 ---
tab1, tab2 = st.tabs(["🏗️ 名簿・ルール・スキル設定", "🧬 勤務作成実行"])

with tab1:
    col_cfg1, col_cfg2 = st.columns(2)
    with col_cfg1:
        st.subheader("👥 人数構成")
        n_mgr = st.number_input("管理者の人数", 0, 5, 2)
        n_reg = st.number_input("一般職の人数", 1, 20, 8)
        tot = n_mgr + n_reg
        # 人数増減に合わせたデータ調整
        if len(st.session_state.master_data) != tot:
            st.session_state.master_data = st.session_state.master_data.reindex(range(tot)).fillna(method='ffill')
            st.session_state.prev_data = st.session_state.prev_data.reindex(range(tot)).fillna("休")

    with col_cfg2:
        st.subheader("📋 勤務グループ")
        sh_input = st.text_input("略称(カンマ区切り)", st.session_state.user_shifts)
        s_list = [s.strip() for s in sh_input.split(",") if s.strip()]
        st.session_state.user_shifts = sh_input
        e_gr = st.multiselect("早番グループ", s_list, default=[x for x in s_list if x in st.session_state.early_shifts])
        l_gr = st.multiselect("遅番グループ", s_list, default=[x for x in s_list if x in st.session_state.late_shifts])
        st.session_state.early_shifts, st.session_state.late_shifts = e_gr, l_gr

    st.divider()
    st.subheader("👤 スタッフ詳細マスタ (名前・公休・スキル・回数)")
    # 型を維持するためのマッピング
    for s in s_list:
        if f"{s}スキル" not in st.session_state.master_data.columns:
            st.session_state.master_data[f"{s}スキル"] = "○"
            st.session_state.master_data[f"{s}回数"] = 0
    
    # カテゴリカル型を適用して強制プルダウン
    active_master = st.session_state.master_data.copy()
    for s in s_list:
        active_master[f"{s}スキル"] = pd.Categorical(active_master[f"{s}スキル"], categories=["○", "△", "×"])
    
    # ここが解決の鍵：更新データをその場でsession_stateに叩き込む
    ed_m = st.data_editor(active_master, use_container_width=True, key="master_editor_ui")
    st.session_state.master_data = ed_m
    staff_names = ed_m["名前"].tolist()

with tab2:
    _, num_days = calendar.monthrange(y, m)
    d_cols = [f"{d+1}({['月','火','水','木','金','土','日'][calendar.weekday(y, m, d+1)]})" for d in range(num_days)]
    
    c_p, c_r = st.columns([1, 2.5])
    with c_p:
        st.write("⏮️ 前月引継ぎ(4日間)")
        # インデックス名だけ上書き表示
        active_prev = st.session_state.prev_data.copy()
        active_prev.index = staff_names
        for col in active_prev.columns: active_prev[col] = pd.Categorical(active_prev[col], categories=["日", "休", "早", "遅"])
        ed_p = st.data_editor(active_prev, use_container_width=True, key="prev_editor_ui")
        st.session_state.prev_data = ed_p.reset_index(drop=True)

    with c_r:
        st.write("📝 今月の指定 (申し込み)")
        if 'request_data' not in st.session_state or st.session_state.request_data.shape[1] != num_days:
            st.session_state.request_data = pd.DataFrame("", index=range(tot), columns=d_cols)
        
        active_req = st.session_state.request_data.copy()
        active_req.index = staff_names
        status_opts = ["", "休", "日"] + s_list
        for col in active_req.columns: active_req[col] = pd.Categorical(active_req[col], categories=status_opts)
        ed_r = st.data_editor(active_req, use_container_width=True, key="req_editor_ui")
        st.session_state.request_data = ed_r.reset_index(drop=True)

    st.write("🚫 不要担務の設定 (チェック)")
    if 'exclude_data' not in st.session_state or st.session_state.exclude_data.shape[1] != len(s_list):
        st.session_state.exclude_data = pd.DataFrame(False, index=[d+1 for d in range(num_days)], columns=s_list)
    ed_x = st.data_editor(st.session_state.exclude_data, use_container_width=True, key="excl_editor_ui")
    st.session_state.exclude_data = ed_x

    # 保存ファイル
    backup = {"master": st.session_state.master_data.to_dict(), "prev": st.session_state.prev_data.to_dict(), "shifts": sh_input}
    st.sidebar.download_button("📥 今の設定を保存", json.dumps(backup, ensure_ascii=False), f"RosterConfig_{y}_{m}.json")

    # --- 最適化実行 (V72 Rhythm + Fair Engine) ---
    if st.button("🚀 究極のAI最適化を実行する", type="primary"):
        model = cp_model.CpModel()
        num_s = len(s_list)
        S_OFF, S_NIK = 0, num_s + 1
        E_IDS = [s_list.index(x) + 1 for x in e_gr]
        L_IDS = [s_list.index(x) + 1 for x in l_gr]
        
        x = {(si, di, i): model.NewBoolVar(f'x_{si}_{di}_{i}') for si in range(tot) for di in range(num_days) for i in range(num_s+2)}
        penalties = []

        # 担務充足ロジック
        for di in range(num_days):
            wd_val = calendar.weekday(y, m, di+1)
            for i, s_n in enumerate(s_list):
                sid = i + 1
                is_excl = ed_x.iloc[di, i] or (wd_val == 6 and s_n == "C")
                skill_○ = [si for si in range(tot) if ed_m.iloc[si, i+2] == "○"]
                skill_△ = [si for si in range(tot) if ed_m.iloc[si, i+2] == "△"]
                
                if is_excl: model.Add(sum(x[si, di, sid] for si in range(tot)) == 0)
                else:
                    filled_f = model.NewBoolVar(f'f_{di}_{sid}')
                    model.Add(sum(x[si, di, sid] for si in skill_○) == 1).OnlyEnforceIf(filled_f)
                    penalties.append(filled_f * 10000000)
                    model.Add(sum(x[si, di, sid] for si in skill_△) <= 1)

            for si in range(tot): model.Add(sum(x[si, di, shift_id] for shift_id in range(num_s+2)) == 1)

        # 個人・リズム・連勤・公休
        for si in range(tot):
            ise_m = [model.NewBoolVar(f'ise_{si}_{d}') for d in range(num_days)]
            isl_m = [model.NewBoolVar(f'isl_{si}_{d}') for d in range(num_days)]
            is_o = [x[si, d, S_OFF] for d in range(num_days)]

            for d in range(num_days):
                model.Add(sum(x[si, d, k] for k in E_IDS) == 1).OnlyEnforceIf(ise_m[d])
                model.Add(sum(x[si, d, k] for k in E_IDS) == 0).OnlyEnforceIf(ise_m[d].Not())
                model.Add(sum(x[si, d, k] for k in L_IDS) == 1).OnlyEnforceIf(isl_m[d])
                model.Add(sum(x[si, d, k] for k in L_IDS) == 0).OnlyEnforceIf(isl_m[d].Not())

                r_val = ed_r.iloc[si, d]
                rid_map = {"休":S_OFF, "日":S_NIK}
                for i_n, s_n in enumerate(s_list): rid_map[s_n] = i_n+1
                if r_val in rid_map: model.Add(x[si, d, rid_map[r_val]] == 1)
                
                for i_n, s_n in enumerate(s_list):
                    if ed_m.iloc[si, i_n+2] == "×": model.Add(x[si, d, i_n+1] == 0)
                if d < num_days - 1:
                    ok_le = model.NewBoolVar(f'le_{si}_{d}')
                    model.Add(isl_m[d] + ise_m[d+1] <= 1).OnlyEnforceIf(ok_le)
                    penalties.append(ok_le * 20000 * w_strict)
                if d == 0 and (ed_p.iloc[si, 3] == "遅" or (ed_p.iloc[si, 3] in l_gr)): model.Add(ise_m[0] == 0)

            hist_w = [1 if ed_p.iloc[si, k] != "休" else 0 for k in range(4)] + [(1 - x[si, di, S_OFF]) for di in range(num_days)]
            for start_k in range(len(hist_w)-4):
                c4 = model.NewBoolVar(f'c4_{si}_{start_k}')
                model.Add(sum(hist_w[start_k:start_k+5]) <= 4).OnlyEnforceIf(c4)
                penalties.append(c4 * 10000 * w_strict)

            for d in range(num_days-1):
                mxb = model.NewBoolVar(f'mx_{si}_{d}')
                model.AddBoolAnd([ise_m[d], isl_m[d+1]]).OnlyEnforceIf(mxb)
                penalties.append(mxb * 1000 * w_rhythm)

            if si < n_mgr:
                for d in range(num_days):
                    is_sh = (calendar.weekday(y, m, d+1) >= 5)
                    mg_f = model.NewBoolVar(f'mgv_{si}_{d}')
                    if is_sh: model.Add(is_o[d] == 1).OnlyEnforceIf(mg_f)
                    else: model.Add(is_o[d] == 0).OnlyEnforceIf(mg_f)
                    penalties.append(mg_f * 5000)
            else:
                for d in range(num_days):
                    if ed_r.iloc[si, d] != "日": model.Add(x[si, d, S_NIK] == 0)

            t_hol = int(ed_m.iloc[si, 1])
            err_var = model.NewIntVar(0, num_days, f'h_err_{si}')
            model.AddAbsEquality(err_var, sum(is_o) - t_h if (t_h := t_hol) else 0)
            penalties.append(err_var * -10000 * w_strict)

        for i_f in range(1, num_s+1):
            counts = [model.NewIntVar(0, num_days, f'c{p_si}_{i_f}') for p_si in range(tot)]
            for p_si in range(tot): model.Add(counts[p_si] == sum(x[p_si, d, i_f] for d in range(num_days)))
            max_v, min_v = model.NewIntVar(0, num_days, f'max_{i_f}'), model.NewIntVar(0, num_days, f'min_{i_f}')
            model.AddMaxEquality(max_v, counts); model.AddMinEquality(min_v, counts)
            penalties.append((max_v - min_v) * -500 * w_fair)

        model.Maximize(sum(penalties))
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 50.0
        status = solver.Solve(model)

        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            st.success("✨ 最高精度で調整が完了しました。")
            res_rows = []
            id_to_char = {S_OFF:"休", S_NIKKIN:"日"}
            for i, n in enumerate(s_list): id_to_char[i+1] = n
            for si in range(tot):
                res_rows.append([id_to_char[next(j for j in range(num_s+2) if solver.Value(x[si, d, j])==1)] for d in range(num_days)])
            out_df = pd.DataFrame(res_rows, index=staff_names, columns=d_cols)
            out_df["公休計"] = [row.count("休") for row in res_rows]
            st.dataframe(out_df.style.map(lambda v: 'background-color: #ffcccc' if v=="休" else ('background-color: #e0f0ff' if x=="日" else ('background-color: #ffffcc' if v in e_gr else 'background-color: #ccffcc'))), use_container_width=True)
            st.download_button("📥 最終結果保存(CSV)", out_df.to_csv().encode('utf-8-sig'), "roster_v84.csv")
        else: st.error("❌ 解がありません。設定を見直してください。")

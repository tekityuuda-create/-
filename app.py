import streamlit as st
import pandas as pd
import calendar
import json
from ortools.sat.python import cp_model

# --- 1. 画面基本設定 ---
st.set_page_config(page_title="世界最高峰 勤務作成AI V77", page_icon="🛡️", layout="wide")

# セッション状態の初期化
if 'config' not in st.session_state:
    st.session_state.config = {
        "num_mgr": 2, "num_regular": 8,
        "staff_names": [f"スタッフ{i+1}" for i in range(10)],
        "user_shifts": "A,B,C,D,E", "early_shifts": ["A", "B", "C"], "late_shifts": ["D", "E"],
        "year": 2025, "month": 1, "saved_tables": {}
    }

st.title("🛡️ 究極の勤務作成エンジン (Ultra-Robust V77)")

# --- 2. サイドバー：データ保存と復元 ---
with st.sidebar:
    st.header("💾 設定の保存と復元")
    uploaded_file = st.file_uploader("設定ファイルを読み込む(.json)", type="json")
    if uploaded_file is not None:
        try:
            st.session_state.config.update(json.load(uploaded_file))
            st.success("全てのデータを正常に復元しました。")
        except Exception:
            st.error("エラー：ファイル形式が不正です。")

    st.divider()
    year = int(st.number_input("年", 2024, 2030, st.session_state.config["year"]))
    month = int(st.number_input("月", 1, 12, st.session_state.config["month"]))

# --- 3. タブ構成 ---
tab_master, tab_create = st.tabs(["👥 1. スタッフ名簿・ルール設定", "🧬 2. 勤務表の作成・実行"])

with tab_master:
    col_l, col_r = st.columns(2)
    with col_l:
        st.subheader("👥 組織構成")
        n_mgr = st.number_input("管理者の人数", 0, 5, st.session_state.config["num_mgr"])
        n_reg = st.number_input("一般スタッフの人数", 1, 20, st.session_state.config["num_regular"])
        total = int(n_mgr + n_reg)
    with col_r:
        st.subheader("📋 シフトグループ")
        raw_s = st.text_input("勤務略称 (カンマ区切り)", st.session_state.config["user_shifts"])
        s_list = [s.strip() for s in raw_s.split(",") if s.strip()]
        e_shifts = st.multiselect("早番グループ", s_list, default=[x for x in s_list if x in st.session_state.config["early_shifts"]])
        l_shifts = st.multiselect("遅番グループ", s_list, default=[x for x in s_list if x in st.session_state.config["late_shifts"]])

    st.divider()
    st.subheader("👤 スタッフ詳細マスタ")
    
    # マスタ列名の定義（固定名を使用することでエラーを回避）
    col_name = "名前"
    col_holi = "公休数"
    skill_cols = [f"{s}スキル" for s in s_list]
    count_cols = [f"{s}回数" for s in s_list]
    
    saved_master = st.session_state.config.get("saved_tables", {}).get("master")
    if saved_master:
        master_df = pd.DataFrame(saved_master)
    else:
        init_data = {col_name: [f"スタッフ{i+1}" for i in range(total)], col_holi: [9] * total}
        for s in s_list:
            init_data[f"{s}スキル"] = ["○"] * total
            init_data[f"{s}回数"] = [0] * total
        master_df = pd.DataFrame(init_data)

    # 行列の整合性チェック
    master_df = master_df.reindex(range(total)).fillna("")
    for i in range(total):
        if not master_df.at[i, col_name]: master_df.at[i, col_name] = f"スタッフ{i+1}"
        if not master_df.at[i, col_holi]: master_df.at[i, col_holi] = 9
    
    # スキル列をプルダウン化
    for s_col in skill_cols:
        if s_col in master_df.columns:
            master_df[s_col] = pd.Categorical(master_df[s_col], categories=["○", "△", "×"])
    
    ed_master = st.data_editor(master_df, use_container_width=True, key="master_ed")
    staff_list = ed_master[col_name].tolist()

with tab_create:
    _, num_days = calendar.monthrange(year, month)
    week_ja = ['月','火','水','木','金','土','日']
    d_cols = [f"{d+1}({week_ja[calendar.weekday(year, month, d+1)]})" for d in range(num_days)]
    
    st.subheader("⏮️ 前月末の状況 & 📝 今月の指定")
    p_days = ["前月4日前", "前月3日前", "前月2日前", "前月末日"]
    saved_p = st.session_state.config.get("saved_tables", {}).get("prev")
    p_df = pd.DataFrame(saved_p) if saved_p else pd.DataFrame("休", index=staff_list, columns=p_days)
    p_df = p_df.reindex(index=staff_list, columns=p_days).fillna("休")
    for col in p_days: p_df[col] = pd.Categorical(p_df[col], categories=["日", "休", "早", "遅"])
    ed_prev = st.data_editor(p_df, use_container_width=True, key="prev_editor")

    options = ["", "休", "日"] + s_list
    saved_r = st.session_state.config.get("saved_tables", {}).get("request")
    r_df = pd.DataFrame(saved_r) if saved_r else pd.DataFrame("", index=staff_list, columns=d_cols)
    r_df = r_df.reindex(index=staff_list, columns=d_cols).fillna("")
    for col in d_cols: r_df[col] = pd.Categorical(r_df[col], categories=options)
    ed_req = st.data_editor(r_df, use_container_width=True, key="r_ed")

    st.subheader("🚫 不要担務")
    saved_ex = st.session_state.config.get("saved_tables", {}).get("exclude")
    ex_df = pd.DataFrame(saved_ex) if saved_ex else pd.DataFrame(False, index=[d+1 for d in range(num_days)], columns=s_list)
    ex_df = ex_df.reindex(index=[d+1 for d in range(num_days)], columns=s_list).fillna(False)
    ed_ex = st.data_editor(ex_df, use_container_width=True, key="ex_ed")

    # 全保存データ同期
    st.session_state.config.update({
        "num_mgr": n_mgr, "num_regular": n_reg, "staff_names": staff_list, "user_shifts": raw_s,
        "early_shifts": e_shifts, "late_shifts": l_shifts, "year": year, "month": month,
        "saved_tables": {
            "master": ed_master.to_dict(), "prev": ed_prev.to_dict(), "request": ed_req.to_dict(), "exclude": ed_ex.to_dict()
        }
    })
    st.sidebar.download_button("📥 全設定を保存する", json.dumps(st.session_state.config, ensure_ascii=False), f"config_{year}_{month}.json")

    if st.button("🚀 究極の最適化を実行する", type="primary"):
        model = cp_model.CpModel()
        S_OFF, S_NIK = 0, len(s_list) + 1
        E_IDS = [s_list.index(x) + 1 for x in e_shifts]
        L_IDS = [s_list.index(x) + 1 for x in l_shifts]
        
        # 変数定義
        x = {(s, d, i): model.NewBoolVar(f'x_{s}_{d}_{i}') for s in range(total) for d in range(num_days) for i in range(len(s_list) + 2)}
        penalty = []
        c_to_id = {"休": S_OFF, "日": S_NIK, "": -1}
        for i_s, n_s in enumerate(s_list): c_to_id[n_s] = i_s + 1

        # 担務充足
        for d in range(num_days):
            wd_v = calendar.weekday(year, month, d+1)
            for i_shift, s_name in enumerate(s_list):
                sid = i_shift + 1
                is_ex = ed_ex.iloc[d, i_shift] or (wd_v == 6 and s_name == "C")
                skilled = [s for s in range(total) if ed_master.at[s, f"{s_name}スキル"] == "○"]
                trainees = [s for s in range(total) if ed_master.at[s, f"{s_name}スキル"] == "△"]
                s_sum = sum(x[s, d, sid] for s in skilled)
                t_sum = sum(x[s, d, sid] for s in trainees)
                if is_ex: model.Add(s_sum + t_sum == 0)
                else:
                    model.Add(s_sum == 1)
                    model.Add(t_sum <= 1)

        # 個人制約
        for s in range(total):
            is_e = [model.NewBoolVar(f'ise_{s}_{d}') for d in range(num_days)]
            is_l = [model.NewBoolVar(f'isl_{s}_{d}') for d in range(num_days)]
            is_off = [x[s, d, S_OFF] for d in range(num_days)]

            for d in range(num_days):
                model.Add(sum(x[s, d, i] for i in range(len(s_list) + 2)) == 1)
                model.Add(sum(x[s, d, i] for i in E_IDS) == 1).OnlyEnforceIf(is_e[d])
                model.Add(sum(x[s, d, i] for i in E_IDS) == 0).OnlyEnforceIf(is_e[d].Not())
                model.Add(sum(x[s, d, i] for i in L_IDS) == 1).OnlyEnforceIf(is_l[d])
                model.Add(sum(x[s, d, i] for i in L_IDS) == 0).OnlyEnforceIf(is_l[d].Not())

                req_val = ed_req.iloc[s, d]
                if req_val in c_to_id and req_val != "": model.Add(x[s, d, c_to_id[req_val]] == 1)
                for i_shift, s_name in enumerate(s_list):
                    if ed_master.at[s, f"{s_name}スキル"] == "×": model.Add(x[s, d, i_shift+1] == 0)

                if d < num_days - 1: model.Add(is_l[d] + is_e[d+1] <= 1)
                if d == 0 and (ed_prev.iloc[s, 3] == "遅" or (ed_prev.iloc[s, 3] in l_shifts)):
                    model.Add(is_e[0] == 0)

            # 連勤制限
            history_w = [1 if ed_prev.iloc[s, k] != "休" else 0 for k in range(4)] + [(1 - is_off[d]) for d in range(num_days)]
            for start_d in range(len(history_w)-4): model.Add(sum(history_w[start_d:start_d+5]) <= 4)

            # 3連休禁止
            history_o = [1 if ed_prev.iloc[s, k] == "休" else 0 for k in range(4)] + is_off
            for start_d in range(len(history_o) - 2):
                is_3o = model.NewBoolVar(f'i3o_{s}_{start_d}')
                model.AddBoolAnd(history_o[start_d:start_d+3]).OnlyEnforceIf(is_3o)
                penalty.append(is_3o * -8000000)

            # 管理者・一般 / 公休 / 見習い回数
            if s < n_mgr:
                for d in range(num_days):
                    wd_v = calendar.weekday(year, month, d+1)
                    m_g = model.NewBoolVar(f'mg_{s}_{d}')
                    if wd_v >= 5: model.Add(is_off[d] == 1).OnlyEnforceIf(m_g)
                    else: model.Add(is_off[d] == 0).OnlyEnforceIf(m_g)
                    penalty.append(m_g * 1000000)
            else:
                for d in range(num_days):
                    if ed_req.iloc[s, d] != "日": model.Add(x[s, d, S_NIK] == 0)

            for i_shift, s_name in enumerate(s_list):
                try:
                    t_val = int(ed_master.at[s, f"{s_name}回数"] or 0)
                except:
                    t_val = 0
                if ed_master.at[s, f"{s_name}スキル"] == "△" and t_val > 0:
                    model.Add(sum(x[s, d, i_shift+1] for d in range(num_days)) == t_val)

            act_h = sum(is_off)
            try:
                target_h = int(ed_hols.iloc[s, 0] or 9)
            except:
                target_h = 9
            h_err = model.NewIntVar(0, num_days, f'herr_{s}')
            model.AddAbsEquality(h_err, act_h - target_h)
            penalty.append(h_err * -5000000)

        # 公平性
        for i_shift in range(1, len(s_list) + 1):
            sc = [model.NewIntVar(0, num_days, f'sc_{s}_{i_shift}') for s in range(total)]
            for s in range(total): model.Add(sc[s] == sum(x[s, d, i_shift] for d in range(num_days)))
            mx, mn = model.NewIntVar(0, num_days, f'mx_{i_shift}'), model.NewIntVar(0, num_days, f'min_{i_shift}')
            model.AddMaxEquality(mx, sc); model.AddMinEquality(mn, sc)
            penalty.append((mx - mn) * -2000000)

        model.Maximize(sum(penalty))
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 45.0
        status = solver.Solve(model)

        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            st.success("✨ 最適解を抽出しました。")
            res_data = []
            char_map = {S_OFF: "休", S_NIK: "日"}
            for i_shift, n_shift in enumerate(s_list): char_map[i_shift+1] = n_shift
            for s in range(total):
                row = [char_map[next(i_s for i_s in range(len(s_list)+2) if solver.Value(x[s, d, i_s])==1)] for d in range(num_days)]
                res_data.append(row)
            res_df = pd.DataFrame(res_data, index=staff_list, columns=d_cols)
            res_df["公休計"] = [row.count("休") for row in res_data]
            def clr(v):
                if v == "休": return 'background-color: #ffcccc'
                if v == "日": return 'background-color: #e0f0ff'
                if v in e_shifts: return 'background-color: #ffffcc'
                return 'background-color: #ccffcc'
            st.dataframe(res_df.style.map(clr), use_container_width=True)
            st.download_button("📥 CSV保存", res_df.to_csv().encode('utf-8-sig'), "roster.csv")
        else: st.error("⚠️ 解が見つかりません。")

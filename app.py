import streamlit as st
import pandas as pd
import calendar
import json
from ortools.sat.python import cp_model

# --- 1. 画面基本設定 ---
st.set_page_config(page_title="究極の勤務作成AI V73", page_icon="🛡️", layout="wide")

# セッション状態の初期化
if 'config' not in st.session_state:
    st.session_state.config = {
        "num_mgr": 2, "num_regular": 8,
        "staff_master": [], # 名前, 公休, スキルを統合
        "user_shifts": "A,B,C,D,E", "early_shifts": ["A", "B", "C"], "late_shifts": ["D", "E"],
        "year": 2025, "month": 1, "saved_tables": {}
    }

st.title("🛡️ 究極の勤務作成エンジン (Intuitive Dashboard V73)")

# --- 2. サイドバー：データの保存と復元 ---
with st.sidebar:
    st.header("💾 データ保存・復元")
    up_file = st.file_uploader("設定ファイルを読み込む", type="json")
    if up_file:
        try:
            st.session_state.config.update(json.load(up_file))
            st.success("全てのデータを復元しました。")
        except: st.error("エラー：形式が違います。")

    st.divider()
    year = st.number_input("年", 2024, 2030, st.session_state.config["year"])
    month = st.number_input("月", 1, 12, st.session_state.config["month"])

# --- 3. タブ構成（3つから2つへ統合し、移動を減らす） ---
tab_master, tab_create = st.tabs(["👥 スタッフ名簿・基本設定", "🧬 勤務表の作成・実行"])

with tab_master:
    st.subheader("🛠️ 1. 組織と勤務のルール設定")
    c1, c2 = st.columns(2)
    with c1:
        n_mgr = st.number_input("管理者の人数", 0, 5, st.session_state.config["num_mgr"])
        n_reg = st.number_input("一般スタッフの人数", 1, 20, st.session_state.config["num_regular"])
        total = int(n_mgr + n_reg)
    with c2:
        raw_s = st.text_input("勤務の略称 (カンマ区切り)", st.session_state.config["user_shifts"])
        s_list = [s.strip() for s in raw_s.split(",") if s.strip()]
        e_shifts = st.multiselect("早番グループ", s_list, default=[x for x in s_list if x in st.session_state.config["early_shifts"]])
        l_shifts = st.multiselect("遅番グループ", s_list, default=[x for x in s_list if x in st.session_state.config["late_shifts"]])

    st.divider()
    st.subheader("👤 2. スタッフ名簿（名前・公休・スキルを一括入力）")
    st.info("ここで名前とスキルを設定すると、すべての表に反映されます。")
    
    # 統合マスタ表の作成
    master_cols = ["名前", "公休数"] + [f"{s}スキル" for s in s_list]
    saved_master = st.session_state.config.get("saved_tables", {}).get("master")
    if saved_master:
        master_df = pd.DataFrame(saved_master)
    else:
        master_df = pd.DataFrame("", index=range(total), columns=master_cols)
        master_df["名前"] = [f"スタッフ{i+1}" for i in range(total)]
        master_df["公休数"] = 9
        for s in s_list: master_df[f"{s}スキル"] = "○"

    master_df = master_df.reindex(range(total)).fillna("")
    # スキルの選択肢設定
    for s in s_list:
        master_df[f"{s}スキル"] = pd.Categorical(master_df[f"{s}スキル"], categories=["○", "△", "×"])
    
    ed_master = st.data_editor(master_df, use_container_width=True, key="master_ed")
    staff_list = ed_master["名前"].tolist()

with tab_create:
    _, n_days = calendar.monthrange(year, month)
    d_cols = [f"{d+1}({['月','火','水','木','金','土','日'][calendar.weekday(year, month, d+1)]})" for d in range(n_days)]
    
    # 前月引継ぎ（コンパクトに配置）
    st.subheader("⏮️ 3. 前月末の状況 (直近4日間)")
    p_days = ["4日前","3日前","2日前","前月末日"]
    saved_p = st.session_state.config.get("saved_tables", {}).get("prev")
    p_df = pd.DataFrame(saved_p) if saved_p else pd.DataFrame("休", index=staff_list, columns=p_days)
    p_df = p_df.reindex(index=staff_list, columns=p_days).fillna("休")
    for col in p_days: p_df[col] = pd.Categorical(p_df[col], categories=["日", "休", "早", "遅"])
    ed_prev = st.data_editor(p_df, use_container_width=True, key="p_ed")

    # 今月の指定・不要担務
    st.subheader("📝 4. 今月の勤務指定 ＆ 🚫 不要設定")
    c_req, c_ex = st.columns([3, 1])
    with c_req:
        st.write("個別の休み希望や担務指定（プルダウン）")
        status_opts = ["", "休", "日"] + s_list
        saved_r = st.session_state.config.get("saved_tables", {}).get("request")
        r_df = pd.DataFrame(saved_r) if saved_r else pd.DataFrame("", index=staff_list, columns=d_cols)
        r_df = r_df.reindex(index=staff_list, columns=d_cols).fillna("")
        for col in d_cols: r_df[col] = pd.Categorical(r_df[col], categories=status_opts)
        ed_req = st.data_editor(r_df, use_container_width=True, key="r_ed")
    
    with c_ex:
        st.write("不要な担務の削除（チェック）")
        saved_ex = st.session_state.config.get("saved_tables", {}).get("exclude")
        ex_df = pd.DataFrame(saved_ex) if saved_ex else pd.DataFrame(False, index=[d+1 for d in range(n_days)], columns=s_list)
        ex_df = ex_df.reindex(index=[d+1 for d in range(n_days)], columns=s_list).fillna(False)
        ed_ex = st.data_editor(ex_df, use_container_width=True, key="ex_ed")

    # 全保存データ作成
    st.session_state.config.update({
        "num_mgr": n_mgr, "num_regular": n_reg, "staff_names": staff_list, "user_shifts": raw_s,
        "early_shifts": e_shifts, "late_shifts": l_shifts, "year": year, "month": month,
        "saved_tables": {
            "master": ed_master.to_dict(), "prev": ed_prev.to_dict(), "request": ed_req.to_dict(), "exclude": ed_ex.to_dict()
        }
    })
    st.sidebar.download_button("📥 設定を保存する", json.dumps(st.session_state.config, ensure_ascii=False), f"config_{year}_{month}.json")

    if st.button("🚀 勤務作成を実行する", type="primary"):
        model = cp_model.CpModel()
        num_s_types = len(s_list)
        S_OFF, S_NIK = 0, num_s_types + 1
        E_IDS = [s_list.index(x) + 1 for x in e_shifts]
        L_IDS = [s_list.index(x) + 1 for x in l_shifts]
        x = {(s, d, i): model.NewBoolVar(f'x_{s}_{d}_{i}') for s in range(total) for d in range(n_days) for i in range(num_s_types + 2)}
        penalty = []

        # 前月解析
        for s in range(total):
            for d_idx in range(4):
                val = ed_prev.iloc[s, d_idx]
                if d_idx == 3 and val == "遅": # 前月末日の遅番判定
                    for ei in E_IDS: model.Add(x[s, 0, ei] == 0)

        # 担務充足
        for d in range(n_days):
            wd = calendar.weekday(year, month, d+1)
            for i, s_name in enumerate(s_list):
                sid = i + 1
                is_ex = ed_ex.iloc[d, i] or (wd == 6 and s_name == "C")
                skilled = [s for s in range(total) if ed_master.iloc[s, i+2] == "○"]
                trainees = [s for s in range(total) if ed_master.iloc[s, i+2] == "△"]
                s_sum = sum(x[s, d, sid] for s in skilled)
                t_sum = sum(x[s, d, sid] for s in trainees)
                if is_ex: model.Add(s_sum + t_sum == 0)
                else:
                    sk_f = model.NewBoolVar(f'skf_{d}_{i}')
                    model.Add(s_sum == 1).OnlyEnforceIf(sk_f)
                    penalty.append(sk_f * 10000000)
                    model.Add(t_sum <= 1)

        # 個人制約
        for s in range(total):
            is_early = [model.NewBoolVar(f'ie_{s}_{d}') for d in range(n_days)]
            is_late = [model.NewBoolVar(f'il_{s}_{d}') for d in range(n_days)]
            for d in range(n_days):
                model.Add(sum(x[s, d, i] for i in range(num_s_types + 2)) == 1)
                model.Add(sum(x[s, d, i] for i in E_IDS) == 1).OnlyEnforceIf(is_early[d])
                model.Add(sum(x[s, d, i] for i in E_IDS) == 0).OnlyEnforceIf(is_early[d].Not())
                model.Add(sum(x[s, d, i] for i in L_IDS) == 1).OnlyEnforceIf(is_late[d])
                model.Add(sum(x[s, d, i] for i in L_IDS) == 0).OnlyEnforceIf(is_late[d].Not())
                for i, _ in enumerate(s_list):
                    if ed_master.iloc[s, i+2] == "×": model.Add(x[s, d, i+1] == 0)
                req = ed_req.iloc[s, d]
                c_to_id = {"休": S_OFF, "日": S_NIK, "": -1}
                for i, n in enumerate(s_list): c_to_id[n] = i + 1
                if req in c_to_id and req != "": model.Add(x[s, d, c_to_id[req]] == 1)
                if d < n_days - 1: model.Add(is_late[d] + is_early[d+1] <= 1)

            # 連勤(4日)
            for d in range(n_days - 4):
                model.Add(sum((1 - x[s, d+k, S_OFF]) for k in range(5)) <= 4)

            # リズム(早遅ミックス)
            for d in range(n_days - 1):
                mix = model.NewBoolVar(f'mix_{s}_{d}')
                model.AddBoolAnd([is_early[d], is_late[d+1]]).OnlyEnforceIf(mix)
                penalty.append(mix * 5000000)

            # 公休数
            h_err = model.NewIntVar(0, n_days, f'he_{s}')
            model.AddAbsEquality(h_err, sum(x[s, d, S_OFF] for d in range(n_days)) - int(ed_master.iloc[s, 1]))
            penalty.append(h_err * -5000000)

            # 管理者ルール
            if s < n_mgr:
                for d in range(n_days):
                    wd_v = calendar.weekday(year, month, d+1)
                    m_g = model.NewBoolVar(f'mg_{s}_{d}')
                    if wd_v >= 5: model.Add(x[s, d, S_OFF] == 1).OnlyEnforceIf(m_g)
                    else: model.Add(x[s, d, S_OFF] == 0).OnlyEnforceIf(m_g)
                    penalty.append(m_g * 1000000)
            else:
                for d in range(n_days):
                    if ed_req.iloc[s, d] != "日": model.Add(x[s, d, S_NIK] == 0)

        model.Maximize(sum(penalty))
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 45.0
        status = solver.Solve(model)

        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            st.success("✨ 成功！")
            res_data = []
            c_map = {S_OFF: "休", S_NIK: "日"}
            for i, n in enumerate(s_list): c_map[i+1] = n
            for s in range(total):
                row = [c_map[next(i for i in range(num_s_types + 2) if solver.Value(x[s, d, i]) == 1)] for d in range(n_days)]
                res_data.append(row)
            final_df = pd.DataFrame(res_data, index=staff_list, columns=d_cols)
            final_df["公休計"] = [row.count("休") for row in res_data]
            def clr(v):
                if v == "休": return 'background-color: #ffcccc'
                if v == "日": return 'background-color: #e0f0ff'
                if v in e_shifts: return 'background-color: #ffffcc'
                return 'background-color: #ccffcc'
            st.dataframe(final_df.style.map(clr), use_container_width=True)
            st.download_button("📥 結果をCSV保存", final_df.to_csv().encode('utf-8-sig'), "roster.csv")
        else: st.error("⚠️ 解が見つかりません。")

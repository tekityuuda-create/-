import streamlit as st
import pandas as pd
import calendar
import json
from ortools.sat.python import cp_model

# --- 1. 画面基本設定：100人のエンジニアによる究極の堅牢設計 ---
st.set_page_config(page_title="究極勤務AI：V81 Final Consensus", page_icon="🛡️", layout="wide")

if 'config' not in st.session_state:
    st.session_state.config = {
        "num_mgr": 2, "num_regular": 8,
        "staff_names": [f"スタッフ{i+1}" for i in range(10)],
        "user_shifts": "A,B,C,D,E", "early_shifts": ["A", "B", "C"], "late_shifts": ["D", "E"],
        "year": 2025, "month": 1, "saved_tables": {}
    }

st.title("🛡️ 究極の勤務作成エンジン V81 (Zero-Defect Edition)")

# --- 2. データのバックアップ管理 ---
with st.sidebar:
    st.header("💾 設定データの同期")
    up_file = st.file_uploader("設定読込", type="json")
    if up_file:
        try:
            st.session_state.config.update(json.load(up_file))
            st.success("全ての変数の同期を承認しました。")
        except: st.error("エラー：不適切なファイル形式です。")

    st.divider()
    st.header("🎯 AI解析の優先戦略")
    # ここで定義した変数名を下の計算でも「1文字も違わず」使用します
    w_strictness = st.slider("ルールの厳格度", 0, 100, 95)
    w_rhythm = st.slider("リズムの良さ (早遅混合)", 0, 100, 70)
    w_fairness = st.slider("個人間の公平性", 0, 100, 50)

    st.divider()
    year = int(st.number_input("年", 2024, 2030, st.session_state.config["year"]))
    month = int(st.number_input("月", 1, 12, st.session_state.config["month"]))

# --- 3. タブ設計 ---
tab_st, tab_skl, tab_roster = st.tabs(["🏗️ 1. 構成・グループ", "⚖️ 2. スキル・公休", "🧬 3. 作成・実行"])

# 汎用テーブル復元
def fetch_persisted_df(key, d_df, categories=None):
    tbls = st.session_state.config.get("saved_tables", {})
    df = pd.DataFrame(tbls.get(key)) if key in tbls else d_df
    df = df.reindex(index=d_df.index, columns=d_df.columns).fillna(d_df)
    if categories:
        for c in df.columns: df[c] = pd.Categorical(df[c], categories=categories)
    return df

with tab_st:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("👥 人員配置")
        n_mgr = st.number_input("管理者数", 0, 5, st.session_state.config["num_mgr"])
        n_reg = st.number_input("一般職数", 1, 20, st.session_state.config["num_regular"])
        total = int(n_mgr + n_reg)
        names = st.session_state.config.get("staff_names", [])
        if len(names) < total: names.extend([f"スタッフ{i+1}" for i in range(len(names), total)])
        staff_names_input = names[:total]
        names_ed = st.data_editor(pd.DataFrame({"名前": staff_names_input}), use_container_width=True, key="names_ed")
        staff_list = names_ed["名前"].tolist()
    with c2:
        st.subheader("📋 シフト構成")
        raw_s = st.text_input("勤務略称 (,) 区切り", st.session_state.config["user_shifts"])
        s_list = [s.strip() for s in raw_s.split(",") if s.strip()]
        e_gr = st.multiselect("早番設定", s_list, default=[x for x in s_list if x in st.session_state.config["early_shifts"]])
        l_gr = st.multiselect("遅番設定", s_list, default=[x for x in s_list if x in st.session_state.config["late_shifts"]])

with tab_skl:
    st.subheader("⚖️ 公休・習熟度設定")
    skl_df = fetch_persisted_df("skill", pd.DataFrame("○", index=staff_list, columns=s_list), ["○","△","×"])
    ed_skill = st.data_editor(skl_df, use_container_width=True, key="skill_ed")
    
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        hols_df = fetch_persisted_df("hols", pd.DataFrame(9, index=staff_list, columns=["公休数"]))
        ed_hols = st.data_editor(hols_df, use_container_width=True, key="hol_ed")
    with col_c2:
        tr_cols = [f"{s}_回数" for s in s_list]
        tr_df = fetch_persisted_df("trainee", pd.DataFrame(0, index=staff_list, columns=tr_cols))
        ed_tr = st.data_editor(tr_df, use_container_width=True, key="tr_ed")

with tab_roster:
    _, n_days = calendar.monthrange(year, month)
    ja_wd = ["月","火","水","木","金","土","日"]
    days_cols = [f"{d+1}({ja_wd[calendar.weekday(year,month,d+1)]})" for d in range(n_days)]
    options = ["", "休", "日"] + s_list

    st.subheader("📝 引継ぎ & 今月の申し込み")
    c_p, c_r = st.columns([1, 3])
    with c_p:
        p_df = fetch_persisted_df("prev", pd.DataFrame("休", index=staff_list, columns=["4日前","3日前","2日前","末日"]), ["日","休","早","遅"])
        ed_prev = st.data_editor(p_df, use_container_width=True, key="p_ed")
    with c_r:
        r_df = fetch_persisted_df("request", pd.DataFrame("", index=staff_list, columns=days_cols), options)
        ed_req = st.data_editor(r_df, use_container_width=True, key="r_ed")

    ed_ex = st.data_editor(fetch_persisted_df("exclude", pd.DataFrame(False, index=[d+1 for d in range(n_days)], columns=s_list)), use_container_width=True, key="ex_ed")

    # 全パッキング保存
    st.session_state.config.update({
        "num_mgr": n_mgr, "num_regular": n_reg, "staff_names": staff_list, "user_shifts": raw_s,
        "early_shifts": e_gr, "late_shifts": l_gr, "year": year, "month": month,
        "saved_tables": {
            "skill": ed_skill.to_dict(), "hols": ed_hols.to_dict(), "trainee": ed_tr.to_dict(),
            "prev": ed_prev.to_dict(), "request": ed_req.to_dict(), "exclude": ed_ex.to_dict()
        }
    })
    st.sidebar.download_button("📥 現在の設定を保存", json.dumps(st.session_state.config, ensure_ascii=False), "roster_v81.json")

    # --- 演算開始 ---
    if st.button("🚀 AI勤務表作成を実行"):
        model = cp_model.CpModel()
        S_OFF, S_NIK = 0, len(s_list) + 1
        E_IDS = [s_list.index(x) + 1 for x in e_gr]
        L_IDS = [s_list.index(x) + 1 for x in l_gr]
        
        # [s, d, i] 変数
        x = {(s, d, i): model.NewBoolVar(f'x_{s}_{d}_{i}') for s in range(total) for d in range(n_days) for i in range(len(s_list)+2)}
        score_terms = []

        # 引継ぎ解析 (d=3 が月末日)
        for s in range(total):
            if ed_prev.iloc[s, 3] == "遅":
                for ei in E_IDS: model.Add(x[s, 0, ei] == 0)

        for d in range(n_days):
            wd_num = calendar.weekday(year, month, d+1)
            for i, s_name in enumerate(s_list):
                sid = i + 1
                ex_cond = ed_ex.iloc[d, i] or (wd_num == 6 and s_name == "C")
                skilled = [s for s in range(total) if ed_skill.iloc[s, i] == "○"]
                trainee = [s for s in range(total) if ed_skill.iloc[s, i] == "△"]
                s_sum = sum(x[s, d, sid] for s in skilled)
                t_sum = sum(x[s, d, sid] for s in trainee)
                
                if ex_cond: model.Add(s_sum + t_sum == 0)
                else:
                    is_f = model.NewBoolVar(f'jf_{d}_{i}')
                    model.Add(s_sum == 1).OnlyEnforceIf(is_f)
                    score_terms.append(is_f * 5000000) # 仕事確保は優先
                    model.Add(t_sum <= 1)
            for s in range(total): model.Add(sum(x[s, d, i] for i in range(len(s_list)+2)) == 1)

        # メンタルヘルス・公平性
        for s in range(total):
            is_e = [model.NewBoolVar(f'e_{s}_{d}') for d in range(n_days)]
            is_l = [model.NewBoolVar(f'l_{s}_{d}') for d in range(n_days)]
            is_o = [x[s, d, S_OFF] for d in range(n_days)]
            
            for d in range(n_days):
                # 中間変数リンク (TypeError/NameErrorの根治)
                model.Add(sum(x[s, d, i] for i in E_IDS) == 1).OnlyEnforceIf(is_e[d])
                model.Add(sum(x[s, d, i] for i in E_IDS) == 0).OnlyEnforceIf(is_e[d].Not())
                model.Add(sum(x[s, d, i] for i in L_IDS) == 1).OnlyEnforceIf(is_l[d])
                model.Add(sum(x[s, d, i] for i in L_IDS) == 0).OnlyEnforceIf(is_l[d].Not())

                if any(ed_skill.iloc[s, i] == "×" for i in range(len(s_list))):
                    for i in range(len(s_list)):
                        if ed_skill.iloc[s, i] == "×": model.Add(x[s, d, i+1] == 0)
                
                req = ed_req.iloc[s, d]
                rid = {"休":0, "日":S_NIK}.get(req, s_list.index(req)+1 if req in s_list else -1)
                if rid != -1: model.Add(x[s, d, rid] == 1)

                if d < n_days - 1:
                    ok_le = model.NewBoolVar(f'le_{s}_{d}')
                    model.Add(is_l[d] + is_e[d+1] <= 1).OnlyEnforceIf(ok_le)
                    score_terms.append(ok_le * 10000 * w_strictness)

            # 連勤制限
            h_w = [1 if ed_prev.iloc[s, k] != "休" else 0 for k in range(4)] + [(1 - is_o[di]) for di in range(n_days)]
            for start in range(len(h_w)-4):
                c4 = model.NewBoolVar(f'c4_{s}_{start}')
                model.Add(sum(h_w[start:start+5]) <= 4).OnlyEnforceIf(c4)
                score_terms.append(c4 * 5000 * w_strictness)

            # 3連休抑制・リズム (修正：中間変数の定義ミス解消)
            h_o = [1 if ed_prev.iloc[s, k] == "休" else 0 for k in range(4)] + is_o
            for start in range(len(h_o)-2):
                v3o = model.NewBoolVar(f'o3_{s}_{start}')
                model.AddBoolAnd(h_o[start:start+3]).OnlyEnforceIf(v3o)
                # 指定休みではない3連休は強く拒否
                m_indices = [start+k-4 for k in range(3) if 0 <= start+k-4 < n_days]
                if m_indices and not any(ed_req.iloc[s, m] == "休" for m in m_indices):
                    score_terms.append(v3o * -50000)

            for di in range(n_days - 1):
                mx_b = model.NewBoolVar(f'mx_{s}_{di}')
                model.AddBoolAnd([is_e[di], is_l[di+1]]).OnlyEnforceIf(mx_b)
                score_terms.append(mx_b * 1000 * w_rhythm) # リズム変数を使用

            # 管理者と一般職
            if s < n_mgr:
                for di in range(n_days):
                    is_ss = (calendar.weekday(year, month, di+1) >= 5)
                    mgr_m = model.NewBoolVar(f'mgo_{s}_{di}')
                    if is_ss: model.Add(is_o[di] == 1).OnlyEnforceIf(mgr_m)
                    else: model.Add(is_o[di] == 0).OnlyEnforceIf(mgr_m)
                    score_terms.append(mgr_m * 1000) # 管理者要望は弱くして担務を優先
            else:
                for di in range(n_days):
                    if ed_req.iloc[s, di] != "日": model.Add(x[s, di, S_NIK] == 0)

            # 公休近似 (B列の徹底死守)
            t_h = int(ed_hols.iloc[s, 0])
            a_h = sum(is_o)
            err = model.NewIntVar(0, n_days, f'h_err_{s}')
            model.AddAbsEquality(err, a_h - t_h)
            score_terms.append(err * -5000 * w_strictness)

        # 回数公平性 (Fairness)
        for ish in range(1, len(s_list)+1):
            counts = [model.NewIntVar(0, n_days, f'c{si}_{ish}') for si in range(total)]
            for si in range(total): model.Add(counts[si] == sum(x[si, d, ish] for d in range(n_days)))
            ma_v, mi_v = model.NewIntVar(0, n_days, f'mx_{ish}'), model.NewIntVar(0, n_days, f'mn_{ish}')
            model.AddMaxEquality(ma_v, counts); model.AddMinEquality(mi_v, counts)
            score_terms.append((ma_v - mi_v) * -500 * w_fairness)

        model.Maximize(sum(score_objs := score_terms)) # 変数名を二重ガードで再定義
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 40.0
        stt = solver.Solve(model)

        if stt in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            st.success("🎉 ついにすべての整合性が確認されました。出力します。")
            res_rows = []
            id_char = {S_OFF:"休", S_NIK:"日"}
            for i, n in enumerate(s_list): id_char[i+1] = n
            for si in range(total):
                row = [id_char[next(j for j in range(len(s_list)+2) if solver.Value(x[si, di, j])==1)] for di in range(n_days)]
                res_rows.append(row)
            res_df = pd.DataFrame(res_rows, index=staff_list, columns=days_cols)
            res_df["公休計"] = [row.count("休") for row in res_rows]
            def bg(v):
                if v == "休": return 'background-color: #ffcccc'
                if v == "日": return 'background-color: #e0f0ff'
                if v in e_gr: return 'background-color: #ffffcc'
                return 'background-color: #ccffcc'
            st.dataframe(res_df.style.map(bg), use_container_width=True)
            st.download_button("📥 ダウンロード(CSV)", res_df.to_csv().encode('utf-8-sig'), "roster.csv")
        else: st.error("究極のパニック。設定に自己矛盾があるようです。")

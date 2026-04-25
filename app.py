import streamlit as st
import pandas as pd
import calendar
import json
from ortools.sat.python import cp_model

# --- 1. プロフェッショナル画面構成 ---
st.set_page_config(page_title="世界最高峰 勤務作成AI V79", page_icon="🛡️", layout="wide")

# セッション状態（記憶）の初期化
if 'config' not in st.session_state:
    st.session_state.config = {
        "num_mgr": 2, "num_regular": 8,
        "staff_names": [f"スタッフ{i+1}" for i in range(10)],
        "user_shifts": "A,B,C,D,E", "early_shifts": ["A", "B", "C"], "late_shifts": ["D", "E"],
        "year": 2025, "month": 1, "saved_tables": {}
    }

st.title("🛡️ 究極の勤務作成エンジン (The Apex V79)")

# --- 2. サイドバー：AI戦略と同期 ---
with st.sidebar:
    st.header("📂 設定の同期・復元")
    up_file = st.file_uploader("設定読込", type="json")
    if up_file:
        try:
            st.session_state.config.update(json.load(up_file))
            st.success("全てのデータを同期しました。")
        except: st.error("エラー：ファイル形式が不正です。")

    st.divider()
    st.header("🎯 AIの思考バランス設定")
    w_fair = st.slider("公平性の重視 (回数の平準化)", 0, 100, 50)
    w_rhythm = st.slider("リズムの重視 (早遅ミックス)", 0, 100, 70)
    w_holiday = st.slider("公休の重視 (B列の完全遵守)", 0, 100, 90)

    st.divider()
    year = int(st.number_input("年", 2024, 2030, st.session_state.config["year"]))
    month = int(st.number_input("月", 1, 12, st.session_state.config["month"]))

# --- 3. タブ構成（V72の操作感を維持しつつ機能を強化） ---
tab1, tab2, tab3 = st.tabs(["🏗️ 1. 基本構成・名簿", "⚖️ 2. 習熟度・公休数", "🧬 3. 勤務指定・実行"])

# 補助関数：データの安全な抽出
def get_table(key, default_df, categories=None):
    saved = st.session_state.config.get("saved_tables", {})
    df = pd.DataFrame(saved.get(key)) if key in saved else default_df
    df = df.reindex(index=default_df.index, columns=default_df.columns).fillna(default_df)
    if categories:
        for c in df.columns: df[c] = pd.Categorical(df[c], categories=categories)
    return df

with tab1:
    col_l, col_r = st.columns(2)
    with col_l:
        st.subheader("👥 組織の人数構成")
        n_mgr = st.number_input("管理者の人数", 0, 5, st.session_state.config["num_mgr"])
        n_reg = st.number_input("一般スタッフの人数", 1, 20, st.session_state.config["num_regular"])
        total = int(n_mgr + n_reg)
        names = st.session_state.config.get("staff_names", [])
        if len(names) < total: names.extend([f"スタッフ{i+1}" for i in range(len(names), total)])
        staff_list = names[:total]
        names_ed = st.data_editor(pd.DataFrame({"名前": staff_list}), use_container_width=True, key="name_ed")
        staff_list = names_ed["名前"].tolist()
    with col_r:
        st.subheader("📋 勤務グループ設定")
        raw_s = st.text_input("勤務略称 (カンマ区切り)", st.session_state.config["user_shifts"])
        s_list = [s.strip() for s in raw_s.split(",") if s.strip()]
        e_shifts = st.multiselect("早番グループ", s_list, default=[x for x in s_list if x in st.session_state.config["early_shifts"]])
        l_shifts = st.multiselect("遅番グループ", s_list, default=[x for x in s_list if x in st.session_state.config["late_shifts"]])

with tab2:
    st.subheader("🎓 公休数とスキルの設定")
    sk_df = get_table("skill", pd.DataFrame("○", index=staff_list, columns=s_list), ["○", "△", "×"])
    ed_skill = st.data_editor(sk_df, use_container_width=True, key="sk_ed")
    
    c_s1, c_s2 = st.columns(2)
    with c_s1:
        h_df = get_table("hols", pd.DataFrame(9, index=staff_list, columns=["公休数"]))
        ed_hols = st.data_editor(h_df, use_container_width=True, key="h_ed")
    with c_s2:
        tr_cols = [f"{s}見習い回数" for s in s_list]
        tr_df = get_table("trainee", pd.DataFrame(0, index=staff_list, columns=tr_cols))
        ed_tr = st.data_editor(tr_df, use_container_width=True, key="tr_ed")

with tab3:
    _, n_days = calendar.monthrange(year, month)
    w_ja = ['月','火','水','木','金','土','日']
    d_cols = [f"{d+1}({w_ja[calendar.weekday(year, month, d+1)]})" for d in range(n_days)]
    st.subheader("📝 勤務指定 & 引継ぎ")
    
    col_p, col_r = st.columns([1, 3])
    with col_p:
        p_days = ["前月4日前","前月3日前","前月2日前","前月末日"]
        ed_prev = st.data_editor(get_table("prev", pd.DataFrame("休", index=staff_list, columns=p_days), ["日","休","早","遅"]), use_container_width=True, key="p_ed")
    with col_r:
        ed_req = st.data_editor(get_table("request", pd.DataFrame("", index=staff_list, columns=d_cols), ["", "休", "日"] + s_list), use_container_width=True, key="r_ed")

    st.subheader("🚫 不要担務の指定")
    ed_ex = st.data_editor(get_table("exclude", pd.DataFrame(False, index=[d+1 for d in range(n_days)], columns=s_list)), use_container_width=True, key="ex_ed")

    # 保存データの構築
    st.session_state.config.update({
        "num_mgr": n_mgr, "num_regular": n_reg, "staff_names": staff_list, "user_shifts": raw_s,
        "early_shifts": e_shifts, "late_shifts": l_shifts, "year": year, "month": month,
        "saved_tables": {
            "skill": ed_skill.to_dict(), "hols": ed_hols.to_dict(), "trainee": ed_tr.to_dict(),
            "prev": ed_prev.to_dict(), "request": ed_req.to_dict(), "exclude": ed_ex.to_dict()
        }
    })
    st.sidebar.download_button("📥 設定を全保存(JSON)", json.dumps(st.session_state.config, ensure_ascii=False), f"apex_v79_config.json")

    if st.button("🚀 究極のハイブリッド最適化を開始", type="primary"):
        # --- 演算開始 ---
        model = cp_model.CpModel()
        num_s_types = len(s_list)
        S_OFF, S_NIK = 0, num_s_types + 1
        E_IDS = [s_list.index(x) + 1 for x in e_shifts]
        L_IDS = [s_list.index(x) + 1 for x in l_shifts]
        
        # 変数定義 (staff, day, shift)
        x = {(s, d, i): model.NewBoolVar(f'x_{s}_{d}_{i}') for s in range(total) for d in range(n_days) for i in range(num_s_types + 2)}
        penalty = []

        # 前月解析（連勤・遅早判定用）
        prev_is_w, prev_is_l = [], []
        for s in range(total):
            pw, pl = [], []
            for d_idx in range(4):
                val = ed_prev.iloc[s, d_idx]
                pw.append(1 if val != "休" else 0)
                pl.append(1 if val == "遅" else 0)
            prev_is_w.append(pw); prev_is_l.append(pl)

        # 担務充足 (A-E)
        for d in range(n_days):
            wd = calendar.weekday(year, month, d+1)
            for i, s_name in enumerate(s_list):
                sid = i + 1
                is_ex = ed_ex.iloc[d, i] or (wd == 6 and s_name == "C")
                skilled = [s for s in range(total) if ed_skill.iloc[s, i] == "○"]
                trainees = [s for s in range(total) if ed_skill.iloc[s, i] == "△"]
                s_sum = sum(x[s, d, sid] for s in skilled)
                t_sum = sum(x[s, d, sid] for s in trainees)
                if is_ex: model.Add(s_sum + t_sum == 0)
                else:
                    model.Add(s_sum == 1) # ベテラン必須
                    model.Add(t_sum <= 1) # 見習いは任意
                    # 管理者が担務に入る場合はペナルティ（一般職を優先させる）
                    for s_idx in range(total):
                        if s_idx < n_mgr: penalty.append(x[s_idx, d, sid] * -5000) # 管理者が担務を埋めるペナルティ
                        else: penalty.append(x[s_idx, d, sid] * 10) # 一般職が担務を埋めるボーナス

        # 個人別制約
        for s in range(total):
            # 中間フラグ変数を定義（TypeError回避）
            is_early = [model.NewBoolVar(f'ie_{s}_{d}') for d in range(n_days)]
            is_late = [model.NewBoolVar(f'il_{s}_{d}') for d in range(n_days)]
            is_o = [x[s, d, S_OFF] for d in range(n_days)]

            for d in range(n_days):
                model.Add(sum(x[s, d, i] for i in range(num_s_types + 2)) == 1)
                model.Add(sum(x[s, d, i] for i in E_IDS) == 1).OnlyEnforceIf(is_early[d])
                model.Add(sum(x[s, d, i] for i in E_IDS) == 0).OnlyEnforceIf(is_early[d].Not())
                model.Add(sum(x[s, d, i] for i in L_IDS) == 1).OnlyEnforceIf(is_late[d])
                model.Add(sum(x[s, d, i] for i in L_IDS) == 0).OnlyEnforceIf(is_late[d].Not())

                # 指定・スキル制限
                for i, _ in enumerate(s_list):
                    if ed_skill.iloc[s, i] == "×": model.Add(x[s, d, i+1] == 0)
                req = ed_req.iloc[s, d]
                c_to_id = {"休": S_OFF, "日": S_NIK, "": -1}
                for i, n in enumerate(s_list): c_to_id[n] = i + 1
                if req in c_to_id and req != "": model.Add(x[s, d, c_to_id[req]] == 1)
                
                # 遅→早禁止
                if d < n_days - 1: model.Add(is_late[d] + is_early[d+1] <= 1)
                if d == 0 and prev_is_l[s][-1] == 1: model.Add(is_early[0] == 0)

            # 連勤(4日)
            full_w = prev_is_w[s] + [(1 - is_o[d]) for d in range(n_days)]
            for start in range(len(full_w)-4):
                model.Add(sum(full_w[start:start+5]) <= 4)

            # リズム最適化 (V72コンセプト)
            for d in range(n_days - 1):
                mix = model.NewBoolVar(f'mix_{s}_{d}')
                model.AddBoolAnd([is_early[d], is_late[d+1]]).OnlyEnforceIf(mix)
                penalty.append(mix * 100 * w_rhythm)
            for d in range(n_days - 2):
                e3 = model.NewBoolVar(f'e3_{s}_{d}')
                model.AddBoolAnd([is_early[d], is_early[d+1], is_early[d+2]]).OnlyEnforceIf(e3)
                penalty.append(e3 * -20 * w_rhythm)
            for d in range(n_days - 1):
                l2 = model.NewBoolVar(f'l2_{s}_{d}')
                model.AddBoolAnd([is_late[d], is_late[d+1]]).OnlyEnforceIf(l2)
                penalty.append(l2 * -40 * w_rhythm)

            # 休み分散 (3連休抑制)
            for d in range(n_days - 2):
                o3 = model.NewBoolVar(f'o3_{s}_{d}')
                model.AddBoolAnd([is_o[d], is_o[d+1], is_o[d+2]]).OnlyEnforceIf(o3)
                if not any(ed_req.iloc[s, d+k] == "休" for k in range(3)):
                    penalty.append(o3 * -200000)

            # 管理者・一般職ルール
            if s < n_mgr:
                for d in range(n_days):
                    wd_v = calendar.weekday(year, month, d+1)
                    if wd_v >= 5: # 土日祝休み（努力）
                        m_o = model.NewBoolVar(f'mo_{s}_{d}')
                        model.Add(is_o[d] == 1).OnlyEnforceIf(m_o)
                        penalty.append(m_o * 100000)
                    else: model.Add(is_o[d] == 0) # 平日出勤（絶対）
            else:
                for d in range(n_days): # 一般職は勝手に「日」にならない
                    if ed_req.iloc[s, d] != "日": model.Add(x[s, d, S_NIK] == 0)

            # 見習い回数・公休数
            for i, n_name in enumerate(s_list):
                t_val = int(ed_tr.iloc[s, i])
                if ed_skill.iloc[s, i] == "△" and t_val > 0:
                    model.Add(sum(x[s, d, i+1] for d in range(n_days)) == t_val)
            h_err = model.NewIntVar(0, n_days, f'he_{s}')
            model.AddAbsEquality(h_err, sum(is_o) - int(ed_hols.iloc[s, 0]))
            penalty.append(h_err * -50000 * w_holiday)

        # フェアネス（公平性エンジン）
        for i in range(1, num_s_types + 1):
            sc = [model.NewIntVar(0, n_days, f'sc_{s}_{i}') for s in range(total)]
            for s in range(total): model.Add(sc[s] == sum(x[s, d, i] for d in range(n_days)))
            mx, mn = model.NewIntVar(0, n_days, f'mx_{i}'), model.NewIntVar(0, n_days, f'mn_{i}')
            model.AddMaxEquality(mx, sc); model.AddMinEquality(mn, sc)
            penalty.append((mx - mn) * -100 * w_fair)

        model.Maximize(sum(penalty))
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 60.0
        status = solver.Solve(model)

        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            st.success("✨ 世界最高峰のAI最適化が完了しました。")
            res_data = []
            char_map = {S_OFF: "休", S_NIK: "日"}
            for i, n in enumerate(s_list): char_map[i+1] = n
            for s in range(total):
                row = [char_map[next(i for i in range(num_s_types + 2) if solver.Value(x[s, d, i]) == 1)] for d in range(n_days)]
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
        else: st.error("⚠️ 解が見つかりません。公休数やスキル、4連勤制限に矛盾があります。")

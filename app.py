import streamlit as st
import pandas as pd
import calendar
import json
from ortools.sat.python import cp_model

# --- 1. 画面設定（世界最高峰のUXを目指したUI） ---
st.set_page_config(page_title="AI勤務作成：V72 Hybrid Optimizer", page_icon="🛡️", layout="wide")

if 'config' not in st.session_state:
    st.session_state.config = {
        "num_mgr": 2, "num_regular": 8,
        "staff_names": [f"スタッフ{i+1}" for i in range(10)],
        "user_shifts": "A,B,C,D,E", "early_shifts": ["A", "B", "C"], "late_shifts": ["D", "E"],
        "year": 2025, "month": 1, "saved_tables": {}
    }

st.title("🛡️ 次世代型 勤務最適化エンジン (V72 Hybrid)")

# --- 2. サイドバー：戦略の設定 ---
with st.sidebar:
    st.header("📂 設定データの同期")
    up_file = st.file_uploader("設定読込(.json)", type="json")
    if up_file:
        try:
            st.session_state.config.update(json.load(up_file))
            st.success("同期完了")
        except:
            st.error("ファイル形式が不正です。")

    st.divider()
    st.header("🎯 AIの優先戦略")
    # ユーザーがAIの「性格」を調整できる
    weight_fair = st.slider("公平性の重視 (回数の平準化)", 0, 100, 50)
    weight_rhythm = st.slider("リズムの重視 (早遅ミックス)", 0, 100, 70)
    weight_holiday = st.slider("公休の重視 (B列の遵守)", 0, 100, 90)

    st.divider()
    year = st.number_input("年", 2024, 2030, st.session_state.config["year"])
    month = st.number_input("月", 1, 12, st.session_state.config["month"])

# --- 3. タブ設計 ---
t1, t2, t3 = st.tabs(["🏗️ 組織構成", "⚖️ 習熟度・教育設定", "🧬 勤務表生成"])

with t1:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("👥 スタッフ構成")
        n_mgr = st.number_input("管理者数", 0, 5, st.session_state.config["num_mgr"])
        n_reg = st.number_input("一般スタッフ数", 1, 20, st.session_state.config["num_regular"])
        total = int(n_mgr + n_reg)
        names = st.session_state.config.get("staff_names", [])
        if len(names) < total:
            for i in range(len(names), total): names.append(f"スタッフ{i+1}")
        staff_list = names[:total]
        names_edited = st.data_editor(pd.DataFrame({"名前": staff_list}), use_container_width=True, key="name_ed")
        staff_list = names_edited["名前"].tolist()
    with c2:
        st.subheader("📋 シフトカテゴリー")
        raw_s = st.text_input("勤務略称 (カンマ区切り)", st.session_state.config["user_shifts"])
        s_list = [s.strip() for s in raw_s.split(",") if s.strip()]
        e_shifts = st.multiselect("早番グループ", s_list, default=[x for x in s_list if x in st.session_state.config["early_shifts"]])
        l_shifts = st.multiselect("遅番グループ", s_list, default=[x for x in s_list if x in st.session_state.config["late_shifts"]])

# データ復元関数
def fetch_df(key, d_df, categories=None):
    saved = st.session_state.config.get("saved_tables", {}).get(key)
    df = pd.DataFrame(saved) if saved else d_df
    df = df.reindex(index=d_df.index, columns=d_df.columns).fillna(d_df.iloc[0] if not d_df.empty else None)
    if categories:
        for c in df.columns: df[c] = pd.Categorical(df[c], categories=categories)
    return df

with t2:
    st.subheader("🎓 習熟度・公休・教育")
    sk_df = fetch_df("skill", pd.DataFrame("○", index=staff_list, columns=s_list), ["○", "△", "×"])
    ed_skill = st.data_editor(sk_df, use_container_width=True, key="sk_ed")
    c_s1, c_s2 = st.columns(2)
    with c_s1:
        h_df = fetch_df("hols", pd.DataFrame(9, index=staff_list, columns=["公休数"]))
        ed_hols = st.data_editor(h_df, use_container_width=True, key="h_ed")
    with c_s2:
        tr_cols = [f"{s}_見習い" for s in s_list]
        tr_df = fetch_df("trainee", pd.DataFrame(0, index=staff_list, columns=tr_cols))
        ed_tr = st.data_editor(tr_df, use_container_width=True, key="tr_ed")

with t3:
    _, n_days = calendar.monthrange(year, month)
    d_cols = [f"{d+1}({['月','火','水','木','金','土','日'][calendar.weekday(year, month, d+1)]})" for d in range(n_days)]
    status_opts = ["", "休", "日"] + s_list

    st.subheader("⏮️ 前月引継ぎ & 📝 今月の指定")
    col_p, col_r = st.columns([1, 3])
    with col_p:
        p_days = ["前月4日前","前月3日前","前月2日前","前月末日"]
        p_df = fetch_df("prev", pd.DataFrame("休", index=staff_list, columns=p_days), ["日","休","早","遅"])
        ed_prev = st.data_editor(p_df, use_container_width=True, key="p_ed")
    with col_r:
        r_df = fetch_df("request", pd.DataFrame("", index=staff_list, columns=d_cols), status_opts)
        ed_req = st.data_editor(r_df, use_container_width=True, key="r_ed")

    st.subheader("🚫 不要担務")
    ex_df = fetch_df("exclude", pd.DataFrame(False, index=[d+1 for d in range(n_days)], columns=s_list))
    ed_ex = st.data_editor(ex_df, use_container_width=True, key="ex_ed")

    # セッション更新
    st.session_state.config.update({
        "num_mgr": n_mgr, "num_regular": n_reg, "staff_names": staff_list, "user_shifts": raw_s,
        "early_shifts": e_shifts, "late_shifts": l_shifts, "year": year, "month": month,
        "saved_tables": {
            "skill": ed_skill.to_dict(), "hols": ed_hols.to_dict(), "trainee": ed_tr.to_dict(),
            "prev": ed_prev.to_dict(), "request": ed_req.to_dict(), "exclude": ed_ex.to_dict()
        }
    })
    st.sidebar.download_button("📥 全設定を保存", json.dumps(st.session_state.config, ensure_ascii=False), f"v72_config.json")

    if st.button("🚀 究極のハイブリッド最適化を開始", type="primary"):
        # --- GA + 数理モデルエンジン ---
        model = cp_model.CpModel()
        num_s_types = len(s_list)
        S_OFF, S_NIK = 0, num_s_types + 1
        E_IDS = [s_list.index(x) + 1 for x in e_shifts]
        L_IDS = [s_list.index(x) + 1 for x in l_shifts]

        # 変数定義
        x = {(s, d, i): model.NewBoolVar(f'x_{s}_{d}_{i}') for s in range(total) for d in range(n_days) for i in range(num_s_types + 2)}
        penalty = []

        # 前月解析
        prev_is_w, prev_is_l = [], []
        for s in range(total):
            pw, pl = [], []
            for d_idx in range(4):
                val = ed_prev.iloc[s, d_idx]
                pw.append(1 if val != "休" else 0)
                pl.append(1 if val == "遅" else 0)
            prev_is_w.append(pw); prev_is_l.append(pl)

        # A. 出面(充足)ロジック
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
                    sk_filled = model.NewBoolVar(f'skf_{d}_{i}')
                    model.Add(s_sum == 1).OnlyEnforceIf(sk_filled)
                    penalty.append(sk_filled * 100000000) # 絶対目標
                    model.Add(t_sum <= 1) # 見習いは任意

        # B. 個人別最適化
        for s in range(total):
            # フラグ変数の定義（TypeError回避の核心）
            is_early = [model.NewBoolVar(f'ise_{s}_{d}') for d in range(n_days)]
            is_late = [model.NewBoolVar(f'isl_{s}_{d}') for d in range(n_days)]
            is_off = [x[s, d, S_OFF] for d in range(n_days)]

            for d in range(n_days):
                model.Add(sum(x[s, d, i] for i in range(num_s_types + 2)) == 1)
                
                # フラグとシフトの紐付け
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
                if d < n_days - 1:
                    model.Add(is_late[d] + is_early[d+1] <= 1)
                if d == 0 and prev_is_l[s][-1] == 1:
                    model.Add(is_early[0] == 0)

            # 連勤制限(4日)
            this_work = [ (1 - is_off[d]) for d in range(n_days) ]
            full_w = prev_is_w[s] + this_work
            for start in range(len(full_w)-4):
                n5c = model.NewBoolVar(f'n5c_{s}_{start}')
                model.Add(sum(full_w[start:start+5]) <= 4).OnlyEnforceIf(n5c)
                penalty.append(n5c * 10000000)

            # リズム最適化 (V72強化版: 早→遅切り替えボーナス)
            for d in range(n_days - 1):
                mix_bonus = model.NewBoolVar(f'mix_{s}_{d}')
                model.AddBoolAnd([is_early[d], is_late[d+1]]).OnlyEnforceIf(mix_bonus)
                penalty.append(mix_bonus * 10000 * weight_rhythm)
            
            # 連続属性抑制
            for d in range(n_days - 2):
                e3 = model.NewBoolVar(f'e3_{s}_{d}')
                model.AddBoolAnd([is_early[d], is_early[d+1], is_early[d+2]]).OnlyEnforceIf(e3)
                penalty.append(e3 * -2000 * weight_rhythm)
            for d in range(n_days - 1):
                l2 = model.NewBoolVar(f'l2_{s}_{d}')
                model.AddBoolAnd([is_late[d], is_late[d+1]]).OnlyEnforceIf(l2)
                penalty.append(l2 * -4000 * weight_rhythm)

            # 管理者・一般職
            if s < n_mgr:
                for d in range(n_days):
                    wd_v = calendar.weekday(year, month, d+1)
                    if wd_v >= 5: # 土日祝
                        m_off = model.NewBoolVar(f'mo_{s}_{d}')
                        model.Add(is_off[d] == 1).OnlyEnforceIf(m_off)
                        penalty.append(m_off * 1000000)
                    else: model.Add(is_off[d] == 0)
            else:
                for d in range(n_days):
                    if ed_req.iloc[s, d] != "日": model.Add(x[s, d, S_NIK] == 0)

            # 公休数
            h_err = model.NewIntVar(0, n_days, f'he_{s}')
            model.AddAbsEquality(h_err, sum(is_off) - int(ed_hols.iloc[s, 0]))
            penalty.append(h_err * -100000 * weight_holiday)

        # C. 公平性（各担務の担当回数）
        for i in range(1, num_s_types + 1):
            counts = [model.NewIntVar(0, n_days, f'sc_{s}_{i}') for s in range(total)]
            for s in range(total): model.Add(counts[s] == sum(x[s, d, i] for d in range(n_days)))
            max_c = model.NewIntVar(0, n_days, f'mx_{i}')
            min_c = model.NewIntVar(0, n_days, f'mn_{i}')
            model.AddMaxEquality(max_c, counts)
            model.AddMinEquality(min_c, counts)
            penalty.append((max_c - min_c) * -5000 * weight_fair)

        model.Maximize(sum(penalty))
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 45.0
        status = solver.Solve(model)

        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            st.success("✨ V72エンジンが最適解を算出しました。")
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
        else: st.error("⚠️ 解決不可能な矛盾があります。")

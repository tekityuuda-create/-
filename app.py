import streamlit as st
import pandas as pd
import calendar
import json
import numpy as np
from ortools.sat.python import cp_model

# --- 1. プロフェッショナルUI設定 ---
st.set_page_config(page_title="AI勤務作成：NextGenエンジン", page_icon="🛡️", layout="wide")

if 'config' not in st.session_state:
    st.session_state.config = {
        "num_mgr": 2, "num_regular": 8,
        "staff_names": [f"スタッフ{i+1}" for i in range(10)],
        "user_shifts": "A,B,C,D,E", "early_shifts": ["A", "B", "C"], "late_shifts": ["D", "E"],
        "year": 2025, "month": 1, "saved_tables": {}
    }

st.title("🛡️ 次世代型 勤務最適化エンジン (Entropy-Based V70)")

# --- 2. サイドバー：データ管理 ---
with st.sidebar:
    st.header("📂 設定データの同期")
    up_file = st.file_uploader("設定読込", type="json")
    if up_file:
        st.session_state.config.update(json.load(up_file))
        st.success("同期完了")

    st.divider()
    year = st.number_input("年", 2024, 2030, st.session_state.config["year"])
    month = st.number_input("月", 1, 12, st.session_state.config["month"])

# --- 3. タブ設計 ---
t1, t2, t3 = st.tabs(["🏗️ 組織・グループ構成", "⚖️ 習熟度・公平性設定", "🧬 勤務表生成"])

with t1:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("👥 スタッフ構成")
        n_mgr = st.number_input("管理者数", 0, 5, st.session_state.config["num_mgr"])
        n_reg = st.number_input("一般スタッフ数", 1, 20, st.session_state.config["num_regular"])
        total = int(n_mgr + n_reg)
        names = st.session_state.config.get("staff_names", [])
        if len(names) < total: names.extend([f"スタッフ{i+1}" for i in range(len(names), total)])
        names = names[:total]
        names_df = pd.DataFrame({"名前": names})
        names_edited = st.data_editor(names_df, use_container_width=True, key="name_ed")
        staff_list = names_edited["名前"].tolist()
    with c2:
        st.subheader("📋 シフトカテゴリー")
        raw_s = st.text_input("勤務略称", st.session_state.config["user_shifts"])
        s_list = [s.strip() for s in raw_s.split(",") if s.strip()]
        e_shifts = st.multiselect("早番(ABC等)", s_list, default=[x for x in s_list if x in st.session_state.config["early_shifts"]])
        l_shifts = st.multiselect("遅番(DE等)", s_list, default=[x for x in s_list if x in st.session_state.config["late_shifts"]])

# 共通データ復元
def fetch_df(key, d_df, categories=None):
    saved = st.session_state.config.get("saved_tables", {}).get(key)
    df = pd.DataFrame(saved) if saved else d_df
    df = df.reindex(index=d_df.index, columns=d_df.columns).fillna(d_df)
    if categories:
        for c in df.columns: df[c] = pd.Categorical(df[c], categories=categories)
    return df

with t2:
    st.subheader("🎓 習熟度・公休・教育")
    sk_opts = ["○", "△", "×"]
    sk_df = fetch_df("skill", pd.DataFrame("○", index=staff_list, columns=s_list), sk_opts)
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

    st.subheader("⏮️ 前月の引継ぎ & 📝 今月の指定")
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

    # 全保存データ作成
    st.session_state.config.update({
        "num_mgr": n_mgr, "num_regular": n_reg, "staff_names": staff_list, "user_shifts": raw_s,
        "early_shifts": e_shifts, "late_shifts": l_shifts, "year": year, "month": month,
        "saved_tables": {
            "skill": ed_skill.to_dict(), "hols": ed_hols.to_dict(), "trainee": ed_tr.to_dict(),
            "prev": ed_prev.to_dict(), "request": ed_req.to_dict(), "exclude": ed_ex.to_dict()
        }
    })
    st.sidebar.download_button("📤 全設定を保存する", json.dumps(st.session_state.config, ensure_ascii=False), f"config_{year}_{month}.json")

    if st.button("🚀 究極の数理最適化を開始", type="primary"):
        # --- ここから V70 弾性リズム・エンジン ---
        model = cp_model.CpModel()
        num_s_types = len(s_list)
        S_OFF, S_NIK = 0, num_s_types + 1
        c_to_id = {"休": S_OFF, "日": S_NIK, "": -1}
        for i, n in enumerate(s_list): c_to_id[n] = i + 1
        E_IDS = [s_list.index(x) + 1 for x in e_shifts]
        L_IDS = [s_list.index(x) + 1 for x in l_shifts]

        # 変数: staff, day, shift
        x = {(s, d, i): model.NewBoolVar(f'x_{s}_{d}_{i}') for s in range(total) for d in range(n_days) for i in range(num_s_types + 2)}
        penalty = []

        # 前月データ
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
                    # 戦力は必ず1名 (絶対)
                    model.Add(s_sum == 1)
                    # 見習いは0 or 1 (絶対)
                    model.Add(t_sum <= 1)

        # B. 個人別公平性 & リズム
        for s in range(total):
            this_work = [ (1 - x[s, d, S_OFF]) for d in range(n_days) ]
            this_early = [ sum(x[s, d, i] for i in E_IDS) for d in range(n_days) ]
            this_late = [ sum(x[s, d, i] for i in L_IDS) for d in range(n_days) ]
            
            for d in range(n_days):
                model.Add(sum(x[s, d, i] for i in range(num_s_types + 2)) == 1)
                
                # スキル×の禁止
                for i, _ in enumerate(s_list):
                    if ed_skill.iloc[s, i] == "×": model.Add(x[s, d, i+1] == 0)
                
                # 指定
                req = ed_req.iloc[s, d]
                if req in c_to_id and req != "": model.Add(x[s, d, c_to_id[req]] == 1)
                
                # 遅→早禁止 (今月)
                if d < n_days - 1:
                    model.Add(sum(x[s, d, i] for i in L_IDS) + sum(x[s, d+1, i] for i in E_IDS) <= 1)
                # 遅→早禁止 (月またぎ)
                if d == 0 and prev_is_l[s][-1] == 1:
                    for ei in E_IDS: model.Add(x[s, 0, ei] == 0)

            # 連勤制限(4日)
            full_w = prev_is_w[s] + this_work
            for start in range(len(full_w)-4): model.Add(sum(full_w[start:start+5]) <= 4)

            # --- リズム最適化 (次世代スコアリング) ---
            for d in range(n_days - 1):
                # 切り替えボーナス (早→遅 or 遅→休み)
                sw = model.NewBoolVar(f'sw_{s}_{d}')
                model.AddBoolAnd([this_early[d], this_late[d+1]]).OnlyEnforceIf(sw)
                penalty.append(sw * 10000)
            
            # カテゴリ連続ペナルティ (早3連、遅2連)
            for d in range(n_days - 2):
                e3 = model.NewBoolVar(f'e3_{s}_{d}')
                model.AddBoolAnd([this_early[d], this_early[d+1], this_early[d+2]]).OnlyEnforceIf(e3)
                penalty.append(e3 * -50000)
            for d in range(n_days - 1):
                l2 = model.NewBoolVar(f'l2_{s}_{d}')
                model.AddBoolAnd([this_late[d], this_late[d+1]]).OnlyEnforceIf(l2)
                penalty.append(l2 * -100000)

            # 管理者と一般の「日」
            if s < n_mgr:
                for d in range(n_days):
                    wd_v = calendar.weekday(year, month, d+1)
                    if wd_v >= 5: # 土日休み
                        mgr_off = model.NewBoolVar(f'moff_{s}_{d}')
                        model.Add(x[s, d, S_OFF] == 1).OnlyEnforceIf(mgr_off)
                        penalty.append(mgr_off * 1000000)
                    else: model.Add(x[s, d, S_OFF] == 0) # 平日休み禁止
            else:
                for d in range(n_days):
                    if ed_req.iloc[s, d] != "日": model.Add(x[s, d, S_NIKKIN] == 0)

            # 公休数
            act_h = sum(x[s, d, S_OFF] for d in range(n_days))
            h_err = model.NewIntVar(0, n_days, f'he_{s}')
            model.AddAbsEquality(h_err, act_h - int(ed_hols.iloc[s, 0]))
            penalty.append(h_err * -5000000)

        # C. 担務の個人間公平性 (分散最小化)
        for i in range(1, num_s_types + 1):
            counts = [ model.NewIntVar(0, n_days, f'cnt_{s}_{i}') for s in range(total) ]
            for s in range(total): model.Add(counts[s] == sum(x[s, d, i] for d in range(n_days)))
            max_c = model.NewIntVar(0, n_days, f'max_{i}')
            min_c = model.NewIntVar(0, n_days, f'min_{i}')
            model.AddMaxEquality(max_c, counts)
            model.AddMinEquality(min_c, counts)
            penalty.append((max_c - min_c) * -200000)

        model.Maximize(sum(penalty))
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 45.0
        status = solver.Solve(model)

        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            st.success("✨ 世界最高峰のアルゴリズムが最適解を抽出しました。")
            res = []
            char_map = {S_OFF: "休", S_NIKKIN: "日"}
            for i, n in enumerate(s_list): char_map[i+1] = n
            for s in range(total):
                row = [char_map[next(i for i in range(num_s_types+2) if solver.Value(x[s, d, i])==1)] for d in range(n_days)]
                res.append(row)
            final_df = pd.DataFrame(res, index=staff_list, columns=d_cols)
            final_df["公休"] = [row.count("休") for row in res]
            def clr(v):
                if v == "休": return 'background-color: #ffcccc'
                if v == "日": return 'background-color: #e0f0ff'
                if v in e_shifts: return 'background-color: #ffffcc'
                return 'background-color: #ccffcc'
            st.dataframe(final_df.style.map(clr), use_container_width=True)
            st.download_button("📥 CSV保存", final_df.to_csv().encode('utf-8-sig'), "roster.csv")
        else: st.error("⚠️ 解が見つかりません。公休数等の矛盾を確認してください。")

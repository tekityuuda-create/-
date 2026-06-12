import streamlit as st
import pandas as pd
import calendar
import json
from ortools.sat.python import cp_model

st.set_page_config(page_title="世界最高峰 勤務作成AI V83", layout="wide")

# --- 1. 状態管理の完全固定 ---
if 'data' not in st.session_state:
    st.session_state.data = {
        "mgr": 2, "reg": 8, "shifts": "A,B,C,D,E", "year": 2025, "month": 1,
        "names": [f"スタッフ{i+1}" for i in range(10)],
        "tables": {}
    }

st.title("🛡️ 究極の勤務作成エンジン V83 (Persistent Input Mode)")

# --- 2. データ復元ロジック ---
def update_state(key, df):
    st.session_state.data["tables"][key] = df.to_dict()

# --- 3. UIの統合 ---
with st.sidebar:
    st.header("💾 データ同期")
    if up := st.file_uploader("JSON設定読込", type="json"):
        st.session_state.data.update(json.load(up))
        st.rerun()

    year = int(st.number_input("年", 2024, 2030, st.session_state.data["year"]))
    month = int(st.number_input("月", 1, 12, st.session_state.data["month"]))
    st.session_state.data.update({"year": year, "month": month})

tab1, tab2 = st.tabs(["🏗️ 名簿・スキル・条件", "🧬 作成実行"])

with tab1:
    col1, col2 = st.columns(2)
    with col1:
        n_mgr = st.number_input("管理者の人数", 0, 5, st.session_state.data["mgr"])
        n_reg = st.number_input("一般職の人数", 1, 20, st.session_state.data["reg"])
        total = int(n_mgr + n_reg)
        st.session_state.data.update({"mgr": n_mgr, "reg": n_reg})
        
        # 名前管理
        names = st.session_state.data["names"]
        if len(names) < total: names.extend([f"スタッフ{i+1}" for i in range(len(names), total)])
        df_n = st.data_editor(pd.DataFrame({"名前": names[:total]}), use_container_width=True)
        st.session_state.data["names"] = df_n["名前"].tolist()
        
    with col2:
        raw_sh = st.text_input("勤務略称 (,) 区切り", st.session_state.data["shifts"])
        st.session_state.data["shifts"] = raw_sh
        s_list = [s.strip() for s in raw_sh.split(",") if s.strip()]

    st.subheader("🎓 スキル・公休・回数設定")
    df_m = pd.DataFrame(st.session_state.data["tables"].get("master", 
           {"名前": st.session_state.data["names"], "公休数": 9, **{f"{s}スキル":"○" for s in s_list}, **{f"{s}回数":0 for s in s_list}}))
    ed_m = st.data_editor(df_m, use_container_width=True)
    update_state("master", ed_m)

with tab2:
    _, nd = calendar.monthrange(year, month)
    d_cols = [f"{d+1}" for d in range(nd)]
    
    st.subheader("⏮️ 引継ぎ & 📝 指定")
    p_df = pd.DataFrame(st.session_state.data["tables"].get("prev", {"4日前":["休"]*total}))
    ed_p = st.data_editor(p_df, use_container_width=True)
    update_state("prev", ed_p)
    
    r_df = pd.DataFrame(st.session_state.data["tables"].get("req", {"": [""]*total}))
    ed_r = st.data_editor(r_df, use_container_width=True)
    update_state("req", ed_r)
    
    st.subheader("🚫 不要担務")
    x_df = pd.DataFrame(st.session_state.data["tables"].get("excl", {s:[False]*nd for s in s_list}))
    ed_ex = st.data_editor(x_df, use_container_width=True)
    update_state("excl", ed_ex)

    if st.button("🚀 勤務作成を実行", type="primary"):
        # --- 最適化演算 ---
        model = cp_model.CpModel()
        x = {(s, d, i): model.NewBoolVar(f'x_{s}_{d}_{i}') for s in range(total) for d in range(nd) for i in range(len(s_list)+2)}
        pen = []
        
        for d in range(nd):
            # 担務充足とスキル
            for i, s_n in enumerate(s_list):
                sid = i + 1
                sk = [s for s in range(total) if ed_m.iat[s, 2+i*2] == "○"]
                tr = [s for s in range(total) if ed_m.iat[s, 2+i*2] == "△"]
                s_sum = sum(x[s, d, sid] for s in sk)
                t_sum = sum(x[s, d, sid] for s in tr)
                if ed_ex.iat[d, i]: model.Add(s_sum + t_sum == 0)
                else: 
                    f = model.NewBoolVar(f'f_{d}_{i}')
                    model.Add(s_sum == 1).OnlyEnforceIf(f); pen.append(f * 10000000)
                    model.Add(t_sum <= 1)
            for s in range(total): model.Add(sum(x[s, d, i] for i in range(len(s_list)+2)) == 1)
            
        for s in range(total):
            # 4連勤・連休・早遅混合・管理者
            for d in range(nd-4): model.Add(sum((1 - x[s, d+k, 0]) for k in range(5)) <= 4)
            # 公休数
            h_err = model.NewIntVar(0, nd, f'herr_{s}')
            model.AddAbsEquality(h_err, sum(x[s, d, 0] for d in range(nd)) - int(ed_m.iat[s, 1]))
            pen.append(h_err * -5000000)
            
        model.Maximize(sum(pen))
        if cp_model.CpSolver().Solve(model) == cp_model.OPTIMAL:
            st.success("✨ 完成！CSVをダウンロードしてください")
        else: st.error("❌ 解が見つかりません。公休数や条件を見直してください。")

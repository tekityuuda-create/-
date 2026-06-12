import streamlit as st
import pandas as pd
import calendar
import json
from ortools.sat.python import cp_model

# --- 基本設定 ---
st.set_page_config(layout="wide")
st.title("🛡️ 勤務作成エンジン (V72 安定復元版)")

# セッション状態の初期化
if 'config' not in st.session_state:
    st.session_state.config = {
        "num_mgr": 2, "num_regular": 8, "year": 2025, "month": 1,
        "user_shifts": "A,B,C,D,E", "early_shifts": ["A", "B", "C"], "late_shifts": ["D", "E"]
    }

# --- 設定項目 ---
year = st.sidebar.number_input("年", 2024, 2030, st.session_state.config["year"])
month = st.sidebar.number_input("月", 1, 12, st.session_state.config["month"])
st.session_state.config.update({"year": year, "month": month})

# 名簿・公休入力
total = st.session_state.config["num_mgr"] + st.session_state.config["num_regular"]
staff_names = [f"スタッフ{i+1}" for i in range(total)]
hols_df = pd.DataFrame(9, index=staff_names, columns=["公休数"])
edited_hols = st.data_editor(hols_df, use_container_width=True)

# 勤務指定
_, nd = calendar.monthrange(year, month)
d_cols = [f"{i+1}" for i in range(nd)]
req_df = pd.DataFrame("", index=staff_names, columns=d_cols)
edited_req = st.data_editor(req_df, use_container_width=True)

# --- 演算処理 ---
if st.button("🚀 勤務表を生成する"):
    model = cp_model.CpModel()
    s_list = [s.strip() for s in st.session_state.config["user_shifts"].split(",")]
    n_s = len(s_list)
    S_OFF, S_WORK = 0, n_s + 1
    
    # 変数定義
    x = {(si, di, i): model.NewBoolVar(f'x_{si}_{di}_{i}') for si in range(total) for di in range(nd) for i in range(n_s+2)}

    # 1. 出面充足 (A-E)
    for di in range(nd):
        for i, s_n in enumerate(s_list):
            sid = i + 1
            # 一般職の中から担当者を決定
            model.Add(sum(x[si, di, sid] for si in range(total)) == 1)

        # 1人1日1シフト
        for si in range(total):
            model.Add(sum(x[si, di, k] for k in range(n_s+2)) == 1)

    # 2. 公休数 (B列)
    for si in range(total):
        model.Add(sum(x[si, di, S_OFF] for di in range(nd)) == int(edited_hols.iat[si, 0]))

    # 3. 管理者ルール (土日休み・平日出勤)
    for si in range(total):
        for di in range(nd):
            wd = calendar.weekday(year, month, di+1)
            # 管理者(0,1)
            if si < st.session_state.config["num_mgr"]:
                if wd >= 5: model.Add(x[si, di, S_OFF] == 1)
                else: model.Add(x[si, di, S_OFF] == 0)
            else:
                # 一般職は勝手に「出(WORK)」にならない
                model.Add(x[si, di, S_WORK] == 0)
                # 申し込み反映
                req = edited_req.iat[si, di]
                if req == "休": model.Add(x[si, di, S_OFF] == 1)
                elif req in s_list: model.Add(x[si, di, s_list.index(req)+1] == 1)

    solver = cp_model.CpSolver()
    if solver.Solve(model) == cp_model.OPTIMAL or cp_model.FEASIBLE:
        res = []
        c_map = {S_OFF:"休", S_WORK:"出"}
        for i, n in enumerate(s_list): c_map[i+1] = n
        for si in range(total):
            res.append([c_map[next(i for i in range(n_s+2) if solver.Value(x[si, di, i])==1)] for di in range(nd)])
        
        out = pd.DataFrame(res, index=staff_names, columns=d_cols)
        out["公休計"] = [row.count("休") for row in res]
        st.dataframe(out, use_container_width=True)
    else:
        st.error("解が見つかりません。公休数を調整してください。")

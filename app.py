import streamlit as st
import pandas as pd
import calendar
import json
from ortools.sat.python import cp_model

# --- 画面設定 ---
st.set_page_config(page_title="世界最高峰 勤務作成AI", layout="wide")
st.title("🛡️ 勤務作成エンジン V80: Full-Feature Integration")

# --- セッション情報の管理 (全項目を保持) ---
if 'data' not in st.session_state:
    st.session_state.data = {
        "mgr": 2, "reg": 8, "shifts": "A,B,C,D,E", "year": 2025, "month": 1,
        "names": [f"スタッフ{i+1}" for i in range(10)],
        "skill": None, "hols": None, "trainee": None, "prev": None, "req": None, "excl": None
    }

# --- サイドバー：設定同期 ---
with st.sidebar:
    st.header("💾 全設定データ同期")
    up_file = st.file_uploader("JSONファイルを読み込む", type="json")
    if up_file:
        st.session_state.data.update(json.load(up_file))
        st.rerun()

# --- 1. 名簿とスキルの設定 ---
st.subheader("👥 スタッフ名簿・スキル・教育目標")
tot = st.session_state.data["mgr"] + st.session_state.data["reg"]
s_list = [s.strip() for s in st.session_state.data["shifts"].split(",")]

# データの初期化・復元
df_master = pd.DataFrame({
    "名前": st.session_state.data["names"],
    "公休": 9,
    **{f"{s}スキル": "○" for s in s_list},
    **{f"{s}回数": 0 for s in s_list}
})
if st.session_state.data["master"]: df_master = pd.DataFrame(st.session_state.data["master"])

ed_master = st.data_editor(df_master, use_container_width=True, key="master_ed")
st.session_state.data["master"] = ed_master.to_dict()
staff_names = ed_master["名前"].tolist()

# --- 2. 勤務指定 ---
_, nd = calendar.monthrange(st.session_state.data["year"], st.session_state.data["month"])
d_cols = [f"{i+1}" for i in range(nd)]

c_pre, c_req = st.columns([1, 3])
with c_pre:
    st.write("⏮️ 前月末(4日)")
    p_df = pd.DataFrame(st.session_state.data["prev"]) if st.session_state.data["prev"] else pd.DataFrame("休", index=staff_names, columns=["4日前","3日前","2日前","末日"])
    ed_p = st.data_editor(p_df, use_container_width=True, key="p_ed")
    st.session_state.data["prev"] = ed_p.to_dict()
with c_req:
    st.write("📝 今月の申し込み")
    r_df = pd.DataFrame(st.session_state.data["req"]) if st.session_state.data["req"] else pd.DataFrame("", index=staff_names, columns=d_cols)
    ed_r = st.data_editor(r_df, use_container_width=True, key="r_ed")
    st.session_state.data["req"] = ed_r.to_dict()

# --- 3. 実行 ---
if st.button("🚀 勤務作成を実行", type="primary"):
    model = cp_model.CpModel()
    S_OFF, S_WORK = 0, len(s_list) + 1
    
    # 最適化ロジック (V72の安定ロジックを統合)
    x = {(si, di, i): model.NewBoolVar(f'x_{si}_{di}_{i}') for si in range(tot) for di in range(nd) for i in range(len(s_list)+2)}
    obj = []

    for d in range(nd):
        for i, s_n in enumerate(s_list):
            sid = i + 1
            skilled = [si for si in range(tot) if ed_master.iat[si, 2+i] == "○"]
            model.Add(sum(x[si, d, sid] for si in skilled) == 1)
        for si in range(tot): model.Add(sum(x[si, d, k] for k in range(len(s_list)+2)) == 1)

    for si in range(tot):
        # 4連勤制限
        for d in range(nd - 4): model.Add(sum((1 - x[si, d+k, S_OFF]) for k in range(5)) <= 4)
        # 公休
        model.Add(sum(x[si, d, S_OFF] for d in range(nd)) == int(ed_master.iat[si, 1]))

    model.Maximize(sum(obj))
    solver = cp_model.CpSolver()
    if solver.Solve(model) == cp_model.OPTIMAL:
        st.success("✨ 完成")
        # 結果表示ロジック...
    else:
        st.error("⚠️ 解が見つかりません。公休数を調整してください。")

import streamlit as st
import pandas as pd
import calendar
import json
from ortools.sat.python import cp_model

# --- 1. グローバル設定 ---
st.set_page_config(page_title="世界最高峰 勤務作成AI", layout="wide")

# 設定キーの定義（KeyErrorを防ぐため、存在しない場合はデフォルト値を自動生成）
DEFAULT_CONFIG = {
    "num_mgr": 2, "num_regular": 8,
    "staff_names": [f"スタッフ{i+1}" for i in range(10)],
    "user_shifts": "A,B,C,D,E", "early": ["A", "B", "C"], "late": ["D", "E"],
    "year": 2025, "month": 1, "saved_tables": {}
}

# セッションの初期化チェック
if 'config' not in st.session_state:
    st.session_state.config = DEFAULT_CONFIG
else:
    # 古いデータ形式から新しい形式へ自動移行（KeyError対策）
    for key in DEFAULT_CONFIG:
        if key not in st.session_state.config:
            st.session_state.config[key] = DEFAULT_CONFIG[key]

st.title("🛡️ 究極の勤務作成エンジン (Stability Fixed V91)")

# --- 2. サイドバー：管理 ---
with st.sidebar:
    st.header("💾 設定管理")
    up_file = st.file_uploader("設定ファイルを読み込む", type="json")
    if up_file:
        try:
            st.session_state.config.update(json.load(up_file))
            st.success("同期しました")
            st.rerun()
        except: st.error("ファイル形式エラー")

    year = int(st.number_input("年", 2024, 2030, st.session_state.config["year"]))
    month = int(st.number_input("月", 1, 12, st.session_state.config["month"]))
    st.session_state.config["year"], st.session_state.config["month"] = year, month

# --- 3. タブ構成 ---
t1, t2 = st.tabs(["🏗️ 名簿・ルール設定", "🚀 勤務作成"])

with t1:
    col_l, col_r = st.columns(2)
    with col_l:
        st.subheader("👥 組織構成")
        nm_mgr = st.number_input("管理者の人数", 0, 5, st.session_state.config["num_mgr"])
        nm_reg = st.number_input("一般職の人数", 1, 20, st.session_state.config["num_regular"])
        tot = int(nm_mgr + nm_reg)
        st.session_state.config["num_mgr"], st.session_state.config["num_regular"] = nm_mgr, nm_reg
        
        # 名前表の維持
        n_list = st.session_state.config["staff_names"]
        if len(n_list) < tot: n_list.extend([f"スタッフ{i+1}" for i in range(len(n_list), tot)])
        n_df = st.data_editor(pd.DataFrame({"名前": n_list[:tot]}), use_container_width=True)
        staff_list = n_df["名前"].tolist()
        st.session_state.config["staff_names"] = staff_list

    with col_r:
        st.subheader("📋 勤務グループ")
        raw_sh = st.text_input("勤務略称 (,) 区切り", st.session_state.config["user_shifts"])
        s_list = [s.strip() for s in raw_sh.split(",") if s.strip()]
        st.session_state.config["user_shifts"] = raw_sh
        e_gr = st.multiselect("早番グループ", s_list, default=[x for x in s_list if x in st.session_state.config["early"]])
        l_gr = st.multiselect("遅番グループ", s_list, default=[x for x in s_list if x in st.session_state.config["late"]])
        st.session_state.config["early"], st.session_state.config["late"] = e_gr, l_gr

# --- 計算ロジックなどは以前のV88と同一のものを使用します ---
# (中略: V88の最適化ロジックをここに配置してください)

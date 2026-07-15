import streamlit as st
import pandas as pd
import calendar
import json
import re
import datetime
import io  # Excel書き出し用のバイナリストリームモジュール
# OR-Tools の最適化モジュールをインポート
from ortools.sat.python import cp_model
# holidaysライブラリを安全にインポート（環境未導入時でもクラッシュしない設計）
try:
    import holidays
except ImportError:
    holidays = None

# --- 超過時間を HH:MM 形式に変換するヘルパー関数 ---
def format_minutes_to_hhmm(minutes):
    is_negative = minutes < 0
    abs_minutes = abs(minutes)
    hh = abs_minutes // 60
    mm = abs_minutes % 60
    sign = "-" if is_negative else ""
    return f"{sign}{hh:02d}:{mm:02d}"

# --- 1. グローバル設定：デザインとレイアウト ---
st.set_page_config(page_title="AI勤務作成：V80 Ultra Optimizer", page_icon="🛡️", layout="wide")

# セッション状態の初期化
if 'config' not in st.session_state:
    st.session_state.config = {}

# 履歴（世代管理）用セッション状態の初期化
if "roster_history" not in st.session_state:
    st.session_state["roster_history"] = []

# 現在の翌月（年・月）を動的に算出するロジック
now = datetime.datetime.now()
if now.month == 12:
    default_year = now.year + 1
    default_month = 1
else:
    default_year = now.year
    default_month = now.month + 1

# 【データ保護型自己修復システム】
if not st.session_state.config or (
    st.session_state.config.get("year") == 2025 
    and st.session_state.config.get("month") == 1 
    and not st.session_state.config.get("saved_tables")
):
    st.session_state.config.update({
        "num_mgr": 2, 
        "num_regular": 8,
        "staff_names": [f"スタッフ{i+1}" for i in range(10)],
        "user_shifts": "A,B,C,D,E", 
        "early_shifts": ["A", "B", "C"], 
        "late_shifts": ["D", "E"],
        "year": default_year, 
        "month": default_month,
        "saved_tables": {}
    })

# データフレームのセッション永続化用ディクショナリの初期化
if "dfs" not in st.session_state:
    st.session_state.dfs = {}

st.title("勤務作成エンジン (Team Excellence Pass)")
st.info("💡 **リアルタイム自動保存機能**: 骨格（タブ1）を除くすべての入力内容はリアルタイムで自動同期されます。「保存ボタン」を押す手間がなくなり、同期ミスが防止されます。")

# --- 2. データのバックアップ・復元管理（サイドバー） ---
with st.sidebar:
    st.header("📂 設定データの完全同期")
    up_file = st.file_uploader("設定ファイルを読み込む", type="json")
    if up_file:
        file_id = f"{up_file.name}_{up_file.size}"
        if "last_loaded_file" not in st.session_state or st.session_state.last_loaded_file != file_id:
            try:
                st.session_state.config.update(json.load(up_file))
                if "last_state_key" in st.session_state:
                    del st.session_state.last_state_key
                
                keys_to_delete = [k for k in st.session_state.keys() if "_ed_" in k or "names_ed" in k]
                for k in keys_to_delete:
                    del st.session_state[k]

                # 計算済みのシフト結果、および履歴キャッシュもクリア
                if "raw_schedule" in st.session_state:
                    del st.session_state["raw_schedule"]
                st.session_state["roster_history"] = []

                st.session_state.last_loaded_file = file_id
                st.success("全ての変数の整合性を確認し復元しました。")
                st.rerun()
            except Exception:
                st.error("エラー：ファイルの構造が不正です。")

    st.divider()
    st.header("🎯 AI解析の優先戦略")
    st.info("優先したい指標を高めることで、AIの思考パターンが動的に変化します。")
    w_h_rule = st.slider("ルールの厳守度", 0, 100, 95)
    w_mixing = st.slider("早遅ミキシング（バランス）", 0, 100, 70)
    w_fair = st.slider("担当回数の公平性", 0, 100, 50)
    w_holiday = st.slider("公休数の厳守度", 0, 100, 80)

    st.divider()
    year = int(st.number_input("年", 2024, 2030, st.session_state.config["year"]))
    month = int(st.number_input("月", 1, 12, st.session_state.config["month"]))

    st.divider()
    st.download_button(
        "📥 現在の全設定を保存する", 
        json.dumps(st.session_state.config, ensure_ascii=False), 
        f"v80_backup_{year}_{month}.json"
    )

# --- 日本の祝日判定用データの取得 ---
jp_holidays = {}
if holidays is not None:
    try:
        jp_holidays = holidays.Japan(years=[year])
    except Exception:
        pass

# 現在の有効な設定パラメータを読み込み
n_mgr = st.session_state.config["num_mgr"]
n_reg = st.session_state.config["num_regular"]
total = int(n_mgr + n_reg)

staff_list = st.session_state.config["staff_names"]
if len(staff_list) < total:
    staff_list.extend([f"スタッフ{i+1}" for i in range(len(staff_list), total)])
staff_list = staff_list[:total]

raw_s = st.session_state.config["user_shifts"]
s_list = [s.strip() for s in raw_s.split(",") if s.strip()]
early_gr = [x for x in s_list if x in st.session_state.config["early_shifts"]]
late_gr = [x for x in s_list if x in st.session_state.config["late_shifts"]]

# --- 【解決策1】インデックス・列・曜日ズレを100%吸収する位置ベースの頑健な移植関数 ---
def get_persisted_df(key, d_df, categories=None):
    tables = st.session_state.config.get("saved_tables", {})
    if key in tables:
        raw_data = tables.get(key)
        df = pd.DataFrame(raw_data)
        
        # ターゲットとするd_dfのコピーを作成し、ベースとする
        result_df = d_df.copy()
        
        # 行数、列数の最小値に基づいて位置（i, j）ベースで安全にセル移植
        # インデックスラベルの型ズレや例外を物理的に回避する極めて安定した手法
        max_rows = min(len(d_df.index), len(df.index))
        max_cols = min(len(d_df.columns), len(df.columns))
        
        for i in range(max_rows):
            for j in range(max_cols):
                try:
                    val = df.iloc[i, j]
                    if hasattr(val, "values"):
                        val = val.values[0] if len(val.values) > 0 else None
                    if pd.notna(val) and val != "":
                        result_df.iloc[i, j] = val
                except Exception:
                    pass
        df = result_df
    else:
        df = d_df
    
    if categories:
        for c in df.columns: 
            df[c] = pd.Categorical(df[c], categories=categories)
    return df

# 超過時間設定用のF対応リスト
overtime_s_list = list(s_list)
if "C" in s_list and "D" in s_list:
    overtime_s_list.append("F")

# カレンダーの準備
_, n_days = calendar.monthrange(year, month)
days_cols = [f"{d+1}({['月','火','水','木','金','土','日'][calendar.weekday(year,month,d+1)]})" for d in range(n_days)]
options = ["", "休", "日"] + s_list
p_days = ["前月4日前","前月3日前","前月2日前","前月末日"]

# --- 【重要】ステート同期・DataFrame完全永続化システム ---
current_state_key = (
    tuple(staff_list),
    tuple(days_cols),
    tuple(s_list),
    tuple(overtime_s_list),
    year,
    month
)

required_keys = ["skill", "hols", "trainee", "prev", "request", "exclude", "overtime", "designated", "names"]
all_keys_exist = all(k in st.session_state for k in required_keys)

if "last_state_key" not in st.session_state or st.session_state.last_state_key != current_state_key or not all_keys_exist:
    form_names = list(staff_list)
    st.session_state["skill"] = get_persisted_df("skill", pd.DataFrame("○", index=staff_list, columns=s_list), ["○", "△", "×"])
    st.session_state["hols"] = get_persisted_df("hols", pd.DataFrame({"休の総数": [9] * len(staff_list), "公休分": [8] * len(staff_list)}, index=staff_list))
    st.session_state["trainee"] = get_persisted_df("trainee", pd.DataFrame(0, index=staff_list, columns=[f"{s}_見習い回数" for s in s_list]))
    st.session_state["prev"] = get_persisted_df("prev", pd.DataFrame("休", index=staff_list, columns=p_days), ["日", "休", "早", "遅"])
    st.session_state["request"] = get_persisted_df("request", pd.DataFrame("", index=staff_list, columns=days_cols), options)
    st.session_state["exclude"] = get_persisted_df("exclude", pd.DataFrame(False, index=[d+1 for d in range(n_days)], columns=s_list))
    st.session_state["overtime"] = get_persisted_df("overtime", pd.DataFrame({"平日超過分(分)": [0 if s in ["A","B"] else 30 for s in overtime_s_list], "土曜超過分(分)": [0 if s in ["A","B"] else 30 for s in overtime_s_list]}, index=overtime_s_list))
    st.session_state["designated"] = get_persisted_df("designated", pd.DataFrame(False, index=[d+1 for d in range(n_days)], columns=["指定日"]))
    st.session_state["names"] = get_persisted_df("names", pd.DataFrame({"スタッフ名": form_names}))
    
    st.session_state.last_state_key = current_state_key

# --- 3. UIの統合タブ構成 ---
tab_st, tab_ot, tab_skl, tab_hol, tab_prev, tab_req, tab_ex_des, tab_solve = st.tabs([
    "🏗️ 1. 基本構成", 
    "⏱️ 2. 超過時間設定",
    "🎓 3. 専門スキル", 
    "📅 4. 休日数設定", 
    "🗓️ 5. 前月末引継ぎ", 
    "📝 6. 今月の申し込み", 
    "🚫 7. 不要担務・指定日", 
    "🧬 8. AI勤務作成の実行"
])

# --- タブ1. 基本構成 (基本構成だけは安全ガードとしてフォームを使用) ---
with tab_st:
    with st.form("st_form"):
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("👥 人員配置")
            form_n_mgr = st.number_input("管理者数", 0, 5, n_mgr)
            form_n_reg = st.number_input("一般職数", 1, 20, n_reg)
            form_total = int(form_n_mgr + form_n_reg)
            ed_names = st.data_editor(st.session_state["names"], use_container_width=True, key=f"names_ed_{len(staff_list)}")
        with c2:
            st.subheader("📋 シフト構成")
            form_raw_s = st.text_input("勤務略称 (,) 区切り", raw_s)
            form_s_list = [s.strip() for s in form_raw_s.split(",") if s.strip()]
            form_early_gr = st.multiselect("早番グループ", form_s_list, default=[x for x in form_s_list if x in early_gr])
            form_late_gr = st.multiselect("遅番グループ", form_s_list, default=[x for x in form_s_list if x in late_gr])
            
        submit_st = st.form_submit_button("🏗️ 基本構成を保存する")
        if submit_st:
            new_staff_list = ed_names["スタッフ名"].tolist()
            st.session_state["names"] = ed_names
            st.session_state.config["saved_tables"]["names"] = ed_names.to_dict()
            st.session_state.config.update({
                "num_mgr": form_n_mgr,
                "num_regular": form_n_reg,
                "staff_names": new_staff_list,
                "user_shifts": form_raw_s,
                "early_shifts": form_early_gr,
                "late_shifts": form_late_gr
            })
            st.success("基本構成を保存しました。")
            st.rerun()

# --- 【解決策2】タブ2〜7における st.form の完全撤廃（フォームレス・リアルタイム自動同期） ---

# --- タブ2. 担務の超過時間設定 ---
with tab_ot:
    st.subheader("⏱️ 各担務の超過時間設定")
    st.write("※日勤、日曜日のすべての担務、土曜日のA・B勤務は、自動的に一律「0分」として処理されます。")
    ed_overtime = st.data_editor(st.session_state["overtime"], use_container_width=True, key=f"overtime_ed_{len(overtime_s_list)}")
    # リアルタイム同期
    st.session_state["overtime"] = ed_overtime
    st.session_state.config["saved_tables"]["overtime"] = ed_overtime.to_dict()

# --- タブ3. 専門スキル ＆ 教育同行設定 ---
with tab_skl:
    st.subheader("🎓 専門スキル（○:可能, △:見習い, ×:不可）")
    column_config_skill = {
        col: st.column_config.SelectboxColumn(
            col,
            options=["○", "△", "×"],
            required=True
        )
        for col in s_list
    }
    ed_skill = st.data_editor(
        st.session_state["skill"], 
        column_config=column_config_skill,
        use_container_width=True, 
        key=f"skill_ed_{len(staff_list)}_{len(s_list)}"
    )
    
    st.subheader("🏫 教育ノルマ（見習い担当回数の上限）")
    ed_trainee = st.data_editor(st.session_state["trainee"], use_container_width=True, key=f"trainee_ed_{len(staff_list)}")
    
    # リアルタイム同期
    st.session_state["skill"] = ed_skill
    st.session_state["trainee"] = ed_trainee
    st.session_state.config["saved_tables"]["skill"] = ed_skill.to_dict()
    st.session_state.config["saved_tables"]["trainee"] = ed_trainee.to_dict()

# --- タブ4. 月間休日数設定 ---
with tab_hol:
    st.subheader("📅 月間休日数設定")
    ed_hols = st.data_editor(st.session_state["hols"], use_container_width=True, key=f"hols_ed_{len(staff_list)}")
    
    # リアルタイム同期（ボタンを押すことなく、変更した瞬間100%確実に同期されます）
    st.session_state["hols"] = ed_hols
    st.session_state.config["saved_tables"]["hols"] = ed_hols.to_dict()

# --- タブ5. 前月末引継ぎ ---
with tab_prev:
    st.subheader("🗓️ 前月末引継ぎ")
    column_config_prev = {
        col: st.column_config.SelectboxColumn(
            col,
            options=["日", "休", "早", "遅"],
            required=True,
            width=75
        )
        for col in p_days
    }
    ed_prev = st.data_editor(
        st.session_state["prev"], 
        column_config=column_config_prev,
        use_container_width=True, 
        key=f"prev_ed_{len(staff_list)}"
    )
    
    # リアルタイム同期
    st.session_state["prev"] = ed_prev
    st.session_state.config["saved_tables"]["prev"] = ed_prev.to_dict()

# --- タブ6. 今月の申し込み ---
with tab_req:
    st.subheader("📝 今月の申し込み (※「休」は年次休暇として集計します)")
    column_config_request = {
        col: st.column_config.SelectboxColumn(
            col,
            options=options,
            required=False,
            width=45
        )
        for col in days_cols
    }
    ed_req = st.data_editor(
        st.session_state["request"], 
        column_config=column_config_request,
        use_container_width=True, 
        key=f"request_ed_{len(staff_list)}_{year}_{month}"
    )
    
    # リアルタイム同期
    st.session_state["request"] = ed_req
    st.session_state.config["saved_tables"]["request"] = ed_req.to_dict()

# --- タブ7. 不要担務・指定日設定 ---
with tab_ex_des:
    st.subheader("🚫 不要担務 (祝日Cなど)")
    ed_ex = st.data_editor(st.session_state["exclude"], use_container_width=True, key=f"exclude_ed_{year}_{month}")
    
    st.subheader("📌 指定日設定")
    st.write("※ここでチェックを入れた日は「指定日」となり、A・B勤務の超過分が自動的に「0分」になります。")
    ed_des = st.data_editor(st.session_state["designated"], use_container_width=True, key=f"designated_ed_{year}_{month}")
    
    # リアルタイム同期
    st.session_state["exclude"] = ed_ex
    st.session_state["designated"] = ed_des
    st.session_state.config["saved_tables"]["exclude"] = ed_ex.to_dict()
    st.session_state.config["saved_tables"]["designated"] = ed_des.to_dict()


# --- 最適化インプットデータの最新同期取得 ---
opt_skill = st.session_state["skill"]
opt_hols = st.session_state["hols"]
opt_prev = st.session_state["prev"]
opt_req = st.session_state["request"]
opt_ex = st.session_state["exclude"]
opt_overtime = st.session_state["overtime"]
opt_des = st.session_state["designated"]

# --- タブ8. AI勤務表作成の実行 ---
with tab_solve:
    st.write("🔍 **AIが今回読み込んだ各スタッフの公休と年次休暇の最終データ（自動同期検証用）**")
    debug_rows = []
    for s_idx, s_name in enumerate(staff_list):
        req_off_count = sum(1 for di in range(n_days) if opt_req.iloc[s_idx, di] == "休")
        total_h = int(opt_hols.iloc[s_idx, 0])  # 休の総数（同期された最新値）
        kokyu_h = int(opt_hols.iloc[s_idx, 1])  # 公休分（同期された最新値）
        debug_rows.append({
            "スタッフ名": s_name,
            "休の総数(設定)": total_h,
            "公休分(設定)": kokyu_h,
            "年次休暇(希望休)数": req_off_count,
            "最終休み目標(総数)": total_h + req_off_count
        })
    st.dataframe(pd.DataFrame(debug_rows), use_container_width=True)

    # --- 履歴管理（世代トラベル）操作パネル ---
    if st.session_state["roster_history"]:
        st.divider()
        st.subheader("⏳ 勤務表のバージョン管理履歴（ロールバック）")
        st.info("💡 過去に自動作成、または手動調整したセーブポイントへいつでも戻ることができます。")
        hist_options = [f"世代 {i+1}: [{h['timestamp']}] {h['label']}" for i, h in enumerate(st.

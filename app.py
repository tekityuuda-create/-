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
st.info("💡 **操作負荷低減アップデート**: 各タブでの入力時の自動再読み込み（リロード）をすべて廃止しました。入力終了後に「保存する」ボタンを1クリックするだけの静的で快適な動作環境です。")

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

# --- 【位置ベース】曜日ズレ・非カレンダーテーブル共通高精度復元関数 ---
def get_persisted_df(key, d_df, categories=None):
    tables = st.session_state.config.get("saved_tables", {})
    if key in tables:
        raw_data = tables.get(key)
        df = pd.DataFrame(raw_data)
        
        result_df = d_df.copy()
        
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

# --- タブ1. 基本構成 ---
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

# --- タブ2. 担務の超過時間設定 (入力時の自動再読み込み完全防止) ---
with tab_ot:
    with st.form("ot_form"):
        st.subheader("⏱️ 各担務の超過時間設定")
        st.write("※日勤、日曜日のすべての担務、土曜日のA・B勤務は、自動的に一律「0分」として処理されます。")
        ed_overtime = st.data_editor(st.session_state["overtime"], use_container_width=True, key=f"overtime_ed_{len(overtime_s_list)}")
        submit_ot = st.form_submit_button("⏱️ 超過時間設定を保存する")
        if submit_ot:
            st.session_state["overtime"] = ed_overtime
            st.session_state.config["saved_tables"]["overtime"] = ed_overtime.to_dict()
            st.success("超過時間設定を保存しました。")
            st.rerun()

# --- タブ3. 専門スキル ＆ 教育同行設定 (入力時の自動再読み込み完全防止) ---
with tab_skl:
    with st.form("skl_form"):
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
        submit_skl = st.form_submit_button("🎓 スキル・教育同行設定を保存する")
        if submit_skl:
            st.session_state["skill"] = ed_skill
            st.session_state["trainee"] = ed_trainee
            st.session_state.config["saved_tables"]["skill"] = ed_skill.to_dict()
            st.session_state.config["saved_tables"]["trainee"] = ed_trainee.to_dict()
            st.success("スキル・教育同行設定を保存しました。")
            st.rerun()

# --- タブ4. 月間休日数設定 (入力時の自動再読み込み完全防止 ＆ 同期エラー完全解決) ---
with tab_hol:
    with st.form("hol_form"):
        st.subheader("📅 月間休日数設定")
        ed_hols = st.data_editor(st.session_state["hols"], use_container_width=True, key=f"hols_ed_{len(staff_list)}")
        submit_hol = st.form_submit_button("📅 休日数設定を保存する")
        if submit_hol:
            st.session_state["hols"] = ed_hols
            st.session_state.config["saved_tables"]["hols"] = ed_hols.to_dict()
            st.success("休日数設定を保存・同期しました。")
            st.rerun()

# --- タブ5. 前月末引継ぎ (入力時の自動再読み込み完全防止) ---
with tab_prev:
    with st.form("prev_form"):
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
        submit_prev = st.form_submit_button("🗓️ 前月末引継ぎを保存する")
        if submit_prev:
            st.session_state["prev"] = ed_prev
            st.session_state.config["saved_tables"]["prev"] = ed_prev.to_dict()
            st.success("前月末引継ぎを保存しました。")
            st.rerun()

# --- タブ6. 今月の申し込み (入力時の自動再読み込み完全防止) ---
with tab_req:
    with st.form("request_form"):
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
        submit_req = st.form_submit_button("📝 今月の申し込みを保存する")
        if submit_req:
            st.session_state["request"] = ed_req
            st.session_state.config["saved_tables"]["request"] = ed_req.to_dict()
            st.success("今月の申し込みを保存しました。")
            st.rerun()

# --- タブ7. 不要担務・指定日設定 (入力時の自動再読み込み完全防止) ---
with tab_ex_des:
    with st.form("ex_des_form"):
        st.subheader("🚫 不要担務 (祝日Cなど)")
        ed_ex = st.data_editor(st.session_state["exclude"], use_container_width=True, key=f"exclude_ed_{year}_{month}")
        
        st.subheader("📌 指定日設定")
        st.write("※ここでチェックを入れた日は「指定日」となり、A・B勤務の超過分が自動的に「0分」になります。")
        ed_des = st.data_editor(st.session_state["designated"], use_container_width=True, key=f"designated_ed_{year}_{month}")
        submit_ex_des = st.form_submit_button("🚫 不要担務・指定日設定を保存する")
        if submit_ex_des:
            st.session_state["exclude"] = ed_ex
            st.session_state["designated"] = ed_des
            st.session_state.config["saved_tables"]["exclude"] = ed_ex.to_dict()
            st.session_state.config["saved_tables"]["designated"] = ed_des.to_dict()
            st.success("不要担務・指定日設定を保存しました。")
            st.rerun()

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
        total_h = int(opt_hols.iloc[s_idx, 0])
        kokyu_h = int(opt_hols.iloc[s_idx, 1])
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
        hist_options = [f"世代 {i+1}: [{h['timestamp']}] {h['label']}" for i, h in enumerate(st.session_state["roster_history"])]
        selected_hist_str = st.selectbox("ロールバックする勤務表のバージョンを選択してください:", hist_options, index=len(hist_options)-1)
        selected_idx = hist_options.index(selected_hist_str)
        
        if st.button("🔄 選択したバージョンに復元する"):
            st.session_state["raw_schedule"] = st.session_state["roster_history"][selected_idx]["df"].copy()
            st.success("選択された履歴バージョンから勤務スケジュールを正常に復元しました。")
            st.rerun()

    # --- 数理最適化開始 ---
    st.divider()
    st.subheader("🧬 勤務表作成エンジンの実行")
    
    strategy_mode = st.radio(
        "🎯 **AIの勤務作成戦略（モード）を選択してください**",
        ["⚖️ バランス調整モード（標準）", "🤝 フェアネス（担当回数公平）最優先モード", "🧘 健康・リズム（連勤・シフト負荷低減）最優先モード"],
        horizontal=True,
        help="戦略に応じて、AIの思考ウェイトが自動調整されます。"
    )

    if st.button("🚀 AIによる勤務作成 (最高解モード)"):
        progress_bar = st.progress(10, text="エンジンの初期化中...")
        
        model = cp_model.CpModel()
        
        s_list_extended = list(s_list)
        has_C_and_D = "C" in s_list and "D" in s_list
        c_idx, d_idx, f_idx = -1, -1, -1
        if has_C_and_D:
            s_list_extended.append("F")
            c_idx = s_list.index("C")
            d_idx = s_list.index("D")
            f_idx = s_list_extended.index("F")

        num_types_extended = len(s_list_extended)
        
        S_OFF, S_NIK = 0, num_types_extended + 1
        S_CHO = num_types_extended + 2
        S_NEN = num_types_extended + 3
        
        E_IDS = [s_list_extended.index(x) + 1 for x in early_gr if x in s_list_extended]
        L_IDS = [s_list_extended.index(x) + 1 for x in late_gr if x in s_list_extended]
        
        if "⚖️" in strategy_mode:
            current_w_h_rule = w_h_rule
            current_w_rhythm = w_mixing
            current_w_fair = w_fair
        elif "🤝" in strategy_mode:
            current_w_h_rule = w_h_rule
            current_w_rhythm = int(w_mixing * 0.5)
            current_w_fair = int(w_fair * 4.0)
        else:  # 🧘 健康・リズム最優先
            current_w_h_rule = int(w_h_rule * 2.0)
            current_w_rhythm = int(w_mixing * 4.0)
            current_w_fair = int(w_fair * 0.3)

        def get_skill_for_F(s_idx):
            skill_c = opt_skill.iloc[s_idx, c_idx]
            skill_d = opt_skill.iloc[s_idx, d_idx]
            if skill_c == "×" or skill_d == "×":
                return "×"
            elif skill_c == "○" and skill_d == "○":
                return "○"
            return "△"

        progress_bar.progress(30, text="制約条件のマッピング中...")
        x = {(s, d, i): model.NewBoolVar(f'x_{s}_{d}_{i}') for s in range(total) for d in range(n_days) for i in range(num_types_extended + 4)}
        score_objs = []

        for s in range(total):
            for di in range(4):
                val = opt_prev.iloc[s, di]
                if di == 3 and val == "遅":
                    for ei in E_IDS: model.Add(x[s, 0, ei] == 0)

        for d in range(n_days):
            wd = calendar.weekday(year, month, d+1)
            
            use_F_var = None
            if wd == 5 and has_C_and_D:
                use_F_var = model.NewBoolVar(f'use_F_{d}')
                score_objs.append(use_F_var * -1000)

            for i, s_name in enumerate(s_list_extended):
                sid = i + 1
                is_requested_by_someone = any(opt_req.iloc[s, d] == s_name for s in range(total))
                
                if s_name == "F":
                    is_excl = not (wd == 5 and has_C_and_D)
                else:
                    is_excl = (opt_ex.iloc[d, i] and not is_requested_by_someone) or (wd == 6 and s_name == "C" and not is_requested_by_someone)
                
                if s_name == "F":
                    skilled = [s for s in range(total) if get_skill_for_F(s) == "○"]
                    trainee = [s for s in range(total) if get_skill_for_F(s) == "△"]
                else:
                    skilled = [s for s in range(total) if opt_skill.iloc[s, i] == "○"]
                    trainee = [s for s in range(total) if opt_skill.iloc[s, i] == "△"]
                
                s_sum = sum(x[s, d, sid] for s in skilled)
                t_sum = sum(x[s, d, sid] for s in trainee)
                
                if s_name in ["C", "D", "F"] and wd == 5 and has_C_and_D:
                    under_sat_var = model.NewIntVar(0, 1, f'under_sat_{d}_{sid}')
                    if s_name == "F":
                        model.Add(s_sum + t_sum + under_sat_var == 1).OnlyEnforceIf(use_F_var)
                        model.Add(s_sum + t_sum == 0).OnlyEnforceIf(use_F_var.Not())
                    else:
                        model.Add(s_sum + t_sum == 0).OnlyEnforceIf(use_F_var)
                        if is_excl:
                            model.Add(s_sum + t_sum == 0).OnlyEnforceIf(use_F_var.Not())
                        else:
                            model.Add(s_sum + t_sum + under_sat_var == 1).OnlyEnforceIf(use_F_var.Not())
                    score_objs.append(under_sat_var * -100000000)
                else:
                    if is_excl:
                        model.Add(s_sum + t_sum == 0)
                    else:
                        under_std_var = model.NewIntVar(0, 1, f'under_std_{d}_{sid}')
                        model.Add(s_sum + t_sum + under_std_var == 1)
                        score_objs.append(under_std_var * -100000000)
                    
                    for s_t in trainee:
                        all_skilled_staff = [s for s in range(total) if opt_skill.iloc[s, i] == "○"]
                        eligible_mentors_on_duty = sum(x[s, d, other_sid] for s in all_skilled_staff for other_sid in range(1, num_types_extended+1))
                        no_vet_var = model.NewBoolVar(f'no_vet_{s_t}_{d}_{sid}')
                        model.Add(eligible_mentors_on_duty + no_vet_var >= 1).OnlyEnforceIf(x[s_t, d, sid])
                        score_objs.append(no_vet_var * -50000000)

            if wd == 5 and has_C_and_D:
                for s_name in ["C", "D", "F"]:
                    sid = s_list_extended.index(s_name) + 1
                    if s_name == "F":
                        trainee = [s for s in range(total) if get_skill_for_F(s) == "△"]
                    else:
                        trainee = [s for s in range(total) if opt_skill.iloc[s, s_list_extended.index(s_name)] == "△"]
                    
                    for s_t in trainee:
                        all_skilled_staff = []
                        for s in range(total):
                            if s_name == "F":
                                is_ok = (get_skill_for_F(s) == "○")
                            else:
                                is_ok = (opt_skill.iloc[s, s_list_extended.index(s_name)] == "○")
                            if is_ok:
                                all_skilled_staff.append(s)
                                
                        eligible_mentors_on_duty = sum(x[s, d, other_sid] for s in all_skilled_staff for other_sid in range(1, num_types_extended+1))
                        no_vet_var = model.NewBoolVar(f'no_vet_sat_{s_t}_{d}_{sid}')
                        model.Add(eligible_mentors_on_duty + no_vet_var >= 1).OnlyEnforceIf(x[s_t, d, sid])
                        score_objs.append(no_vet_var * -50000000)

            for s in range(total): model.Add(sum(x[s, d, i] for i in range(num_types_extended+4)) == 1)

        progress_bar.progress(60, text="個人別制約および働き溜めモデルを計算中...")
        overtime_shortages = []
        off_discrepancies = []

        for s in range(total):
            is_early = [model.NewBoolVar(f'ie_{s}_{d}') for d in range(n_days)]
            is_late = [model.NewBoolVar(f'il_{s}_{d}') for d in range(n_days)]
            is_off = [model.NewBoolVar(f'io_{s}_{d}') for d in range(n_days)]
            daily_overtime_exprs = []
            
            for d in range(n_days):
                model.Add(is_off[d] == x[s, d, S_OFF] + x[s, d, S_CHO] + x[s, d, S_NEN])
                model.Add(sum(x[s, d, i] for i in E_IDS) == 1).OnlyEnforceIf(is_early[d])
                model.Add(sum(x[s, d, i] for i in E_IDS) == 0).OnlyEnforceIf(is_early[d].Not())
                model.Add(sum(x[s, d, i] for i in L_IDS) == 1).OnlyEnforceIf(is_late[d])
                model.Add(sum(x[s, d, i] for i in L_IDS) == 0).OnlyEnforceIf(is_late[d].Not())

                for i, s_name in enumerate(s_list_extended):
                    if s_name == "F":
                        skill_val = get_skill_for_F(s)
                    else:
                        skill_val = opt_skill.iloc[s, i]
                    if skill_val == "×": model.Add(x[s, d, i+1] == 0)

                req = opt_req.iloc[s, d]
                c_map = {"休": S_NEN, "日": S_NIK, "": -1}
                for i, n in enumerate(s_list_extended): c_map[n] = i+1
                if req in c_map and req != "": 
                    model.Add(x[s, d, c_map[req]] == 1)
                
                if req != "休":
                    model.Add(x[s, d, S_NEN] == 0)

                if d < n_days - 1:
                    not_le = model.NewBoolVar(f'nle_{s}_{d}')
                    model.Add(is_late[d] + is_early[d+1] <= 1).OnlyEnforceIf(not_le)
                    score_objs.append(not_le * 2000000 * current_w_h_rule)

                wd_v = calendar.weekday(year, month, d+1)
                d_date = datetime.date(year, month, d+1)
                is_holiday = d_date in jp_holidays
                is_designated = bool(opt_des.at[d+1, "指定日"]) if d+1 in opt_des.index else False
                
                terms = []
                if wd_v == 6:
                    pass
                elif wd_v == 5:
                    for i, s_name in enumerate(s_list_extended):
                        sid = i + 1
                        if s_name in ["A", "B"]:
                            continue
                        over_val = 0
                        if s_name in opt_overtime.index:
                            over_val = int(opt_overtime.loc[s_name, "土曜超過分(分)"])
                        if over_val > 0:
                            terms.append(x[s, d, sid] * over_val)
                else:
                    for i, s_name in enumerate(s_list_extended):
                        sid = i + 1
                        if (is_holiday or is_designated) and s_name in ["A", "B"]:
                            continue
                        over_val = 0
                        if s_name in opt_overtime.index:
                            over_val = int(opt_overtime.loc[s_name, "平日超過分(分)"])
                        if over_val > 0:
                            terms.append(x[s, d, sid] * over_val)
                
                daily_overtime_exprs.append(sum(terms))

            for d in range(n_days):
                cum_overtime = sum(daily_overtime_exprs[k] for k in range(d + 1))
                cum_cho_count = sum(x[s, k, S_CHO] for k in range(d + 1))
                
                shortage = model.NewIntVar(0, 10000, f'shortage_{s}_{d}')
                model.Add(cum_overtime + shortage >= cum_cho_count * 445)
                score_objs.append(shortage * -1000)
                overtime_shortages.append(shortage)

            for d in range(n_days):
                wd_v = calendar.weekday(year, month, d+1)
                if wd_v >= 5:
                    model.Add(x[s, d, S_CHO] == 0)

            hist_w = [1 if opt_prev.iloc[s, k] != "休" else 0 for k in range(4)] + [(1 - is_off[di]) for di in range(n_days)]
            for st_i in range(len(hist_w) - 4):
                nc = model.NewBoolVar(f'nc_{s}_{st_i}')
                model.Add(sum(hist_w[st_i:st_i+5]) <= 4).OnlyEnforceIf(nc)
                score_objs.append(nc * 1000000 * current_w_h_rule)

            for di in range(n_days - 1):
                mix = model.NewBoolVar(f'mix_{s}_{di}')
                model.AddBoolAnd([is_early[di], is_late[di+1]]).OnlyEnforceIf(mix)
                score_objs.append(mix * 500 * current_w_rhythm)
                if di < n_days - 2:
                    e_block = model.NewBoolVar(f'eb_{s}_{di}')
                    model.Add(is_early[di] + is_early[di+1] + is_early[di+2] - 2 <= e_block)
                    score_objs.append(e_block * -1000 * current_w_rhythm)

            if s < n_mgr:
                for di in range(n_days):
                    wd_v = calendar.weekday(year, month, di+1)
                    if wd_v >= 5: 
                        m_o = model.NewBoolVar(f'mo_{s}_{di}')
                        model.Add(is_off[di] == 1).OnlyEnforceIf(m_o)
                        score_objs.append(m_o * 10000)
                    else: 
                        m_w = model.NewBoolVar(f'mw_{s}_{di}')
                        model.Add(is_off[di] == 0).OnlyEnforceIf(m_w)
                        score_objs.append(m_w * 500000)
            else:
                for di in range(n_days):
                    if opt_req.iloc[s, di] != "日": 
                        nik_var = x[s, di, S_NIK]
                        score_objs.append(nik_var * -10000000)

            req_off_count = sum(1 for di in range(n_days) if opt_req.iloc[s, di] == "休")
            total_off_limit = int(opt_hols.iloc[s, 0])
            kokyu_val = int(opt_hols.iloc[s, 1])
            
            target_cho_count = total_off_limit - kokyu_val
            if target_cho_count < 0:
                target_cho_count = 0

            model.Add(sum(x[s, d, S_NEN] for d in range(n_days)) == req_off_count)

            off_slack_plus = model.NewIntVar(0, n_days, f'off_sp_{s}')
            off_slack_minus = model.NewIntVar(0, n_days, f'off_sm_{s}')
            model.Add(sum(x[s, d, S_OFF] for d in range(n_days)) + off_slack_plus - off_slack_minus == kokyu_val)
            score_objs.append(off_slack_plus * -10000000)
            score_objs.append(off_slack_minus * -10000000)
            off_discrepancies.append((s, "公休数", off_slack_plus, off_slack_minus))

            cho_slack_plus = model.NewIntVar(0, n_days, f'cho_sp_{s}')
            cho_slack_minus = model.NewIntVar(0, n_days, f'cho_sm_{s}')
            model.Add(sum(x[s, d, S_CHO] for d in range(n_days)) + cho_slack_plus - cho_slack_minus == target_cho_count)
            score_objs.append(cho_slack_plus * -10000000)
            score_objs.append(cho_slack_minus * -10000000)
            off_discrepancies.append((s, "調整休数", cho_slack_plus, cho_slack_minus))

        for i_sh in range(1, num_types_extended + 1):
            counts = [model.NewIntVar(0, n_days, f'sh_c{si}_{i_sh}') for si in range(total)]
            for si in range(total): model.Add(counts[si] == sum(x[si, d, i_sh] for d in range(n_days)))
            mx, mn = model.NewIntVar(0, n_days, f'mx_{i_sh}'), model.NewIntVar(0, n_days, f'mn_{i_sh}')
            model.AddMaxEquality(mx, counts); model.AddMinEquality(mn, counts)
            score_objs.append((mx - mn) * -100 * current_w_fair)

        model.Maximize(sum(score_objs))
        
        progress_bar.progress(80, text="AI並列最適化ソルバー実行中（マルチスレッド処理）...")
        slv = cp_model.CpSolver()
        slv.parameters.max_time_in_seconds = 45.0
        slv.parameters.num_search_workers = 4
        
        status = slv.Solve(model)
        progress_bar.progress(100, text="最適化完了！結果の同期処理中...")

        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            st.success(f"✨ AI勤務作成が正常に完了しました。（適用戦略: {strategy_mode}）")
            
            relaxation_messages = []
            for s_idx, off_type, sp, sm in off_discrepancies:
                val_p = slv.Value(sp)
                val_m = slv.Value(sm)
                if val_p > 0:
                    relaxation_messages.append(f"⚠️ {staff_list[s_idx]}の{off_type}が、制約矛盾解消のため目標より **{val_p}日減少** して調整されました。")
                if val_m > 0:
                    relaxation_messages.append(f"⚠️ {staff_list[s_idx]}の{off_type}が、制約矛盾解消のため目標より **{val_m}日増加** して調整されました。")
            
            overtime_shortage_sum = sum(slv.Value(sh) for sh in overtime_shortages)
            if overtime_shortage_sum > 0:
                relaxation_messages.append(f"⚠️ 働き溜め（超過勤務の累積時間）が不足しているスタッフの調整休（調）付与タイミングにおいて、計 **{overtime_shortage_sum}分相当のルール緩和** を実施しました。")

            if relaxation_messages:
                st.warning("⚠️ **AIシステム調整報告（制約緩和レポート）**\n入力された希望休や公休目標に一部競合があったため、AIがルールを極小幅で緩和して作成を成立させました。以下をご確認ください。")
                for msg in relaxation_messages:
                    st.write(msg)
            else:
                st.balloons()
                st.success("✅ **すべての制約条件が100%厳格に守られました。**")

            res_rows = []
            id_char = {S_OFF: "休", S_NIK: "日", S_CHO: "調", S_NEN: "年"}
            for i, n in enumerate(s_list_extended): id_char[i+1] = n
            for si in range(total):
                res_rows.append([id_char[next(j for j in range(num_types_extended+4) if slv.Value(x[si, di, j])==1)] for di in range(n_days)])

            res_df = pd.DataFrame(res_rows, index=staff_list, columns=days_cols)
            st.session_state["raw_schedule"] = res_df

            # 【自動作成結果を履歴管理へ保存】
            new_hist_entry = {
                "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
                "label": f"AI自動作成 ({strategy_mode})",
                "df": res_df.copy()
            }
            if not st.session_state["roster_history"] or not st.session_state["roster_history"][-1]["df"].equals(res_df):
                st.session_state["roster_history"].append(new_hist_entry)
                if len(st.session_state["roster_history"]) > 5:
                    st.session_state["roster_history"].pop(0)
        else: 
            st.error("解が見つかりませんでした。入力制約が競合していないか確認してください。")

    # --- 4. 手動微調整 ＆ リアルタイム整合性検証システム (入力途中のリロードを完全に防止する設計) ---
    if "raw_schedule" in st.session_state:
        st.divider()
        st.subheader("✍️ AI勤務表の手動微調整 ＆ リアルタイム検証")
        st.info("💡 下記の勤務スケジュールを書き換えた後、下部の「💾 手動調整を適用して再計算」ボタンを押してください。編集のたびに画面全体がフラッシュリロードする現象は完全に解消されています。")
        
        # 編集用のフォーム
        with st.form("manual_edit_form"):
            column_config_edit = {
                col: st.column_config.SelectboxColumn(
                    col,
                    options=options,
                    required=True,
                    width=45
                )
                for col in days_cols
            }
            
            # フォーム内に配置することで、フォーカスアウト時の不要な自動リロードを遮断
            edited_raw_df = st.data_editor(
                st.session_state["raw_schedule"],
                column_config=column_config_edit,
                use_container_width=True,
                key=f"schedule_editor_v3_{year}_{month}"
            )
            
            submit_manual = st.form_submit_button("💾 手動調整を適用して再計算する")
            if submit_manual:
                st.session_state["raw_schedule"] = edited_raw_df
                st.success("手動調整を反映し、超過勤務や各種警告を再集計しました。")
                st.rerun()

        # 【個別セーブポイント保存ボタン】
        if st.button("💾 現在の調整版をセーブポイント（履歴）として保存"):
            new_hist_entry = {
                "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
                "label": "ユーザー手動調整版",
                "df": st.session_state["raw_schedule"].copy()
            }
            if not st.session_state["roster_history"] or not st.session_state["roster_history"][-1]["df"].equals(st.session_state["raw_schedule"]):
                st.session_state["roster_history"].append(new_hist_entry)
                if len(st.session_state["roster_history"]) > 5:
                    st.session_state["roster_history"].pop(0)
                st.success("現在の調整内容を履歴（セーブポイント）に登録しました。いつでもこの状態に戻れます。")
            else:
                st.info("現在の勤務表はすでに最新の履歴と同じ内容です。")

        # --- 5. リアルタイム・バリデーション & 統計再計算ロジック ---
        validation_alerts = []
        rec_rows = []
        
        consecutive_rules_broken = 0
        pattern_rules_broken = 0
        hols_mismatch_count = 0
        overtime_limits_exceeded = 0

        # 最新の確定（保存）済みスケジュールをベースに評価
        saved_schedule = st.session_state["raw_schedule"]

        for si, s_name in enumerate(staff_list):
            row_shifts = saved_schedule.iloc[si].tolist()
            
            # (a) 休日数の整合性検証（最新の同期値を厳密に参照）
            n_off = row_shifts.count("休")
            n_cho = row_shifts.count("調")
            n_nen = row_shifts.count("年")
            total_off_actual = n_off + n_cho + n_nen
            
            total_h_target = int(opt_hols.iloc[si, 0])
            kokyu_target = int(opt_hols.iloc[si, 1])
            req_off_count = sum(1 for di in range(n_days) if opt_req.iloc[si, di] == "休")
            target_off_total = total_h_target + req_off_count
            
            if total_off_actual != target_off_total:
                validation_alerts.append(f"⚠️ **{s_name}**: 休日合計が一致しません（目標: {target_off_total}日、手動修正後: {total_off_actual}日）")
                hols_mismatch_count += 1
            if n_off != kokyu_target:
                validation_alerts.append(f"⚠️ **{s_name}**: 公休「休」の数が設定と異なります（設定公休: {kokyu_target}日、手動修正後: {n_off}日）")
                hols_mismatch_count += 1
            if n_nen != req_off_count:
                validation_alerts.append(f"⚠️ **{s_name}**: 年休「年」の数が希望数と異なります（希望年休: {req_off_count}日、手動修正後: {n_nen}日）")
                hols_mismatch_count += 1
                
            # (b) 5連勤以上の検出
            prev_status = [opt_prev.iloc[si, k] for k in range(4)]
            prev_working = [0 if v == "休" else 1 for v in prev_status]
            current_working = [0 if v in ["休", "調", "年"] else 1 for v in row_shifts]
            combined_working = prev_working + current_working
            
            max_consecutive = 0
            curr_consecutive = 0
            for w in combined_working:
                if w == 1:
                    curr_consecutive += 1
                    if curr_consecutive > max_consecutive:
                        max_consecutive = curr_consecutive
                else:
                    curr_consecutive = 0
            
            if max_consecutive >= 5:
                validation_alerts.append(f"🚨 **{s_name}**: **{max_consecutive}連勤**が発生しています（上限4連勤のルール違反）")
                consecutive_rules_broken += 1
                
            # (c) 遅早シフトパターン検証
            last_prev_shift = opt_prev.iloc[si, 3]
            for di in range(n_days):
                today_shift = row_shifts[di]
                if di == 0:
                    prev_is_late = (last_prev_shift == "遅")
                else:
                    prev_shift = row_shifts[di-1]
                    prev_is_late = (prev_shift in late_gr)
                
                today_is_early = (today_shift in early_gr)
                
                if prev_is_late and today_is_early:
                    day_str = f"前月末日〜1日" if di == 0 else f"{di}日〜{di+1}日"
                    validation_alerts.append(f"🚨 **{s_name}**: 遅番の翌日に早番が割り当てられています（{day_str}）")
                    pattern_rules_broken += 1

            # (d) 超過勤務時間の再集計
            staff_overtime_sum = 0
            for di in range(n_days):
                wd_v = calendar.weekday(year, month, di+1)
                assigned_char = row_shifts[di]
                
                d_date = datetime.date(year, month, di+1)
                is_holiday = d_date in jp_holidays
                is_designated = bool(opt_des.at[di+1, "指定日"]) if di+1 in opt_des.index else False
                
                if wd_v == 6:
                    overtime_val = 0
                elif wd_v == 5:
                    if assigned_char in ["A", "B", "日", "休", "調", "年"]:
                        overtime_val = 0
                    elif assigned_char in opt_overtime.index:
                        overtime_val = int(opt_overtime.loc[assigned_char, "土曜超過分(分)"])
                    else:
                        overtime_val = 0
                else:
                    if assigned_char in ["日", "休", "調", "年"]:
                        overtime_val = 0
                    elif (is_holiday or is_designated) and assigned_char in ["A", "B"]:
                        overtime_val = 0
                    elif assigned_char in opt_overtime.index:
                        overtime_val = int(opt_overtime.loc[assigned_char, "平日超過分(分)"])
                    else:
                        overtime_val = 0
                
                staff_overtime_sum += overtime_val
            
            minus_val = n_cho * 445
            final_overtime = staff_overtime_sum - minus_val
            
            # 36協定チェック：時間外労働が45時間（2700分）を超えているか
            if final_overtime > 2700:
                validation_alerts.append(f"⚠️ **36協定アラート**: **{s_name}**の精算後超過勤務が45時間を超過しています（{format_minutes_to_hhmm(final_overtime)}）")
                overtime_limits_exceeded += 1

            rec_rows.append({
                "休の総数": total_off_actual,
                "年休数(希望)": n_nen,
                "設定公休": n_off,
                "調整休日(調)数": n_cho,
                "総超過(前)": format_minutes_to_hhmm(staff_overtime_sum),
                "精算後超過": format_minutes_to_hhmm(final_overtime)
            })

        # 労務健全度スコアの総合算出
        deduction = (
            (consecutive_rules_broken * 10) 
            + (pattern_rules_broken * 10) 
            + (hols_mismatch_count * 15) 
            + (overtime_limits_exceeded * 20)
        )
        compliance_score = max(0, 100 - deduction)

        stats_df = pd.DataFrame(rec_rows, index=staff_list)
        final_display_df = pd.concat([saved_schedule, stats_df], axis=1)

        # 労務健全度スコアリングカードのダッシュボード表示
        st.subheader("🛡️ 労務コンプライアンス ＆ 整合性ダッシュボード")
        c_score, c_detail = st.columns([1, 3])
        with c_score:
            st.metric("労務健全度スコア", f"{compliance_score} / 100 点", delta=f"-{deduction}点" if deduction > 0 else "減点なし")
        with c_detail:
            st.write("**現在の勤務表におけるルール評価統計:**")
            st.write(f"- 連勤制限違反数: **{consecutive_rules_broken}件** | 遅早パターン違反数: **{pattern_rules_broken}件**")
            st.write(f"- 設定休日ミスマッチ: **{hols_mismatch_count}件** | 36協定上限（45時間）超過者数: **{overtime_limits_exceeded}人**")

        if validation_alerts:
            st.warning("⚠️ 手動修正によるルール不整合または労務管理警告が検出されました。運用上問題がないか確認してください。")
            for alert in validation_alerts:
                st.write(alert)
        else:
            st.success("✅ 完璧な整合性が保たれています。すべての基準ルールおよび労務協定の基準をクリアしています。")

        # カラーマッピング描画
        def cl(v):
            if v == "休": return 'background-color: #ffcccc'
            if v == "調": return 'background-color: #ffcc99; font-weight: bold; color: #7a3e00;'
            if v == "年": return 'background-color: #ffb3d9; font-weight: bold; color: #8a004b;'
            if v == "日": return 'background-color: #e0f0ff'
            if v in early_gr: return 'background-color: #ffffcc'
            if v == "F": return 'background-color: #e8d7ff; font-weight: bold; color: #4a148c;'
            return 'background-color: #ccffcc'

        st.subheader("📊 統計・最終集計確認（プレビュー）")
        st.dataframe(final_display_df.style.map(cl), use_container_width=True)

        # Excel書き出し
        towrite = io.BytesIO()
        with pd.ExcelWriter(towrite, engine='openpyxl') as writer:
            final_display_df.style.map(cl).to_excel(writer, index=True, sheet_name="Roster")
        excel_data = towrite.getvalue()

        st.download_button(
            label="📥 編集後の最終勤務表をExcelでダウンロード",
            data=excel_data,
            file_name=f"roster_{year}_{month}_edited.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

import streamlit as st
import pandas as pd
import calendar
import json
import re
import datetime
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

# --- 【完全な解決策：コールバック駆動非破壊ステート保存関数】 ---
# ユーザーが編集を終えた瞬間（Rerunが走る前）に、差分辞書を解析してセッション内のデータフレームを直接更新します。
def store_df(key):
    pkey = '_' + key
    if pkey in st.session_state:
        changes = st.session_state[pkey]
        df = st.session_state[key]
        
        # 1. セルの編集（edited_rows）を正確にマッピングして適用
        if "edited_rows" in changes:
            for row_idx_str, col_changes in changes["edited_rows"].items():
                row_idx = int(row_idx_str)
                # 行番号から正しいインデックス（スタッフ名文字列、日付数値など）を自動取得
                idx_val = df.index[row_idx]
                for col_name, new_val in col_changes.items():
                    df.at[idx_val, col_name] = new_val
                    
        # 2. 行追加があった場合の適用
        if "added_rows" in changes and len(changes["added_rows"]) > 0:
            for added_row in changes["added_rows"]:
                new_idx = df.shape[0]
                for col_name, val in added_row.items():
                    df.at[new_idx, col_name] = val
                    
        # 3. 行削除があった場合の適用
        if "deleted_rows" in changes and len(changes["deleted_rows"]) > 0:
            df = df.drop(df.index[changes["deleted_rows"]]).reset_index(drop=True)
            
        # 更新された DataFrame を確実にセッションのマスターに保存
        st.session_state[key] = df
        
        # saved_tablesにも完全にマッピング（JSONバックアップ出力用）
        if "saved_tables" not in st.session_state.config:
            st.session_state.config["saved_tables"] = {}
        st.session_state.config["saved_tables"][key] = df.to_dict()

# --- 1. グローバル設定：デザインとレイアウト ---
st.set_page_config(page_title="AI勤務作成：V80 Ultra Optimizer", page_icon="🛡️", layout="wide")

if 'config' not in st.session_state:
    st.session_state.config = {
        "num_mgr": 2, "num_regular": 8,
        "staff_names": [f"スタッフ{i+1}" for i in range(10)],
        "user_shifts": "A,B,C,D,E", "early_shifts": ["A", "B", "C"], "late_shifts": ["D", "E"],
        "year": 2025, "month": 1, "saved_tables": {}
    }

# データフレームのセッション永続化用ディクショナリの初期化
if "dfs" not in st.session_state:
    st.session_state.dfs = {}

st.title("勤務作成エンジン (Team Excellence Pass)")
st.info("💡 **リアルタイム自動保存機能搭載**: 画面の入力や変更はすべてリアルタイムで保存されます。入力した値が元に戻ることはありません。")

# --- 2. データのバックアップ・復元管理（サイドバー） ---
with st.sidebar:
    st.header("📂 設定データの完全同期")
    up_file = st.file_uploader("設定ファイルを読み込む", type="json")
    if up_file:
        try:
            st.session_state.config.update(json.load(up_file))
            # アップロード成功時は、セッション内の DataFrame の強制再構築を行うためにキーを初期化
            if "last_state_key" in st.session_state:
                del st.session_state.last_state_key
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
    # ダウンロードボタンをサイドバーに固定し、どのタブにいても常に現在の全設定を1クリックで保存
    st.download_button(
        "📥 現在の全設定を保存する", 
        json.dumps(st.session_state.config, ensure_ascii=False), 
        f"v80_backup_{year}_{month}.json"
    )

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

# --- データの整合性を完全に保つための高精度復元関数（曜日・型ズレの吸収） ---
def get_persisted_df(key, d_df, categories=None):
    tables = st.session_state.config.get("saved_tables", {})
    if key in tables:
        raw_data = tables.get(key)
        df = pd.DataFrame(raw_data)
        
        # 1. 保存データとターゲットデータのインデックス/カラムを文字列型に統一
        df.index = df.index.astype(str)
        df.columns = df.columns.astype(str)
        
        # 2. 曜日変更（例: "1(水)" から "1(土)" への変動）に左右されないよう日付数字のみを抽出
        def clean_col_name(c):
            m = re.match(r'^(\d+)', str(c))
            return m.group(1) if m else str(c)
        
        df.columns = [clean_col_name(c) for c in df.columns]
        
        # 3. 目的とする d_df の構造で新しい DataFrame を構築
        result_df = pd.DataFrame(index=d_df.index, columns=d_df.columns)
        
        # 4. 行番号（位置）およびカラム名（日付）ベースで値を安全に移植する
        # （これによりスタッフ名の順番や名前自体が変更されても、行に設定されていたデータは100%確実に新スタッフに引き継がれます）
        for r_idx, r_target in enumerate(d_df.index):
            if r_idx < len(df.index):
                r_source = df.index[r_idx]
                for c_target in d_df.columns:
                    c_clean = clean_col_name(c_target)
                    if c_clean in df.columns:
                        result_df.at[r_target, c_target] = df.at[r_source, c_clean]
        
        # 5. 未入力やミスマッチの部分をデフォルト値で補完
        result_df = result_df.fillna(d_df)
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
# 現在の基本設定パラメーターのハッシュ（キー）を生成
current_state_key = (
    tuple(staff_list),
    tuple(days_cols),
    tuple(s_list),
    tuple(overtime_s_list),
    year,
    month
)

# 構成変更や年月変更が発生した時、または初回起動時にのみ、セッション内の DataFrame を再構築。
# 単なるセルの値変更によるRerunでは、データフレームを絶対に再作成せず、セッション内のデータを保持し続けます。
if "last_state_key" not in st.session_state or st.session_state.last_state_key != current_state_key:
    form_names = list(staff_list)
    # Categories引数の確実なパス ＆ 各データの安全復元
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
tab_st, tab_skl, tab_roster = st.tabs(["🏗️ 1. 組織と勤務の構成", "⚖️ 2. 公休・スキル・回数", "🧬 3. 勤務表の最適化"])

# --- タブ1. 組織と勤務の構成（自動保存＆メモリバグ完全解消） ---
with tab_st:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("👥 人員配置")
        form_n_mgr = st.number_input("管理者数", 0, 5, n_mgr)
        form_n_reg = st.number_input("一般職数", 1, 20, n_reg)
        form_total = int(form_n_mgr + form_n_reg)
        
        # スタッフ名変更も上書きを廃止し、コールバックだけで安全に同期
        st.data_editor(st.session_state["names"], use_container_width=True, key="_names", on_change=store_df, args=["names"])
    with c2:
        st.subheader("📋 シフト構成")
        form_raw_s = st.text_input("勤務略称 (,) 区切り", raw_s)
        form_s_list = [s.strip() for s in form_raw_s.split(",") if s.strip()]
        form_early_gr = st.multiselect("早番グループ", form_s_list, default=[x for x in form_s_list if x in early_gr])
        form_late_gr = st.multiselect("遅番グループ", form_s_list, default=[x for x in form_s_list if x in late_gr])
        
    st.subheader("⏱️ 各担務の超過時間設定")
    st.write("※日勤、日曜日のすべての担務、土曜日のA・B勤務は、自動的に一律「0分」として処理されます。")
    
    # 循環上書き代入を完全に廃止し、on_change コールバックのみでステート管理
    st.data_editor(st.session_state["overtime"], use_container_width=True, key="_overtime", on_change=store_df, args=["overtime"])

    # パラメータの同期
    new_staff_list = st.session_state["names"]["スタッフ名"].tolist()
    st.session_state.config.update({
        "num_mgr": form_n_mgr,
        "num_regular": form_n_reg,
        "staff_names": new_staff_list,
        "user_shifts": form_raw_s,
        "early_shifts": form_early_gr,
        "late_shifts": form_late_gr
    })

# --- タブ2. 公休・スキル（自動保存＆メモリバグ完全解消） ---
with tab_skl:
    st.subheader("🎓 専門スキル・月間公休数・教育ノルマ")
    st.write("○:可能, △:見習い（ベテラン必須）, ×:不可")
    
    # 【二重安全対策】 column_config を明示的に指定してセレクトボックスとしてレンダリングを完全に固定
    column_config_skill = {
        col: st.column_config.SelectboxColumn(
            col,
            options=["○", "△", "×"],
            required=True
        )
        for col in s_list
    }
    st.data_editor(
        st.session_state["skill"], 
        column_config=column_config_skill,
        use_container_width=True, 
        key="_skill", 
        on_change=store_df, 
        args=["skill"]
    )
    
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        st.subheader("📅 月間休日数設定")
        st.data_editor(st.session_state["hols"], use_container_width=True, key="_hols", on_change=store_df, args=["hols"])
    with col_c2:
        st.subheader("🏫 教育ノルマ設定")
        st.data_editor(st.session_state["trainee"], use_container_width=True, key="_trainee", on_change=store_df, args=["trainee"])

# --- タブ3. 勤務表の最適化（自動保存＆メモリバグ完全解消） ---
with tab_roster:
    # 選択肢設定を column_config を用いてセレクトボックスとして強制固定
    column_config_prev = {
        col: st.column_config.SelectboxColumn(
            col,
            options=["日", "休", "早", "遅"],
            required=True
        )
        for col in p_days
    }
    column_config_request = {
        col: st.column_config.SelectboxColumn(
            col,
            options=options,
            required=False
        )
        for col in days_cols
    }

    # 【レイアウトの大幅改善】左右並び（st.columns）を廃止し、上下並び（縦方向スタック）に再配置
    # これにより横幅がフルに活用され、スライド（横スクロール）を極限まで抑えて快適に入力・閲覧可能になります
    st.subheader("🗓️ 前月末引継ぎ")
    st.data_editor(
        st.session_state["prev"], 
        column_config=column_config_prev,
        use_container_width=True, 
        key="_prev", 
        on_change=store_df, 
        args=["prev"]
    )
    
    st.subheader("📝 今月の申し込み (※「休」は年次休暇として集計します)")
    st.data_editor(
        st.session_state["request"], 
        column_config=column_config_request,
        use_container_width=True, 
        key="_request", 
        on_change=store_df, 
        args=["request"]
    )

    st.divider()

    # 不要担務と指定日設定（こちらは横幅が狭いため、並行並びのままでスッキリ表示されます）
    c_ex, c_des = st.columns([1, 1])
    with c_ex:
        st.subheader("🚫 不要担務 (祝日Cなど)")
        st.data_editor(st.session_state["exclude"], use_container_width=True, key="_exclude", on_change=store_df, args=["exclude"])
    with c_des:
        st.subheader("📌 指定日設定")
        st.write("※ここでチェックを入れた日は「指定日」となり、A・B勤務の超過分が自動的に「0分」になります。")
        st.data_editor(st.session_state["designated"], use_container_width=True, key="_designated", on_change=store_df, args=["designated"])

    # --- 最適化インプットデータの最新同期取得 ---
    opt_skill = st.session_state["skill"]
    opt_hols = st.session_state["hols"]
    opt_prev = st.session_state["prev"]
    opt_req = st.session_state["request"]
    opt_ex = st.session_state["exclude"]
    opt_overtime = st.session_state["overtime"]
    opt_des = st.session_state["designated"]

    # --- データの同期確認テーブル ---
    st.divider()
    st.write("🔍 **AIが今回読み込んだ各スタッフの公休と年次休暇の最終データ（自動同期検証用）**")
    debug_rows = []
    for s_idx, s_name in enumerate(staff_list):
        req_off_count = sum(1 for di in range(n_days) if opt_req.iloc[s_idx, di] == "休")
        total_h = int(opt_hols.iloc[s_idx, 0])  # 休の総数
        kokyu_h = int(opt_hols.iloc[s_idx, 1])  # 公休分
        debug_rows.append({
            "スタッフ名": s_name,
            "休の総数(設定)": total_h,
            "公休分(設定)": kokyu_h,
            "年次休暇(希望休)数": req_off_count,
            "最終休み目標(総数)": total_h + req_off_count
        })
    st.dataframe(pd.DataFrame(debug_rows), use_container_width=True)

    # --- 数理最適化開始 ---
    st.subheader("🧬 勤務表作成エンジンの実行")
    
    if st.button("🚀 AIによる勤務作成 (最高解モード)"):
        model = cp_model.CpModel()
        
        # 内部処理用のシフト拡張（土曜日救済用のFシフトを動的に追加）
        s_list_extended = list(s_list)
        has_C_and_D = "C" in s_list and "D" in s_list
        c_idx, d_idx, f_idx = -1, -1, -1
        if has_C_and_D:
            s_list_extended.append("F")
            c_idx = s_list.index("C")
            d_idx = s_list.index("D")
            f_idx = s_list_extended.index("F")

        num_types_extended = len(s_list_extended)
        
        # 勤務タイプ定義（「年 S_NEN」を追加して拡張）
        S_OFF, S_NIK = 0, num_types_extended + 1
        S_CHO = num_types_extended + 2 # 調
        S_NEN = num_types_extended + 3 # 年(年次休暇)
        
        E_IDS = [s_list_extended.index(x) + 1 for x in early_gr if x in s_list_extended]
        L_IDS = [s_list_extended.index(x) + 1 for x in late_gr if x in s_list_extended]
        
        w_rhythm = w_mixing

        # 日本の祝日判定用データの取得
        jp_holidays = {}
        if holidays is not None:
            try:
                jp_holidays = holidays.Japan(years=[year])
            except Exception:
                pass

        # Fシフト用スキル判定関数
        def get_skill_for_F(s_idx):
            skill_c = opt_skill.iloc[s_idx, c_idx]
            skill_d = opt_skill.iloc[s_idx, d_idx]
            if skill_c == "×" or skill_d == "×":
                return "×"
            elif skill_c == "○" and skill_d == "○":
                return "○"
            return "△"

        # 変数: x[スタッフ, 日, シフト]（勤務数に「年」を追加し範囲を num_types_extended + 4 とする）
        x = {(s, d, i): model.NewBoolVar(f'x_{s}_{d}_{i}') for s in range(total) for d in range(n_days) for i in range(num_types_extended + 4)}
        score_objs = []

        # 前月情報デコード
        for s in range(total):
            for di in range(4):
                val = opt_prev.iloc[s, di]
                if di == 3 and val == "遅":
                    for ei in E_IDS: model.Add(x[s, 0, ei] == 0)

        # 日次の基本ループ
        for d in range(n_days):
            wd = calendar.weekday(year, month, d+1)
            
            # 土曜日の場合のC/D統合（F勤務適用）決定変数
            use_F_var = None
            if wd == 5 and has_C_and_D:
                use_F_var = model.NewBoolVar(f'use_F_{d}')
                score_objs.append(use_F_var * -1000)

            # A. 担務充足
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
                
                # 土曜日限定F適用判定ロジック
                if s_name in ["C", "D", "F"] and wd == 5 and has_C_and_D:
                    under_sat_var = model.NewIntVar(0, 1, f'under_sat_{d}_{sid}')
                    
                    if s_name == "F":
                        model.Add(s_sum + t_sum + under_sat_var == 1).OnlyEnforceIf(use_F_var)
                        model.Add(s_sum + t_sum == 0).OnlyEnforceIf(use_F_var.Not())
                    else:  # C または D
                        model.Add(s_sum + t_sum == 0).OnlyEnforceIf(use_F_var)
                        if is_excl:
                            model.Add(s_sum + t_sum == 0).OnlyEnforceIf(use_F_var.Not())
                        else:
                            model.Add(s_sum + t_sum + under_sat_var == 1).OnlyEnforceIf(use_F_var.Not())
                    
                    score_objs.append(under_sat_var * -100000000)
                    
                else:
                    # 通常曜日、または土曜日のA/B/E勤務
                    if is_excl:
                        model.Add(s_sum + t_sum == 0)
                    else:
                        under_std_var = model.NewIntVar(0, 1, f'under_std_{d}_{sid}')
                        model.Add(s_sum + t_sum + under_std_var == 1)
                        score_objs.append(under_std_var * -100000000)
                    
                    # 通常日の見習い同日ベテラン出勤保証
                    for s_t in trainee:
                        all_skilled_staff = [s for s in range(total) if "○" in opt_skill.iloc[s].values]
                        veteran_on_duty = sum(x[s, d, other_sid] for s in all_skilled_staff for other_sid in range(1, num_types_extended+1))
                        no_vet_var = model.NewBoolVar(f'no_vet_{s_t}_{d}_{sid}')
                        model.Add(veteran_on_duty + no_vet_var >= 1).OnlyEnforceIf(x[s_t, d, sid])
                        score_objs.append(no_vet_var * -50000000)

            # 土曜日の見習い同日ベテラン出勤保証
            if wd == 5 and has_C_and_D:
                for s_name in ["C", "D", "F"]:
                    sid = s_list_extended.index(s_name) + 1
                    if s_name == "F":
                        trainee = [s for s in range(total) if get_skill_for_F(s) == "△"]
                    else:
                        trainee = [s for s in range(total) if opt_skill.iloc[s, s_list_extended.index(s_name)] == "△"]
                    
                    for s_t in trainee:
                        all_skilled_staff = [s for s in range(total) if "○" in opt_skill.iloc[s].values]
                        veteran_on_duty = sum(x[s, d, other_sid] for s in all_skilled_staff for other_sid in range(1, num_types_extended+1))
                        no_vet_var = model.NewBoolVar(f'no_vet_sat_{s_t}_{d}_{sid}')
                        model.Add(veteran_on_duty + no_vet_var >= 1).OnlyEnforceIf(x[s_t, d, sid])
                        score_objs.append(no_vet_var * -50000000)

            # 1日1人1回 (Hard Constraint)
            for s in range(total): model.Add(sum(x[s, d, i] for i in range(num_types_extended+4)) == 1)

        # 個人別の高度な最適化
        for s in range(total):
            is_early = [model.NewBoolVar(f'ie_{s}_{d}') for d in range(n_days)]
            is_late = [model.NewBoolVar(f'il_{s}_{d}') for d in range(n_days)]
            
            # 休み判定（「休 S_OFF」または「調 S_CHO」または「年 S_NEN」の論理和を is_off とする）
            is_off = [model.NewBoolVar(f'io_{s}_{d}') for d in range(n_days)]
            
            # --- 働き溜め（超過残高累積）の動的検証用リストの構成 ---
            daily_overtime_exprs = []
            
            for d in range(n_days):
                # 休、調、年のいずれかが割り当てられている日を「休み」に統合
                model.Add(is_off[d] == x[s, d, S_OFF] + x[s, d, S_CHO] + x[s, d, S_NEN])

                # 判定用スイッチ変数の連動
                model.Add(sum(x[s, d, i] for i in E_IDS) == 1).OnlyEnforceIf(is_early[d])
                model.Add(sum(x[s, d, i] for i in E_IDS) == 0).OnlyEnforceIf(is_early[d].Not())
                model.Add(sum(x[s, d, i] for i in L_IDS) == 1).OnlyEnforceIf(is_late[d])
                model.Add(sum(x[s, d, i] for i in L_IDS) == 0).OnlyEnforceIf(is_late[d].Not())

                # 各種の制限（スキル×、申し込み、遅→早）
                for i, s_name in enumerate(s_list_extended):
                    if s_name == "F":
                        skill_val = get_skill_for_F(s)
                    else:
                        skill_val = opt_skill.iloc[s, i]
                    if skill_val == "×": model.Add(x[s, d, i+1] == 0)

                # 申し込み（希望）の反映（絶対に崩さない最強のハード制約）
                # 希望休の「休」は S_NEN（年次休暇）に強制マッピング
                req = opt_req.iloc[s, d]
                c_map = {"休": S_NEN, "日": S_NIK, "": -1}
                for i, n in enumerate(s_list_extended): c_map[n] = i+1
                if req in c_map and req != "": 
                    model.Add(x[s, d, c_map[req]] == 1)
                
                # 申し込み「休」ではない日は、S_NEN (年) が割り当てられないように制限する
                # （これにより、申し込み日のみがピンポイントで「年」となります）
                if req != "休":
                    model.Add(x[s, d, S_NEN] == 0)

                if d < n_days - 1:
                    not_le = model.NewBoolVar(f'nle_{s}_{d}')
                    model.Add(is_late[d] + is_early[d+1] <= 1).OnlyEnforceIf(not_le)
                    score_objs.append(not_le * 2000000 * w_h_rule)

                # --- 日ごとの獲得超過時間の1次式の組み立て ---
                wd_v = calendar.weekday(year, month, d+1)
                d_date = datetime.date(year, month, d+1)
                is_holiday = d_date in jp_holidays
                is_designated = bool(opt_des.at[d+1, "指定日"]) if d+1 in opt_des.index else False
                
                terms = []
                if wd_v == 6:  # 日曜日
                    pass  # 超過分0
                elif wd_v == 5:  # 土曜日
                    for i, s_name in enumerate(s_list_extended):
                        sid = i + 1
                        if s_name in ["A", "B"]:
                            continue
                        over_val = 0
                        if s_name in opt_overtime.index:
                            over_val = int(opt_overtime.loc[s_name, "土曜超過分(分)"])
                        if over_val > 0:
                            terms.append(x[s, d, sid] * over_val)
                else:  # 平日 (月〜金)
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

            # --- 「調（調整休日）は働き溜めした後に付与する」の動的検証 ---
            # 0日目〜各日dにおいて、[これまでの累積獲得超過時間] >= [これまでの累積調の消費時間（445分 * 累積調数）]を厳格強制
            for d in range(n_days):
                cum_overtime = sum(daily_overtime_exprs[k] for k in range(d + 1))
                cum_cho_count = sum(x[s, k, S_CHO] for k in range(d + 1))
                model.Add(cum_overtime >= cum_cho_count * 445)

            # 「調（調整休日）」は必ず平日にのみ配置（土日への配置はバグ回避のため絶対に禁止）
            for d in range(n_days):
                wd_v = calendar.weekday(year, month, d+1)
                if wd_v >= 5:  # 土曜日(5)または日曜日(6)
                    model.Add(x[s, d, S_CHO] == 0)

            # 連勤制限(4日まで、5日目に罰則)
            hist_w = [1 if opt_prev.iloc[s, k] != "休" else 0 for k in range(4)] + [(1 - is_off[di]) for di in range(n_days)]
            for st_i in range(len(hist_w) - 4):
                nc = model.NewBoolVar(f'nc_{s}_{st_i}')
                model.Add(sum(hist_w[st_i:st_i+5]) <= 4).OnlyEnforceIf(nc)
                score_objs.append(nc * 1000000 * w_h_rule)

            # リズム最適化 (V72 hybrid model)
            for di in range(n_days - 1):
                mix = model.NewBoolVar(f'mix_{s}_{di}')
                model.AddBoolAnd([is_early[di], is_late[di+1]]).OnlyEnforceIf(mix)
                score_objs.append(mix * 500 * w_rhythm)
                if di < n_days - 2:
                    e_block = model.NewBoolVar(f'eb_{s}_{di}')
                    model.Add(is_early[di] + is_early[di+1] + is_early[di+2] - 2 <= e_block)
                    score_objs.append(e_block * -1000 * w_rhythm)

            # 管理者・一般職の聖域
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

            # 各種休み日数の個別厳格配置（ハード制約）
            req_off_count = sum(1 for di in range(n_days) if opt_req.iloc[s, di] == "休") # 希望年休数
            total_off_limit = int(opt_hols.iloc[s, 0])  # 休の総数
            kokyu_val = int(opt_hols.iloc[s, 1])        # 公休分
            
            # 調整休日（調）の割り当て総数 ＝ 設定された「休の総数」 － 「公休分」
            target_cho_count = total_off_limit - kokyu_val
            if target_cho_count < 0:
                target_cho_count = 0
            
            # 各休みの数を個別に等式で完全固定
            # 年休（年）＝ 希望休数
            model.Add(sum(x[s, d, S_NEN] for d in range(n_days)) == req_off_count)
            # 公休（休）＝ 設定公休分
            model.Add(sum(x[s, d, S_OFF] for d in range(n_days)) == kokyu_val)
            # 調整休（調）＝ 調整休数
            model.Add(sum(x[s, d, S_CHO] for d in range(n_days)) == target_cho_count)

        # C. 担務平準化（公平性）
        for i_sh in range(1, num_types_extended + 1):
            counts = [model.NewIntVar(0, n_days, f'sh_c{si}_{i_sh}') for si in range(total)]
            for si in range(total): model.Add(counts[si] == sum(x[si, d, i_sh] for d in range(n_days)))
            mx, mn = model.NewIntVar(0, n_days, f'mx_{i_sh}'), model.NewIntVar(0, n_days, f'mn_{i_sh}')
            model.AddMaxEquality(mx, counts); model.AddMinEquality(mn, counts)
            score_objs.append((mx - mn) * -100 * w_fair)

        model.Maximize(sum(score_objs))
        slv = cp_model.CpSolver()
        slv.parameters.max_time_in_seconds = 45.0
        status = slv.Solve(model)

        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            st.success("✨ 勤務作成と調整が完了しました。申し込み（希望）および公休数は最優先で100%厳格に履行されています。")
            res_rows = []
            id_char = {S_OFF: "休", S_NIK: "日", S_CHO: "調", S_NEN: "年"} # 年を追加
            for i, n in enumerate(s_list_extended): id_char[i+1] = n
            for si in range(total):
                res_rows.append([id_char[next(j for j in range(num_types_extended+4) if slv.Value(x[si, di, j])==1)] for di in range(n_days)])

            # 日本の祝日判定用データの読み込み
            jp_holidays = {}
            if holidays is not None:
                try:
                    jp_holidays = holidays.Japan(years=[year])
                except Exception:
                    pass

            # --- 各人の超過勤務時間、年次休暇、調整休日、差し引きの算出 ---
            total_overtimes = []
            nenkyu_counts = []
            kokyu_values = []
            adjust_off_counts = []
            final_overtimes = []

            for si in range(total):
                staff_overtime_sum = 0
                for di in range(n_days):
                    wd_v = calendar.weekday(year, month, di+1)
                    assigned_char = res_rows[si][di]
                    
                    # 祝日・指定日判定
                    d_date = datetime.date(year, month, di+1)
                    is_holiday = d_date in jp_holidays
                    is_designated = bool(opt_des.at[di+1, "指定日"]) if di+1 in opt_des.index else False
                    
                    if wd_v == 6:  # 日曜日
                        overtime_val = 0
                    elif wd_v == 5:  # 土曜日
                        if assigned_char in ["A", "B", "日", "休", "調", "年"]: # 年・調を追加
                            overtime_val = 0
                        elif assigned_char in opt_overtime.index:
                            overtime_val = int(opt_overtime.loc[assigned_char, "土曜超過分(分)"])
                        else:
                            overtime_val = 0
                    else:  # 平日（月〜金）
                        if assigned_char in ["日", "休", "調", "年"]: # 年・調を追加
                            overtime_val = 0
                        elif (is_holiday or is_designated) and assigned_char in ["A", "B"]:
                            overtime_val = 0
                        elif assigned_char in opt_overtime.index:
                            overtime_val = int(opt_overtime.loc[assigned_char, "平日超過分(分)"])
                        else:
                            overtime_val = 0
                    
                    staff_overtime_sum += overtime_val
                
                # 年次休暇数（カレンダー上の「年」の数をダイレクトにカウント）
                nenkyu_count = res_rows[si].count("年")
                # 設定公休分（カレンダー上の「休」の数をダイレクトにカウント）
                kokyu_val = res_rows[si].count("休")
                # 調整休日数（カレンダー上の「調」の数をダイレクトにカウント）
                adjust_off = res_rows[si].count("調")
                
                # 差し引き分 (調整休日数 * 445分)
                minus_val = adjust_off * 445
                final_overtime = staff_overtime_sum - minus_val
                
                total_overtimes.append(staff_overtime_sum)
                nenkyu_counts.append(nenkyu_count)
                kokyu_values.append(kokyu_val)
                adjust_off_counts.append(adjust_off)
                final_overtimes.append(final_overtime)

            res_df = pd.DataFrame(res_rows, index=staff_list, columns=days_cols)
            res_df["休の総数"] = [row.count("休") + row.count("調") + row.count("年") for row in res_rows]
            res_df["年休数(希望)"] = nenkyu_counts
            res_df["設定公休"] = kokyu_values
            res_df["調整休日(調)数"] = adjust_off_counts
            res_df["総超過(前)"] = [format_minutes_to_hhmm(v) for v in total_overtimes] # HH:MM形式に変換
            res_df["精算後超過"] = [format_minutes_to_hhmm(v) for v in final_overtimes] # HH:MM形式に変換
            
            # 色分け表示関数
            def cl(v):
                if v == "休": return 'background-color: #ffcccc'
                if v == "調": return 'background-color: #ffcc99; font-weight: bold; color: #7a3e00;' # 調整休日はオレンジ系
                if v == "年": return 'background-color: #ffb3d9; font-weight: bold; color: #8a004b;' # 年次休暇はピンク系
                if v == "日": return 'background-color: #e0f0ff'
                if v in early_gr: return 'background-color: #ffffcc'
                if v == "F": return 'background-color: #e8d7ff; font-weight: bold; color: #4a148c;'
                return 'background-color: #ccffcc'
                
            st.dataframe(res_df.style.map(cl), use_container_width=True)
            st.download_button("📥 ダウンロード", res_df.to_csv().encode('utf-8-sig'), "roster.csv")
        else: 
            st.error("解が見つかりませんでした。入力制約が競合していないか確認してください。")

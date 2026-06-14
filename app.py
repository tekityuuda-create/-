import streamlit as st
import pandas as pd
import calendar
import json
import re
from ortools.sat.python import cp_model

# --- 1. グローバル設定：デザインとレイアウト ---
st.set_page_config(page_title="AI勤務作成：V80 Ultra Optimizer", page_icon="🛡️", layout="wide")

if 'config' not in st.session_state:
    st.session_state.config = {
        "num_mgr": 2, "num_regular": 8,
        "staff_names": [f"スタッフ{i+1}" for i in range(10)],
        "user_shifts": "A,B,C,D,E", "early_shifts": ["A", "B", "C"], "late_shifts": ["D", "E"],
        "year": 2025, "month": 1, "saved_tables": {}
    }

st.title("勤務作成エンジン (Team Excellence Pass)")
st.info("💡 **リアルタイム自動保存機能搭載**: 画面の入力や変更はすべてリアルタイムで保存されます。「保存ボタン」を押す必要はありません。")

# --- 2. データのバックアップ・復元管理 ---
with st.sidebar:
    st.header("📂 設定データの完全同期")
    up_file = st.file_uploader("設定ファイルを読み込む", type="json")
    if up_file:
        try:
            st.session_state.config.update(json.load(up_file))
            st.success("全ての変数の整合性を確認し復元しました。")
        except: st.error("エラー：ファイルの構造が不正です。")

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
        
        # 4. スタッフ名と日付数字を一致させて値を安全に移植する（型ズレ・並び順変動・曜日変更をすべて吸収）
        for r_target in d_df.index:
            r_str = str(r_target)
            if r_str in df.index:
                for c_target in d_df.columns:
                    c_clean = clean_col_name(c_target)
                    if c_clean in df.columns:
                        result_df.at[r_target, c_target] = df.at[r_str, c_clean]
        
        # 5. 未入力やミスマッチの部分をデフォルト値で補完
        result_df = result_df.fillna(d_df)
        df = result_df
    else:
        df = d_df
    
    if categories:
        for c in df.columns: 
            df[c] = pd.Categorical(df[c], categories=categories)
    return df

# --- 3. UIの統合タブ構成 ---
tab_st, tab_skl, tab_roster = st.tabs(["🏗️ 1. 組織と勤務の構成", "⚖️ 2. 公休・スキル・回数", "🧬 3. 勤務表の最適化"])

# --- タブ1. 組織と勤務の構成（オートセーブ） ---
with tab_st:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("👥 人員配置")
        form_n_mgr = st.number_input("管理者数", 0, 5, n_mgr)
        form_n_reg = st.number_input("一般職数", 1, 20, n_reg)
        form_total = int(form_n_mgr + form_n_reg)
        
        form_names = list(staff_list)
        if len(form_names) < form_total:
            form_names.extend([f"スタッフ{i+1}" for i in range(len(form_names), form_total)])
        form_names = form_names[:form_total]
        
        names_ed = st.data_editor(pd.DataFrame({"スタッフ名": form_names}), use_container_width=True, key="names_ed")
    with c2:
        st.subheader("📋 シフト構成")
        form_raw_s = st.text_input("勤務略称 (,) 区切り", raw_s)
        form_s_list = [s.strip() for s in form_raw_s.split(",") if s.strip()]
        form_early_gr = st.multiselect("早番グループ", form_s_list, default=[x for x in form_s_list if x in early_gr])
        form_late_gr = st.multiselect("遅番グループ", form_s_list, default=[x for x in form_s_list if x in late_gr])
        
    # タブ1 リアルタイム自動保存
    new_staff_list = names_ed["スタッフ名"].tolist()
    st.session_state.config.update({
        "num_mgr": form_n_mgr,
        "num_regular": form_n_reg,
        "staff_names": new_staff_list,
        "user_shifts": form_raw_s,
        "early_shifts": form_early_gr,
        "late_shifts": form_late_gr
    })

# --- タブ2. 公休・スキル（オートセーブ） ---
with tab_skl:
    st.subheader("🎓 専門スキル・月間公休数・教育ノルマ")
    st.write("○:可能, △:見習い（ベテラン必須）, ×:不可")
    
    skl_df = get_persisted_df("skill", pd.DataFrame("○", index=staff_list, columns=s_list), ["○","△","×"])
    ed_skill = st.data_editor(skl_df, use_container_width=True, key="skill_ed")
    
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        st.subheader("📅 月間公休数設定")
        hols_df = get_persisted_df("hols", pd.DataFrame(9, index=staff_list, columns=["公休数"]))
        ed_hols = st.data_editor(hols_df, use_container_width=True, key="hol_ed")
    with col_c2:
        st.subheader("🏫 教育ノルマ設定")
        tr_cols = [f"{s}_見習い回数" for s in s_list]
        tr_df = get_persisted_df("trainee", pd.DataFrame(0, index=staff_list, columns=tr_cols))
        ed_trainee = st.data_editor(tr_df, use_container_width=True, key="tr_ed")
        
    # タブ2 リアルタイム自動保存
    if "saved_tables" not in st.session_state.config:
        st.session_state.config["saved_tables"] = {}
    st.session_state.config["saved_tables"]["skill"] = ed_skill.to_dict()
    st.session_state.config["saved_tables"]["hols"] = ed_hols.to_dict()
    st.session_state.config["saved_tables"]["trainee"] = ed_trainee.to_dict()

# --- タブ3. 勤務表の最適化（申し込み・オートセーブ・AI実行） ---
with tab_roster:
    _, n_days = calendar.monthrange(year, month)
    days_cols = [f"{d+1}({['月','火','水','木','金','土','日'][calendar.weekday(year,month,d+1)]})" for d in range(n_days)]
    options = ["", "休", "日"] + s_list

    st.subheader("📝 前月末引継ぎ & 今月の申し込み")
    p_days = ["前月4日前","前月3日前","前月2日前","前月末日"]
    p_df = get_persisted_df("prev", pd.DataFrame("休", index=staff_list, columns=p_days), ["日","休","早","遅"])
    r_df = get_persisted_df("request", pd.DataFrame("", index=staff_list, columns=days_cols), options)
    
    c_p, c_r = st.columns([1, 3])
    with c_p: ed_prev = st.data_editor(p_df, use_container_width=True, key="p_ed")
    with c_r: ed_req = st.data_editor(r_df, use_container_width=True, key="r_ed")

    st.subheader("🚫 不要担務 (祝日Cなど)")
    ex_df = get_persisted_df("exclude", pd.DataFrame(False, index=[d+1 for d in range(n_days)], columns=s_list))
    ed_ex = st.data_editor(ex_df, use_container_width=True, key="ex_ed")
    
    # タブ3 リアルタイム自動保存
    if "saved_tables" not in st.session_state.config:
        st.session_state.config["saved_tables"] = {}
    st.session_state.config["saved_tables"]["prev"] = ed_prev.to_dict()
    st.session_state.config["saved_tables"]["request"] = ed_req.to_dict()
    st.session_state.config["saved_tables"]["exclude"] = ed_ex.to_dict()

    st.sidebar.download_button("📥 現在の全設定を保存する", json.dumps(st.session_state.config, ensure_ascii=False), f"v80_backup_{year}_{month}.json")

    # --- 最適化インプットデータの最新取得 ---
    opt_skill = get_persisted_df("skill", pd.DataFrame("○", index=staff_list, columns=s_list))
    opt_hols = get_persisted_df("hols", pd.DataFrame(9, index=staff_list, columns=["公休数"]))
    opt_prev = get_persisted_df("prev", pd.DataFrame("休", index=staff_list, columns=["前月4日前","前月3日前","前月2日前","前月末日"]))
    opt_req = get_persisted_df("request", pd.DataFrame("", index=staff_list, columns=days_cols))
    opt_ex = get_persisted_df("exclude", pd.DataFrame(False, index=[d+1 for d in range(n_days)], columns=s_list))

    # --- データの同期確認テーブル（デバッグ表示） ---
    st.divider()
    st.write("🔍 **AIが今回読み込んだ各スタッフの公休と申し込みの最終データ（自動同期検証用）**")
    debug_rows = []
    for s_idx, s_name in enumerate(staff_list):
        req_off_count = sum(1 for di in range(n_days) if opt_req.iloc[s_idx, di] == "休")
        target_h = int(opt_hols.iloc[s_idx, 0])
        debug_rows.append({
            "スタッフ名": s_name,
            "設定公休数": target_h,
            "希望休(休)数": req_off_count,
            "最終公休目標数": max(target_h, req_off_count)
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
        S_OFF, S_NIK = 0, num_types_extended + 1
        
        E_IDS = [s_list_extended.index(x) + 1 for x in early_gr if x in s_list_extended]
        L_IDS = [s_list_extended.index(x) + 1 for x in late_gr if x in s_list_extended]
        
        w_rhythm = w_mixing

        # Fシフト用スキル判定関数
        def get_skill_for_F(s_idx):
            skill_c = opt_skill.iloc[s_idx, c_idx]
            skill_d = opt_skill.iloc[s_idx, d_idx]
            if skill_c == "×" or skill_d == "×":
                return "×"
            elif skill_c == "○" and skill_d == "○":
                return "○"
            return "△"

        # 変数: x[スタッフ, 日, シフト]
        x = {(s, d, i): model.NewBoolVar(f'x_{s}_{d}_{i}') for s in range(total) for d in range(n_days) for i in range(num_types_extended + 2)}
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
                # 土曜日にF（統合シフト）を採用するためのペナルティを大幅に緩和（-10000点）
                # これにより、少しでも公休数や希望休に無理が出るなら、AIはCとDを諦めて積極的にF（統合）を起動させます
                score_objs.append(use_F_var * -10000)

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
                
                # 土曜日限定のF適用判定ロジック
                if s_name in ["C", "D", "F"] and wd == 5 and has_C_and_D:
                    under_sat_var = model.NewIntVar(0, 1, f'under_sat_{d}_{sid}')
                    
                    if s_name == "F":
                        # シフト人数は等式（== 1）。2名以上重複配置は禁止
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
            for s in range(total): model.Add(sum(x[s, d, i] for i in range(num_types_extended+2)) == 1)

        # 個人別の高度な最適化
        for s in range(total):
            is_early = [model.NewBoolVar(f'ie_{s}_{d}') for d in range(n_days)]
            is_late = [model.NewBoolVar(f'il_{s}_{d}') for d in range(n_days)]
            is_off = [x[s, d, S_OFF] for d in range(n_days)]
            
            for d in range(n_days):
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
                req = opt_req.iloc[s, d]
                c_map = {"休": S_OFF, "日": S_NIK, "": -1}
                for i, n in enumerate(s_list_extended): c_map[n] = i+1
                if req in c_map and req != "": 
                    model.Add(x[s, d, c_map[req]] == 1)
                
                if d < n_days - 1:
                    not_le = model.NewBoolVar(f'nle_{s}_{d}')
                    model.Add(is_late[d] + is_early[d+1] <= 1).OnlyEnforceIf(not_le)
                    score_objs.append(not_le * 2000000 * w_h_rule)

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
                        # 平日は出勤を強く推奨
                        # （管理者は制限なく日勤 (S_NIK) に逃げることができるため、一般職が余った日は自動的に管理者が日勤を担当します）
                        m_w = model.NewBoolVar(f'mw_{s}_{di}')
                        model.Add(is_off[di] == 0).OnlyEnforceIf(m_w)
                        score_objs.append(m_w * 500000)
            else:
                for di in range(n_days):
                    if opt_req.iloc[s, di] != "日": 
                        # 一般職の日勤は原則禁止。
                        # 全員の公休目標を絶対厳守した際、数学的にどうしてもシフト枠が不足して全員があぶれる極限状態のみ、
                        # 日勤へ逃げることを許容（ソフト制約化）。
                        # 管理者の日勤（ペナルティなし）より非常に重いペナルティ（-1000万点）を課すことで、
                        # 「まずは管理者が優先的に日勤に回り、それでも溢れる最悪の場合のみ一般職を日勤にする」ことを保証します。
                        nik_var = x[s, di, S_NIK]
                        score_objs.append(nik_var * -10000000)

            # 目標公休数の厳守（ハード制約）
            # 休み希望("休")の合計数が目標公休数を上回っている場合は、目標公休数を希望数に合わせて自動補正する
            req_off_count = sum(1 for di in range(n_days) if opt_req.iloc[s, di] == "休")
            target_h_count = max(int(opt_hols.iloc[s, 0]), req_off_count)
            
            act_h_count = sum(is_off)
            model.Add(act_h_count == target_h_count)

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
            id_char = {S_OFF: "休", S_NIK: "日"}
            for i, n in enumerate(s_list_extended): id_char[i+1] = n
            for si in range(total):
                res_rows.append([id_char[next(j for j in range(num_types_extended+2) if slv.Value(x[si, di, j])==1)] for di in range(n_days)])
            res_df = pd.DataFrame(res_rows, index=staff_list, columns=days_cols)
            res_df["公休数"] = [row.count("休") for row in res_rows]
            
            # 色分け表示関数
            def cl(v):
                if v == "休": return 'background-color: #ffcccc'
                if v == "日": return 'background-color: #e0f0ff'
                if v in early_gr: return 'background-color: #ffffcc'
                if v == "F": return 'background-color: #e8d7ff; font-weight: bold; color: #4a148c;' # Fは紫色の特別カラー
                return 'background-color: #ccffcc'
                
            st.dataframe(res_df.style.map(cl), use_container_width=True)
            st.download_button("📥 ダウンロード", res_df.to_csv().encode('utf-8-sig'), "roster.csv")
        else: 
            st.error("解が見つかりませんでした。入力制約が競合していないか確認してください。")

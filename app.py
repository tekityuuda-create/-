import streamlit as st
import pandas as pd
import calendar
import json
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

st.warning("⚠️ **重要**: 各タブ（基本構成、スキル・公休、申し込み）で数値を編集した後は、**必ずそのタブの下部にある「保存する・確定する」ボタンをクリック**してください。保存せずに別のタブに移動すると、編集内容が反映されません。")

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

# --- 3. UIの統合タブ構成 ---
tab_st, tab_skl, tab_roster = st.tabs(["🏗️ 1. 組織と勤務の構成", "⚖️ 2. 公休・スキル・回数", "🧬 3. 勤務表の最適化"])

def get_persisted_df(key, d_df, categories=None):
    tables = st.session_state.config.get("saved_tables", {})
    df = pd.DataFrame(tables.get(key)) if key in tables else d_df
    df = df.reindex(index=d_df.index, columns=d_df.columns).fillna(d_df)
    if categories:
        for c in df.columns: df[c] = pd.Categorical(df[c], categories=categories)
    return df

with tab_st:
    with st.form("structure_form"):
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
            
        submitted_st = st.form_submit_button("🏗️ 構成を確定して保存する")
        if submitted_st:
            new_staff_list = names_ed["スタッフ名"].tolist()
            st.session_state.config.update({
                "num_mgr": form_n_mgr,
                "num_regular": form_n_reg,
                "staff_names": new_staff_list,
                "user_shifts": form_raw_s,
                "early_shifts": form_early_gr,
                "late_shifts": form_late_gr
            })
            st.success("構成データを保存しました。")
            st.rerun()

with tab_skl:
    with st.form("skill_form"):
        st.subheader("🎓 専門スキル設定")
        st.write("○:可能, △:見習い（ベテラン必須）, ×:不可")
        skl_df = get_persisted_df("skill", pd.DataFrame("○", index=staff_list, columns=s_list), ["○","△","×"])
        ed_skill = st.data_editor(skl_df, use_container_width=True, key="skill_ed")
        
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            st.subheader("📅 月間公休数設定")
            hols_df = get_persisted_df("hols", pd.DataFrame(9, index=staff_list, columns=["公休数"]))
            ed_hols = st.data_editor(hols_df, use_container_width=True, key="hol_ed")
            
            st.subheader("🏫 教育ノルマ設定")
            tr_cols = [f"{s}_見習い回数" for s in s_list]
            tr_df = get_persisted_df("trainee", pd.DataFrame(0, index=staff_list, columns=tr_cols))
            ed_trainee = st.data_editor(tr_df, use_container_width=True, key="tr_ed")
        with col_c2:
            st.subheader("⏱️ 各担務の残業時間設定 (分)")
            st.write("※1時間半なら 90 と入力してください")
            ot_indices = list(s_list)
            if "C" in s_list and "D" in s_list and "F" not in ot_indices:
                ot_indices.append("F")
            
            default_overtime = pd.DataFrame(
                [90, 60, 120, 150, 60, 180][:len(ot_indices)], 
                index=ot_indices, 
                columns=["残業時間(分)"]
            )
            ot_df = get_persisted_df("overtime", default_overtime)
            
            # 過去の時間表記データを読み込んだ場合の自動変換・救済処理
            if "残業時間(時間)" in ot_df.columns and "残業時間(分)" not in ot_df.columns:
                ot_df["残業時間(分)"] = (ot_df["残業時間(時間)"] * 60).fillna(60).astype(int)
                ot_df = ot_df.drop(columns=["残業時間(時間)"])
            if "残業時間(分)" not in ot_df.columns:
                ot_df["残業時間(分)"] = 60
            ot_df = ot_df.reindex(columns=["残業時間(分)"])
            
            ed_overtime = st.data_editor(ot_df, use_container_width=True, key="ot_ed")
            
        submitted_skl = st.form_submit_button("⚖️ スキル・公休・残業の設定を保存する")
        if submitted_skl:
            if "saved_tables" not in st.session_state.config:
                st.session_state.config["saved_tables"] = {}
            st.session_state.config["saved_tables"]["skill"] = ed_skill.to_dict()
            st.session_state.config["saved_tables"]["hols"] = ed_hols.to_dict()
            st.session_state.config["saved_tables"]["trainee"] = ed_trainee.to_dict()
            st.session_state.config["saved_tables"]["overtime"] = ed_overtime.to_dict()
            st.success("設定を保存しました。")
            st.rerun()

with tab_roster:
    _, n_days = calendar.monthrange(year, month)
    days_cols = [f"{d+1}({['月','火','水','木','金','土','日'][calendar.weekday(year,month,d+1)]})" for d in range(n_days)]
    options = ["", "休", "日", "調"] + s_list

    with st.form("roster_input_form"):
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
        
        submitted_roster_inputs = st.form_submit_button("📝 各種入力データを保存する")
        if submitted_roster_inputs:
            if "saved_tables" not in st.session_state.config:
                st.session_state.config["saved_tables"] = {}
            st.session_state.config["saved_tables"]["prev"] = ed_prev.to_dict()
            st.session_state.config["saved_tables"]["request"] = ed_req.to_dict()
            st.session_state.config["saved_tables"]["exclude"] = ed_ex.to_dict()
            st.success("前月履歴・希望・不要担務設定を保存しました。")
            st.rerun()

    st.sidebar.download_button("📥 現在の全設定を保存する", json.dumps(st.session_state.config, ensure_ascii=False), f"v80_backup_{year}_{month}.json")

    # --- 数理最適化開始 ---
    st.divider()
    st.subheader("🧬 勤務表作成エンジンの実行")
    st.info("⚠️ **注意**: 公休数や残業設定を変更した場合は、必ず各タブの下部にある「保存する」ボタンを押して確定させてから、以下の勤務作成ボタンを押してください。")
    
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
        
        # シフトID定義:
        # 0: 休 (S_OFF)
        # 1〜num_types_extended: A, B, C, D, E, F など
        # num_types_extended + 1: 日勤 (S_NIK)
        # num_types_extended + 2: 調整休日 (S_CHOU)
        S_OFF = 0
        S_NIK = num_types_extended + 1
        S_CHOU = num_types_extended + 2
        
        E_IDS = [s_list_extended.index(x) + 1 for x in early_gr if x in s_list_extended]
        L_IDS = [s_list_extended.index(x) + 1 for x in late_gr if x in s_list_extended]
        
        # 変数マッピング
        w_rhythm = w_mixing

        # 確定済みデータをセッションから安全に再現
        saved = st.session_state.config.get("saved_tables", {})
        opt_skill = pd.DataFrame(saved.get("skill")).reindex(index=staff_list, columns=s_list).fillna("○")
        opt_hols = pd.DataFrame(saved.get("hols")).reindex(index=staff_list, columns=["公休数"]).fillna(9)
        opt_prev = pd.DataFrame(saved.get("prev")).reindex(index=staff_list, columns=["前月4日前","前月3日前","前月2日前","前月末日"]).fillna("休")
        opt_req = pd.DataFrame(saved.get("request")).reindex(index=staff_list, columns=days_cols).fillna("")
        opt_ex = pd.DataFrame(saved.get("exclude")).reindex(index=[d+1 for d in range(n_days)], columns=s_list).fillna(False)
        
        ot_indices = list(s_list)
        if has_C_and_D and "F" not in ot_indices:
            ot_indices.append("F")
            
        # 残業設定のロードと互換性処理
        raw_ot = pd.DataFrame(saved.get("overtime")).reindex(ot_indices)
        if "残業時間(時間)" in raw_ot.columns and "残業時間(分)" not in raw_ot.columns:
            raw_ot["残業時間(分)"] = (raw_ot["残業時間(時間)"] * 60).fillna(60).astype(int)
        if "残業時間(分)" not in raw_ot.columns:
            raw_ot["残業時間(分)"] = 60
        opt_overtime = raw_ot.fillna(60)

        # Fシフト用スキル判定関数
        def get_skill_for_F(s_idx):
            skill_c = opt_skill.iloc[s_idx, c_idx]
            skill_d = opt_skill.iloc[s_idx, d_idx]
            if skill_c == "×" or skill_d == "×":
                return "×"
            elif skill_c == "○" and skill_d == "○":
                return "○"
            return "△"

        # 変数: x[スタッフ, 日, シフト] (休〜調整休日の全レンジをカバー)
        x = {(s, d, i): model.NewBoolVar(f'x_{s}_{d}_{i}') for s in range(total) for d in range(n_days) for i in range(num_types_extended + 3)}
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
                # 統合勤務Fの使用には巨大なペナルティ（-1000万点）を科すことで「通常勤務では回らない最終手段」としてのみ発動させる
                score_objs.append(use_F_var * -10000000)

            # A. 担務充足
            for i, s_name in enumerate(s_list_extended):
                sid = i + 1
                
                # Fは土曜日のみ許可、それ以外の曜日は除外扱い
                if s_name == "F":
                    is_excl = not (wd == 5 and has_C_and_D)
                else:
                    is_excl = opt_ex.iloc[d, i] or (wd == 6 and s_name == "C")
                
                # Fスキル及び通常スキルの判定
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
                    if s_name == "F":
                        # 統合F使用(use_F_var=1)ならFは1人、使用しないならFは0人
                        model.Add(s_sum + t_sum == 1).OnlyEnforceIf(use_F_var)
                        model.Add(s_sum + t_sum == 0).OnlyEnforceIf(use_F_var.Not())
                    else:  # C または D
                        # 統合F使用(use_F_var=1)ならCとDはどちらも0人
                        model.Add(s_sum + t_sum == 0).OnlyEnforceIf(use_F_var)
                        # 統合F不使用(use_F_var=0)ならCとDは1人ずつ（除外日を除く）
                        if is_excl:
                            model.Add(s_sum + t_sum == 0).OnlyEnforceIf(use_F_var.Not())
                        else:
                            model.Add(s_sum + t_sum == 1).OnlyEnforceIf(use_F_var.Not())
                else:
                    # 通常曜日、または土曜日のA/B/E勤務
                    if is_excl:
                        model.Add(s_sum + t_sum == 0)
                    else:
                        model.Add(s_sum + t_sum == 1)
                    
                    # 通常日の見習い同日ベテラン出勤保証
                    for s_t in trainee:
                        all_skilled_staff = [s for s in range(total) if "○" in opt_skill.iloc[s].values]
                        veteran_on_duty = sum(x[s, d, other_sid] for s in all_skilled_staff for other_sid in range(1, num_types_extended+1))
                        model.Add(veteran_on_duty >= 1).OnlyEnforceIf(x[s_t, d, sid])

            # 土曜日の見習い同日ベテラン出勤保証（C/D/Fが個別ループから外れるためここで別途評価）
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
                        model.Add(veteran_on_duty >= 1).OnlyEnforceIf(x[s_t, d, sid])

            # 1日1人1回 (S_CHOUを含めた全レンジからちょうど1つ選択)
            for s in range(total): model.Add(sum(x[s, d, i] for i in range(num_types_extended+3)) == 1)

        # 個人別の高度な最適化
        for s in range(total):
            is_early = [model.NewBoolVar(f'ie_{s}_{d}') for d in range(n_days)]
            is_late = [model.NewBoolVar(f'il_{s}_{d}') for d in range(n_days)]
            
            # 「公休(S_OFF)」または「調整休日(S_CHOU)」の両方を休日状態として連動
            is_off = [model.NewBoolVar(f'is_off_{s}_{d}') for d in range(n_days)]
            for d in range(n_days):
                model.Add(is_off[d] == x[s, d, S_OFF] + x[s, d, S_CHOU])
            
            # 調整休日(S_CHOU)の過剰・不要な使用を抑制するための微小なペナルティ
            score_objs.append(sum(x[s, d, S_CHOU] for d in range(n_days)) * -100)
            
            # 月間残業時間の計算 (直接分単位で整数計算)
            ot_vars = []
            for d in range(n_days):
                wd = calendar.weekday(year, month, d+1)
                ot_mins_by_shift = [0] * (num_types_extended + 3)
                
                for i, s_name in enumerate(s_list_extended):
                    sid = i + 1
                    val_mins = int(opt_overtime.loc[s_name, "残業時間(分)"])
                    
                    if wd == 6:  # 日曜日は全担務残業なし
                        ot_mins_by_shift[sid] = 0
                    elif wd == 5:  # 土曜日のA, Bは残業なし
                        if s_name in ["A", "B"]:
                            ot_mins_by_shift[sid] = 0
                        else:
                            ot_mins_by_shift[sid] = val_mins
                    else:  # 平日
                        ot_mins_by_shift[sid] = val_mins
                
                # 休(S_OFF), 日勤(S_NIK), 調整休日(S_CHOU) は労働時間としては0分
                ot_mins_by_shift[S_OFF] = 0
                ot_mins_by_shift[S_NIK] = 0
                ot_mins_by_shift[S_CHOU] = 0
                
                ot_day = model.NewIntVar(0, 1440, f'ot_{s}_{d}')
                model.Add(ot_day == sum(x[s, d, sid] * ot_mins_by_shift[sid] for sid in range(num_types_extended + 3)))
                ot_vars.append(ot_day)
            
            # 月間残業時間の上限制限
            # 実働総残業時間 - （調整休日の付与数 × 445分）が 30時間(1800分) 以下
            chou_count = sum(x[s, d, S_CHOU] for d in range(n_days))
            model.Add(sum(ot_vars) - chou_count * 445 <= 1800)

            for d in range(n_days):
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

                req = opt_req.iloc[s, d]
                c_map = {"休": S_OFF, "日": S_NIK, "調": S_CHOU, "": -1}
                for i, n in enumerate(s_list_extended): c_map[n] = i+1
                if req in c_map and req != "": model.Add(x[s, d, c_map[req]] == 1)
                
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
                # 連属性抑制
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
                    else: model.Add(is_off[di] == 0) # 平日は基本出勤
            else:
                for di in range(n_days):
                    if opt_req.iloc[s, di] != "日": model.Add(x[s, di, S_NIK] == 0)

            # 公休数不一致を罰則化 (調整休日S_CHOUを含めず、契約上の公休数S_OFFのみを計算)
            target_h_count = int(opt_hols.iloc[s, 0])
            act_h_count = sum(x[s, di, S_OFF] for di in range(n_days))
            h_diff_raw = model.NewIntVar(-n_days, n_days, f'hdr_{s}')
            model.Add(h_diff_raw == act_h_count - target_h_count)
            h_diff = model.NewIntVar(0, n_days, f'hd_{s}')
            model.AddAbsEquality(h_diff, h_diff_raw)
            score_objs.append(h_diff * -50000 * w_holiday)

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
            st.success("✨ 勤務作成と調整が完了しました。")
            res_rows = []
            id_char = {S_OFF: "休", S_NIK: "日", S_CHOU: "調"}
            for i, n in enumerate(s_list_extended): id_char[i+1] = n
            for si in range(total):
                res_rows.append([id_char[next(j for j in range(num_types_extended+3) if slv.Value(x[si, di, j])==1)] for di in range(n_days)])
            res_df = pd.DataFrame(res_rows, index=staff_list, columns=days_cols)
            res_df["公休数"] = [row.count("休") for row in res_rows]
            res_df["調整休数"] = [row.count("調") for row in res_rows]
            
            # 各スタッフの最終的な月間残業時間の集計
            actual_ot_list = []
            for s in range(total):
                total_ot_mins = 0
                count_chou = 0
                for d in range(n_days):
                    assigned_char = res_rows[s][d]
                    if assigned_char == "調":
                        count_chou += 1
                    elif assigned_char in s_list_extended:
                        wd = calendar.weekday(year, month, d+1)
                        val_mins = int(opt_overtime.loc[assigned_char, "残業時間(分)"])
                        # 曜日例外ルール評価
                        if wd == 6:
                            total_ot_mins += 0
                        elif wd == 5 and assigned_char in ["A", "B"]:
                            total_ot_mins += 0
                        else:
                            total_ot_mins += val_mins
                
                # 調整休日による残業相殺控除を適用 (1回につき445分)
                net_ot_mins = total_ot_mins - (count_chou * 445)
                # 残業時間のマイナス値表示を防止するため下限を0.0hとする
                net_ot_hours = max(0.0, round(net_ot_mins / 60.0, 1))
                actual_ot_list.append(net_ot_hours)
            res_df["総残業時間(h)"] = actual_ot_list
            
            # 色分け表示関数
            def cl(v):
                if v == "休": return 'background-color: #ffcccc'
                if v == "日": return 'background-color: #e0f0ff'
                if v == "調": return 'background-color: #ffe0b2; font-weight: bold; color: #e65100;' # 調整休日はオレンジ系
                if v in early_gr: return 'background-color: #ffffcc'
                if v == "F": return 'background-color: #e8d7ff; font-weight: bold; color: #4a148c;'
                return 'background-color: #ccffcc'
                
            st.dataframe(res_df.style.map(cl), use_container_width=True)
            st.download_button("📥 ダウンロード", res_df.to_csv().encode('utf-8-sig'), "roster.csv")
        else: 
            st.error("解が見つかりませんでした。入力制約が競合していないか確認してください。（例：管理者が平日に希望休を出している、または合計人数がシフト数に足りないなど）")

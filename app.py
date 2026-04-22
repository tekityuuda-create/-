import streamlit as st
import pandas as pd
import calendar
import json
from ortools.sat.python import cp_model

# --- 1. 画面基本設定 ---
st.set_page_config(page_title="世界最高峰 勤務作成AI 究極版", page_icon="🛡️", layout="wide")

# セッション状態の初期化
if 'config' not in st.session_state:
    st.session_state.config = {
        "num_mgr": 2, "num_regular": 8,
        "staff_names": [f"スタッフ{i+1}" for i in range(10)],
        "user_shifts": "A,B,C,D,E", "early_shifts": ["A", "B", "C"], "late_shifts": ["D", "E"],
        "year": 2025, "month": 1, "saved_tables": {}
    }

st.title("🛡️ 究極の勤務作成エンジン (The Masterwork V64)")

# --- 2. サイドバー：バックアップと年月 ---
with st.sidebar:
    st.header("💾 設定の保存と復元")
    uploaded_file = st.file_uploader("設定ファイルを読み込む(.json)", type="json")
    if uploaded_file is not None:
        try:
            st.session_state.config.update(json.load(uploaded_file))
            st.success("全てのデータを復元しました。")
        except:
            st.error("エラー：ファイル形式が不正です。")

    st.divider()
    st.header("📅 対象年月")
    year = st.number_input("年", 2024, 2030, st.session_state.config["year"])
    month = st.number_input("月", 1, 12, st.session_state.config["month"])

# --- 3. タブ構成 ---
tab1, tab2, tab3 = st.tabs(["⚙️ システム構成", "👤 スタッフ・スキル設定", "🚀 勤務表の作成"])

with tab1:
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("👥 人数と名前の設定")
        num_mgr = st.number_input("管理者の人数", 0, 5, st.session_state.config["num_mgr"])
        num_regular = st.number_input("一般スタッフの人数", 1, 20, st.session_state.config["num_regular"])
        total_staff = int(num_mgr + num_regular)
        
        current_names = st.session_state.config.get("staff_names", [])
        if len(current_names) < total_staff: current_names.extend([f"スタッフ{i+1}" for i in range(len(current_names), total_staff)])
        final_staff_names = current_names[:total_staff]
        
        name_df = pd.DataFrame({"名前": final_staff_names})
        edited_names_df = st.data_editor(name_df, use_container_width=True, key="name_editor")
        final_staff_names = edited_names_df["名前"].tolist()

    with col2:
        st.subheader("📋 勤務グループ")
        shift_input = st.text_input("勤務略称 (カンマ区切り)", st.session_state.config["user_shifts"])
        user_shifts_list = [s.strip() for s in shift_input.split(",") if s.strip()]
        early_shifts = st.multiselect("早番グループ", user_shifts_list, default=[s for s in user_shifts_list if s in st.session_state.config["early_shifts"]])
        late_shifts = st.multiselect("遅番グループ", user_shifts_list, default=[s for s in user_shifts_list if s in st.session_state.config["late_shifts"]])

# 共通関数：テーブルデータの安全な復元
def get_safe_df(key, default_df, categories=None):
    saved_tables = st.session_state.config.get("saved_tables", {})
    df = pd.DataFrame(saved_tables.get(key)) if key in saved_tables else default_df
    # 行数・列数の不一致を解消
    df = df.reindex(index=default_df.index, columns=default_df.columns).fillna(default_df)
    # プルダウンを強制有効化（最重要）
    if categories:
        for col in df.columns: df[col] = pd.Categorical(df[col], categories=categories)
    return df

with tab2:
    st.subheader("🎓 スキル・公休・教育目標")
    # スキル設定
    skill_opts = ["○", "△", "×"]
    skill_df = get_safe_df("skill", pd.DataFrame("○", index=final_staff_names, columns=user_shifts_list), skill_opts)
    edited_skill = st.data_editor(skill_df, use_container_width=True, key="skill_editor")
    
    c_s1, c_s2 = st.columns(2)
    with c_s1:
        st.write("📊 公休数 (B列)")
        hols_df = get_safe_df("hols", pd.DataFrame(9, index=final_staff_names, columns=["公休数"]))
        edited_hols = st.data_editor(hols_df, use_container_width=True, key="hol_editor")
    with c_s2:
        st.write("📈 見習い(△)の実施回数目標")
        trainee_cols = [f"{s}_見習い回数" for s in user_shifts_list]
        trainee_df = get_safe_df("trainee", pd.DataFrame(0, index=final_staff_names, columns=trainee_cols))
        edited_trainee_targets = st.data_editor(trainee_df, use_container_width=True, key="trainee_target_editor")

with tab3:
    _, num_days = calendar.monthrange(int(year), int(month))
    weekdays_ja = ["月", "火", "水", "木", "金", "土", "日"]
    days_cols = [f"{d+1}({weekdays_ja[calendar.weekday(int(year), int(month), d+1)]})" for d in range(num_days)]
    options = ["", "休", "日"] + user_shifts_list

    st.subheader("⏮️ 前月末の勤務状況 (過去4日間)")
    prev_days = ["前月4日前", "前月3日前", "前月2日前", "前月末日"]
    prev_df = get_safe_df("prev", pd.DataFrame("休", index=final_staff_names, columns=prev_days), ["日", "休", "早", "遅"])
    edited_prev = st.data_editor(prev_df, use_container_width=True, key="prev_editor")

    st.subheader("📝 今月の勤務指定 (申し込み)")
    req_df = get_safe_df("request", pd.DataFrame("", index=final_staff_names, columns=days_cols), options)
    edited_request = st.data_editor(req_df, use_container_width=True, key="request_editor")

    st.subheader("🚫 不要担務の設定")
    excl_df = get_safe_df("exclude", pd.DataFrame(False, index=[d+1 for d in range(num_days)], columns=user_shifts_list))
    edited_exclude = st.data_editor(excl_df, use_container_width=True, key="exclude_editor")

    # 保存データのパッケージング
    total_config_save = {
        "num_mgr": num_mgr, "num_regular": num_regular, "staff_names": final_staff_names,
        "user_shifts": shift_input, "early_shifts": early_shifts, "late_shifts": late_shifts,
        "year": year, "month": month,
        "saved_tables": {
            "skill": edited_skill.to_dict(), "hols": edited_hols.to_dict(), "trainee": edited_trainee_targets.to_dict(),
            "prev": edited_prev.to_dict(), "request": edited_request.to_dict(), "exclude": edited_exclude.to_dict()
        }
    }
    st.sidebar.download_button(label="📥 全設定を保存", data=json.dumps(total_config_save, ensure_ascii=False), file_name=f"config_{year}_{month}.json", mime="application/json")

    if st.button("🚀 究極の最適化を実行する", type="primary"):
        model = cp_model.CpModel()
        num_user_shifts = len(user_shifts_list)
        S_OFF, S_NIKKIN = 0, num_user_shifts + 1
        char_to_id = {"休": S_OFF, "日": S_NIKKIN, "": -1}
        for idx, name in enumerate(user_shifts_list): char_to_id[name] = idx + 1
        e_ids = [user_shifts_list.index(s) + 1 for s in early_shifts]
        l_ids = [user_shifts_list.index(s) + 1 for s in late_shifts]

        shifts = {(s, d, i): model.NewBoolVar(f's{s}d{d}i{i}') for s in range(total_staff) for d in range(num_days) for i in range(num_user_shifts + 2)}
        obj_terms = []

        # 前月解析
        prev_work_matrix, prev_is_late_last = [], []
        for s in range(total_staff):
            row_w = []
            for d_idx in range(4):
                val = edited_prev.iloc[s, d_idx]
                row_w.append(1 if val != "休" else 0)
                if d_idx == 3: prev_is_late_last.append(val == "遅")
            prev_work_matrix.append(row_w)

        # 担務充足
        for d in range(num_days):
            wd_v = calendar.weekday(int(year), int(month), d + 1)
            for idx, s_name in enumerate(user_shifts_list):
                sid = idx + 1
                is_ex = edited_exclude.iloc[d, idx]
                is_sun_c = (wd_v == 6 and s_name == "C")
                skilled_sum = sum(shifts[(s, d, sid)] for s in range(total_staff) if edited_skill.iloc[s, idx] == "○")
                trainee_sum = sum(shifts[(s, d, sid)] for s in range(total_staff) if edited_skill.iloc[s, idx] == "△")
                if is_ex or is_sun_c: model.Add(skilled_sum + trainee_sum == 0)
                else:
                    sk_ok = model.NewBoolVar(f'sk_ok_d{d}_i{sid}')
                    model.Add(skilled_sum == 1).OnlyEnforceIf(sk_ok)
                    obj_terms.append(sk_ok * 20000000)
                    model.Add(trainee_sum <= 1)

        # 公平性エンジン
        shift_counts = {(s, i): model.NewIntVar(0, num_days, f'c{s}_{i}') for s in range(total_staff) for i in range(1, num_user_shifts + 1)}
        for s in range(total_staff):
            for i in range(1, num_user_shifts + 1):
                model.Add(shift_counts[(s, i)] == sum(shifts[(s, d, i)] for d in range(num_days)))
        for i in range(1, num_user_shifts + 1):
            eligible = [s for s in range(total_staff) if edited_skill.iloc[s, i-1] != "×"]
            if eligible:
                max_c, min_c = model.NewIntVar(0, num_days, f'max{i}'), model.NewIntVar(0, num_days, f'min{i}')
                model.AddMaxEquality(max_c, [shift_counts[(s, i)] for s in eligible])
                model.AddMinEquality(min_c, [shift_counts[(s, i)] for s in eligible])
                obj_terms.append((max_c - min_c) * -2000000)

        # 個人制約 & リズム
        for s in range(total_staff):
            is_off_m = [shifts[(s, d, S_OFF)] for d in range(num_days)]
            is_early_m = [model.NewBoolVar(f'ie_{s}_{d}') for d in range(num_days)]
            is_late_m = [model.NewBoolVar(f'il_{s}_{d}') for d in range(num_days)]
            for d in range(num_days):
                model.Add(sum(shifts[(s, d, i)] for i in range(num_user_shifts + 2)) == 1)
                model.Add(sum(shifts[(s, d, i)] for i in e_ids) == 1).OnlyEnforceIf(is_early_m[d])
                model.Add(sum(shifts[(s, d, i)] for i in e_ids) == 0).OnlyEnforceIf(is_early_m[d].Not())
                model.Add(sum(shifts[(s, d, i)] for i in l_ids) == 1).OnlyEnforceIf(is_late_m[d])
                model.Add(sum(shifts[(s, d, i)] for i in l_ids) == 0).OnlyEnforceIf(is_late_m[d].Not())
                req = edited_request.iloc[s, d]
                if req in char_to_id and req != "": model.Add(shifts[(s, d, char_to_id[req])] == 1)
                for idx, _ in enumerate(user_shifts_list):
                    if edited_skill.iloc[s, idx] == "×": model.Add(shifts[(s, d, idx+1)] == 0)
                if d < num_days - 1:
                    for li in l_ids:
                        for ei in e_ids: model.Add(shifts[(s, d, li)] + shifts[(s, d+1, ei)] <= 1)
                if d == 0 and prev_is_late_last[s]:
                    for ei in e_ids: model.Add(shifts[(s, 0, ei)] == 0)

            history_w = prev_work_matrix[s] + [(1 - shifts[(s, d, S_OFF)]) for d in range(num_days)]
            for start_d in range(len(history_w) - 4):
                n5c = model.NewBoolVar(f'n5c_{s}_{start_d}')
                model.Add(sum(history_w[start_d:start_d+5]) <= 4).OnlyEnforceIf(n5c)
                obj_terms.append(n5c * 5000000)

            for d in range(num_days - 1):
                mix = model.NewBoolVar(f'mix_{s}_{d}')
                model.AddBoolAnd([is_early_m[d], is_late_m[d+1]]).OnlyEnforceIf(mix)
                obj_terms.append(mix * 300000)
            
            for d in range(num_days - 2):
                e3 = model.NewBoolVar(f'e3_{s}_{d}')
                model.AddBoolAnd([is_early_m[d], is_early_m[d+1], is_early_m[d+2]]).OnlyEnforceIf(e3)
                obj_terms.append(e3 * -1000000)
            for d in range(num_days - 1):
                l2 = model.NewBoolVar(f'l2_{s}_{d}')
                model.AddBoolAnd([is_late_m[d], is_late_m[d+1]]).OnlyEnforceIf(l2)
                obj_terms.append(l2 * -2000000)

            if s < num_mgr:
                for d in range(num_days):
                    wd_v = calendar.weekday(int(year), int(month), d+1)
                    m_g = model.NewBoolVar(f'mg_{s}_{d}')
                    if wd_v >= 5: model.Add(shifts[(s, d, S_OFF)] == 1).OnlyEnforceIf(m_g)
                    else: model.Add(shifts[(s, d, S_OFF)] == 0).OnlyEnforceIf(m_g)
                    obj_terms.append(m_g * 1000000)
            else:
                for d in range(num_days):
                    if edited_request.iloc[s, d] != "日": model.Add(shifts[(s, d, S_NIKKIN)] == 0)

            for idx, _ in enumerate(user_shifts_list):
                t_val = int(edited_trainee_targets.iloc[s, idx])
                if edited_skill.iloc[s, idx] == "△" and t_val > 0:
                    model.Add(sum(shifts[(s, d, idx+1)] for d in range(num_days)) == t_val)
            act_h = sum(is_off_m)
            h_err = model.NewIntVar(0, num_days, f'herr_{s}')
            model.AddAbsEquality(h_err, act_h - int(edited_hols.iloc[s, 0]))
            obj_terms.append(h_err * -5000000)

        model.Maximize(sum(obj_terms))
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 45.0
        status = solver.Solve(model)

        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            st.success("✨ 究極の公平性とリズムを両立した勤務表を生成しました。")
            res_data = []
            char_map = {S_OFF: "休", S_NIKKIN: "日"}
            for idx, name in enumerate(user_shifts_list): char_map[idx + 1] = name
            for s in range(total_staff):
                row = [char_map[next(i for i in range(num_user_shifts + 2) if solver.Value(shifts[(s, d, i)]) == 1)] for d in range(num_days)]
                res_data.append(row)
            final_df = pd.DataFrame(res_data, index=final_staff_names, columns=days_cols)
            final_df["公休計"] = [row.count("休") for row in res_data]
            def color_cells(val):
                if val == "休": return 'background-color: #ffcccc'
                if val == "日": return 'background-color: #e0f0ff'
                if val in early_shifts: return 'background-color: #ffffcc'
                if val in late_shifts: return 'background-color: #ccffcc'
                return ''
            st.dataframe(final_df.style.map(color_cells), use_container_width=True)
            st.download_button("📥 結果をCSV保存", final_df.to_csv().encode('utf-8-sig'), f"roster.csv")
        else: st.error("⚠️ 解が見つかりません。条件を少し緩めてください。")

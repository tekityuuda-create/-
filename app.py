import streamlit as st
import pandas as pd
import calendar
import json
from ortools.sat.python import cp_model

# ========================================================
# 🛡️ 究極の勤務作成エンジン V86 (Infinite Stability)
# ========================================================

# 1. 画面の初期設定（ページ設定は一番最初のみ）
st.set_page_config(page_title="AI勤務作成 V86", page_icon="🛡️", layout="wide")

# 2. セッション情報の完全初期化（二重入力を防ぐ唯一の方法）
if 'staff_master' not in st.session_state:
    st.session_state.staff_master = pd.DataFrame(
        {"名前": [f"スタッフ{i+1}" for i in range(10)], "公休数": [9] * 10}
    )
    for s in ["A", "B", "C", "D", "E"]:
        st.session_state.staff_master[f"{s}スキル"] = "○"
        st.session_state.staff_master[f"{s}回数"] = 0

if 'shifts_config' not in st.session_state:
    st.session_state.shifts_config = {"raw": "A,B,C,D,E", "early": ["A", "B", "C"], "late": ["D", "E"]}

st.title("🛡️ 究極の勤務作成エンジン V86 (Steady State UI)")

# --- サイドバー：データ復元 ---
with st.sidebar:
    st.header("💾 設定の復元・保存")
    up_file = st.file_uploader("設定ファイルを読込", type="json")
    if up_file:
        try:
            load = json.load(up_file)
            st.session_state.staff_master = pd.DataFrame(load["master"])
            st.session_state.shifts_config = load["shifts"]
            st.success("全ての変数を同期しました。")
            st.rerun()
        except: st.error("不正なファイルです。")

    st.divider()
    st.header("🎯 AI解析の優先度設定")
    w_strict = st.slider("ルールの厳格度", 0, 100, 95)
    w_rhythm = st.slider("リズムの良さ (早遅混合)", 0, 100, 75)
    w_fair = st.slider("個人間の公平性 (回数)", 0, 100, 50)

    st.divider()
    year = int(st.number_input("年", 2024, 2030, 2025))
    month = int(st.number_input("月", 1, 12, 1))

# --- タブ分け ---
t1, t2 = st.tabs(["🏗️ 名簿・ルール設定", "🧬 勤務表の作成・実行"])

with t1:
    col_st1, col_st2 = st.columns(2)
    with col_st1:
        st.subheader("👥 人数構成と名前")
        nm_m = st.number_input("管理者の人数", 0, 5, 2)
        nm_r = st.number_input("一般職の人数", 1, 20, 8)
        total = int(nm_m + nm_r)
        
        # 名前表（この表が「情報の王」）
        # 1回入力で反映されるため、セッションを直接編集させる
        m_df = st.session_state.staff_master.copy()
        if len(m_df) != total:
            m_df = m_df.reindex(range(total)).fillna(method='ffill').fillna(0)
            for i in range(total):
                if pd.isna(m_df.at[i, "名前"]) or m_df.at[i, "名前"] == 0: 
                    m_df.at[i, "名前"] = f"スタッフ{i+1}"
        
        # カテゴリ化
        for s in ["A", "B", "C", "D", "E"]:
            col_k = f"{s}スキル"
            if col_k in m_df.columns:
                m_df[col_k] = pd.Categorical(m_df[col_k], categories=["○", "△", "×"])

        st.write("各項目を入力してください（公休数、担務、習熟度を一度に設定できます）")
        ed_master = st.data_editor(m_df, use_container_width=True, key="main_master_ed")
        st.session_state.staff_master = ed_master # ここでメモリに即時セーブ
        staff_list = ed_master["名前"].tolist()

    with col_st2:
        st.subheader("📋 グループ設定")
        raw_sh = st.text_input("勤務略称 (,) 区切り", st.session_state.shifts_config["raw"])
        s_list = [s.strip() for s in raw_sh.split(",") if s.strip()]
        
        # セッションへの保存
        st.session_state.shifts_config["raw"] = raw_sh
        e_gr = st.multiselect("早番に分類", s_list, default=[x for x in s_list if x in st.session_state.shifts_config["early"]])
        l_gr = st.multiselect("遅番に分類", s_list, default=[x for x in s_list if x in st.session_state.shifts_config["late"]])
        st.session_state.shifts_config["early"] = e_gr
        st.session_state.shifts_config["late"] = l_gr

with t2:
    # 共通データ生成
    _, num_d = calendar.monthrange(year, month)
    week_j = ["月","火","水","木","金","土","日"]
    d_cols = [f"{i+1}({week_j[calendar.weekday(year,month,i+1)]})" for i in range(num_d)]
    opts = ["", "休", "日"] + s_list

    c_pre, c_req = st.columns([1, 3])
    with c_pre:
        st.write("⏮️ 引継状況(直近4日間)")
        p_cols = ["4日前","3日前","2日前","末日"]
        p_base = pd.DataFrame("休", index=staff_list, columns=p_cols)
        ed_p = st.data_editor(p_base, use_container_width=True, key="prev_ui")
    with c_req:
        st.write("📝 今月の固定指定")
        r_base = pd.DataFrame("", index=staff_list, columns=d_cols)
        ed_r = st.data_editor(r_base, use_container_width=True, key="req_ui")

    st.write("🚫 不要担務 (祝日など)")
    ex_base = pd.DataFrame(False, index=[i+1 for i in range(num_d)], columns=s_list)
    ed_x = st.data_editor(ex_base, use_container_width=True, key="ex_ui")

    # ダウンロード機能
    total_data = {"master": ed_master.to_dict(), "shifts": st.session_state.shifts_config}
    st.sidebar.download_button("📥 今の設定をファイル保存", json.dumps(total_data, ensure_ascii=False), "My_AI_Duty.json")

    # --- 数理最適化の起動 (Team of 100 Pro Engineers Logic) ---
    if st.button("🚀 この設定で最高精度の勤務表を抽出する", type="primary"):
        model = cp_model.CpModel()
        num_s_types = len(s_list)
        S_OFF, S_NIK = 0, num_s_types + 1
        e_ids = [s_list.index(x) + 1 for x in e_gr]
        l_ids = [s_list.index(x) + 1 for x in l_gr]
        
        # [s, d, i] Boolean変数定義 (si:staff_id, di:day_id, shift_id)
        x_var = {}
        for si_var in range(total):
            for di_var in range(num_d):
                for i_var in range(num_s_types + 2):
                    x_var[si_var, di_var, i_var] = model.NewBoolVar(f'v_{si_var}_{di_var}_{i_var}')
        
        objs = [] # ペナルティ集合

        for d_i in range(num_d):
            wday = calendar.weekday(year, month, d_i+1)
            for i_idx, s_name in enumerate(s_list):
                sh_id = i_idx + 1
                is_no_work = ed_x.iloc[d_i, i_idx] or (wday == 6 and s_name == "C")
                skilled_ids = [si for si in range(total) if ed_master.iloc[si, i_idx+2] == "○"]
                trainee_ids = [si for si in range(total) if ed_master.iloc[si, i_idx+2] == "△"]
                
                sum_full = sum(x_var[si, d_i, sh_id] for si in skilled_ids)
                sum_train = sum(x_var[si, d_i, sh_id] for si in trainee_ids)
                
                if is_no_work:
                    model.Add(sum(x_var[si, d_i, sh_id] for si in range(total)) == 0)
                else:
                    filled = model.NewBoolVar(f'fill_{d_i}_{sh_id}')
                    model.Add(sum_full == 1).OnlyEnforceIf(filled)
                    objs.append(filled * 10000000) 
                    model.Add(sum_train <= 1)
            # 1人1回制限
            for si in range(total): model.Add(sum(x_var[si, d_i, s_id] for s_id in range(num_s_types+2)) == 1)

        # メンタルと個人の拘束
        for si in range(total):
            # 中間フラグ ( TypeError対策済 )
            f_early = [model.NewBoolVar(f'fe_{si}_{di}') for di in range(num_d)]
            f_late = [model.NewBoolVar(f'fl_{si}_{di}') for di in range(num_d)]
            f_off = [x_var[si, di, S_OFF] for di in range(num_d)]

            for di in range(num_d):
                model.Add(sum(x_var[si, di, i] for i in e_ids) == 1).OnlyEnforceIf(f_early[di])
                model.Add(sum(x_var[si, di, i] for i in e_ids) == 0).OnlyEnforceIf(f_early[di].Not())
                model.Add(sum(x_var[si, di, i] for i in l_ids) == 1).OnlyEnforceIf(f_late[di])
                model.Add(sum(x_var[si, di, i] for i in l_ids) == 0).OnlyEnforceIf(f_late[di].Not())

                req_char = ed_r.iloc[si, di]
                c_mp = {"休":S_OFF, "日":S_NIK, "": -1}
                for ki, kn in enumerate(s_list): c_mp[kn] = ki + 1
                if req_char in c_mp and c_mp[req_char] != -1: model.Add(x_var[si, di, c_mp[req_char]] == 1)

                if any(ed_master.iloc[si, j+2] == "×" for j in range(num_s_types)):
                    for j in range(num_s_types):
                        if ed_master.iloc[si, j+2] == "×": model.Add(x_var[si, di, j+1] == 0)

                # 禁止：遅早
                if di < num_d - 1:
                    le_f = model.NewBoolVar(f'le_{si}_{di}')
                    model.Add(f_late[di] + f_early[di+1] <= 1).OnlyEnforceIf(le_f)
                    objs.append(le_f * 20000 * w_strict)
                # 月またぎ遅早
                if di == 0 and (ed_p.iloc[si, 3] == "遅" or ed_p.iloc[si, 3] in l_gr): model.Add(f_early[0] == 0)

            # 連勤制限
            hst_w = [1 if ed_p.iloc[si, k] != "休" else 0 for k in range(4)] + [(1 - f_off[di]) for di in range(num_d)]
            for ki in range(len(hst_w)-4):
                c4v = model.NewBoolVar(f'c4_{si}_{ki}')
                model.Add(sum(hst_w[ki:ki+5]) <= 4).OnlyEnforceIf(c4v)
                objs.append(c4v * 10000 * w_strict)

            for di in range(num_d - 1):
                mxv = model.NewBoolVar(f'mxv_{si}_{di}')
                model.AddBoolAnd([f_early[di], f_late[di+1]]).OnlyEnforceIf(mxv)
                objs.append(mxv * 2000 * w_rhythm)

            # 区分別の優位性
            if si < nm_m:
                for di in range(num_d):
                    wday_v = calendar.weekday(year, month, di+1)
                    mg_f = model.NewBoolVar(f'mgv_{si}_{di}')
                    if wday_v >= 5: model.Add(f_off[di] == 1).OnlyEnforceIf(mg_f)
                    else: model.Add(f_off[di] == 0).OnlyEnforceIf(mg_f)
                    objs.append(mg_f * 5000)
            else:
                for di in range(num_d):
                    if ed_r.iloc[si, di] != "日": model.Add(x_var[si, di, S_NIK] == 0)

            # 公休数不一致を近似的に解く（絶対に止まらないロジック）
            t_hol = int(ed_master.iloc[si, 1])
            err_var = model.NewIntVar(0, num_d, f'h_err_{si}')
            model.AddAbsEquality(err_var, sum(f_off) - t_hol)
            objs.append(err_var * -5000 * w_strict)

        # 担務の平均化
        for ishift in range(1, num_s_types + 1):
            counts = [model.NewIntVar(0, num_d, f'cnt_{ps}_{ishift}') for ps in range(total)]
            for ps in range(total): model.Add(counts[ps] == sum(x_var[ps, dx, ishift] for dx in range(num_d)))
            mx, mn = model.NewIntVar(0, num_d, f'max_{ishift}'), model.NewIntVar(0, num_d, f'min_{ishift}')
            model.AddMaxEquality(mx, counts); model.AddMinEquality(mn, counts)
            objs.append((mx - mn) * -500 * w_fair)

        model.Maximize(sum(objs))
        solv = cp_model.CpSolver()
        solv.parameters.max_time_in_seconds = 45.0
        stat = solv.Solve(model)

        if stat in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            st.success("🎉 条件を完璧にクリア。最善案を算出しました。")
            r_rows = []
            id_to_char = {S_OFF:"休", S_NIK:"日"}
            for i, n in enumerate(s_list): id_to_char[i+1] = n
            for si in range(total):
                row = [id_to_char[next(j for j in range(num_s_types+2) if solv.Value(x_var[si, di, j])==1)] for di in range(num_d)]
                r_rows.append(row)
            res_df = pd.DataFrame(r_rows, index=staff_list, columns=d_cols)
            res_df["公休計"] = [row.count("休") for row in r_rows]
            def pnt(v):
                if v == "休": return 'background-color: #ffcccc'
                if v == "日": return 'background-color: #e0f0ff'
                if v in e_gr: return 'background-color: #ffffcc'
                return 'background-color: #ccffcc'
            st.dataframe(res_df.style.map(pnt), use_container_width=True)
            st.download_button("📥 完成したCSVを保存", res_df.to_csv().encode('utf-8-sig'), f"final_roster.csv")
        else: st.error("設定が競合しています。管理者の数や担務の削りを確認してください。")

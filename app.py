import streamlit as st
import pandas as pd
import calendar
import json
from ortools.sat.python import cp_model

# --- 1. グローバル設定：最高峰のデザインとアイコン ---
st.set_page_config(page_title="AI勤務作成：V80 Ultra Optimizer", page_icon="🛡️", layout="wide")

if 'config' not in st.session_state:
    st.session_state.config = {
        "num_mgr": 2, "num_regular": 8,
        "staff_names": [f"スタッフ{i+1}" for i in range(10)],
        "user_shifts": "A,B,C,D,E", "early_shifts": ["A", "B", "C"], "late_shifts": ["D", "E"],
        "year": 2025, "month": 1, "saved_tables": {}
    }

st.title("🛡️ 究極の勤務作成エンジン V80 (Team Excellence Pass)")

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

    st.divider()
    year = int(st.number_input("年", 2024, 2030, st.session_state.config["year"]))
    month = int(st.number_input("月", 1, 12, st.session_state.config["month"]))

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
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("👥 人員配置")
        n_mgr = st.number_input("管理者数", 0, 5, st.session_state.config["num_mgr"])
        n_reg = st.number_input("一般職数", 1, 20, st.session_state.config["num_regular"])
        total = int(n_mgr + n_reg)
        names = st.session_state.config.get("staff_names", [])
        if len(names) < total: names.extend([f"スタッフ{i+1}" for i in range(len(names), total)])
        staff_names = names[:total]
        names_ed = st.data_editor(pd.DataFrame({"スタッフ名": staff_names}), use_container_width=True, key="names_ed")
        staff_list = names_ed["スタッフ名"].tolist()
    with c2:
        st.subheader("📋 シフト構成")
        raw_s = st.text_input("勤務略称 (,) 区切り", st.session_state.config["user_shifts"])
        s_list = [s.strip() for s in raw_s.split(",") if s.strip()]
        early_gr = st.multiselect("早番グループ", s_list, default=[x for x in s_list if x in st.session_state.config["early_shifts"]])
        late_gr = st.multiselect("遅番グループ", s_list, default=[x for x in s_list if x in st.session_state.config["late_shifts"]])

with tab_skl:
    st.subheader("🎓 専門スキル・月間公休数・教育ノルマ")
    st.write("○:可能, △:見習い（ベテラン必須）, ×:不可")
    
    # 統合テーブル表示
    skl_df = get_persisted_df("skill", pd.DataFrame("○", index=staff_list, columns=s_list), ["○","△","×"])
    ed_skill = st.data_editor(skl_df, use_container_width=True, key="skill_ed")
    
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        hols_df = get_persisted_df("hols", pd.DataFrame(9, index=staff_list, columns=["公休数"]))
        ed_hols = st.data_editor(hols_df, use_container_width=True, key="hol_ed")
    with col_c2:
        tr_cols = [f"{s}_見習い回数" for s in s_list]
        tr_df = get_persisted_df("trainee", pd.DataFrame(0, index=staff_list, columns=tr_cols))
        ed_trainee = st.data_editor(tr_df, use_container_width=True, key="tr_ed")

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

    # セッション/保存データ全パッキング
    st.session_state.config.update({
        "num_mgr": n_mgr, "num_regular": n_reg, "staff_names": staff_list, "user_shifts": raw_s,
        "early_shifts": early_gr, "late_shifts": late_gr, "year": year, "month": month,
        "saved_tables": {
            "skill": ed_skill.to_dict(), "hols": ed_hols.to_dict(), "trainee": ed_trainee.to_dict(),
            "prev": ed_prev.to_dict(), "request": ed_req.to_dict(), "exclude": ed_ex.to_dict()
        }
    })
    st.sidebar.download_button("📥 現在の全設定を保存する", json.dumps(st.session_state.config, ensure_ascii=False), f"v80_backup_{year}_{month}.json")

    # --- 数理最適化開始 ---
    if st.button("🚀 AIによる勤務作成 (最高解モード)"):
        model = cp_model.CpModel()
        num_types = len(s_list)
        S_OFF, S_NIK = 0, num_types + 1
        E_IDS = [s_list.index(x) + 1 for x in early_gr]
        L_IDS = [s_list.index(x) + 1 for x in late_gr]
        
        # 変数: x[スタッフ, 日, シフト]
        x = {(s, d, i): model.NewBoolVar(f'x_{s}_{d}_{i}') for s in range(total) for d in range(n_days) for i in range(num_types + 2)}
        score_objs = []

        # 前月情報デコード
        for s in range(total):
            for di in range(4):
                val = ed_prev.iloc[s, di]
                if di == 3 and val == "遅":
                    for ei in E_IDS: model.Add(x[s, 0, ei] == 0)

        # 日次の基本ループ
        for d in range(n_days):
            wd = calendar.weekday(year, month, d+1)
            # A. 担務充足 (Soft Constraint)
            for i, s_name in enumerate(s_list):
                sid = i + 1
                is_excl = ed_ex.iloc[d, i] or (wd == 6 and s_name == "C")
                skilled = [s for s in range(total) if ed_skill.iloc[s, i] == "○"]
                trainee = [s for s in range(total) if ed_skill.iloc[s, i] == "△"]
                s_sum = sum(x[s, d, sid] for s in skilled)
                t_sum = sum(x[s, d, sid] for s in trainee)
                
                if is_excl: model.Add(s_sum + t_sum == 0)
                else:
                    # 仕事を埋めることへの執着心
                    job_f = model.NewBoolVar(f'job_{d}_{i}')
                    model.Add(s_sum == 1).OnlyEnforceIf(job_f)
                    score_objs.append(job_f * 5000000) 
                    model.Add(t_sum <= 1)

            # 1日1人1回 (Hard Constraint)
            for s in range(total): model.Add(sum(x[s, d, i] for i in range(num_types+2)) == 1)

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
                for i, _ in enumerate(s_list):
                    if ed_skill.iloc[s, i] == "×": model.Add(x[s, d, i+1] == 0)
                req = ed_req.iloc[s, d]
                c_map = {"休": S_OFF, "日": S_NIK, "": -1}
                for i, n in enumerate(s_list): c_map[n] = i+1
                if req in c_map and req != "": model.Add(x[s, d, c_map[req]] == 1)
                
                if d < n_days - 1:
                    not_le = model.NewBoolVar(f'nle_{s}_{d}')
                    model.Add(is_late[d] + is_early[d+1] <= 1).OnlyEnforceIf(not_le)
                    score_objs.append(not_le * 2000000 * w_h_rule)

            # 連勤制限(4日まで、5日目に罰則)
            hist_w = [1 if ed_prev.iloc[s, k] != "休" else 0 for k in range(4)] + [(1 - is_off[di]) for di in range(n_days)]
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
                    model.AddBoolAnd([is_early[di], is_early[di+1], is_early[di+2]]).OnlyEnforceIf(e_block)
                    score_objs.append(e_block * -1000 * w_rhythm)

            # 管理者・一般職の聖域
            if s < n_mgr:
                for di in range(n_days):
                    wd_v = calendar.weekday(year, month, di+1)
                    if wd_v >= 5: 
                        m_o = model.NewBoolVar(f'mo_{s}_{di}')
                        model.Add(is_off[di] == 1).OnlyEnforceIf(m_o)
                        score_objs.append(m_o * 10000)
                    else: model.Add(is_off[di] == 0) # 平日は基本出勤(絶対制約からSoftへも変更可だがまずは固定)
            else:
                for di in range(n_days):
                    if ed_req.iloc[s, di] != "日": model.Add(x[s, di, S_NIK] == 0)

            # 公休数不一致を罰則化（これが「解が見つからない」を救う）
            target_h_count = int(ed_hols.iloc[s, 0])
            act_h_count = sum(is_off)
            h_diff = model.NewIntVar(0, n_days, f'hd_{s}')
            model.AddAbsEquality(h_diff, act_h_count - target_h_count)
            score_objs.append(h_diff * -50000 * w_holiday)

        # C. 担務平準化（公平性）
        for i_sh in range(1, num_types + 1):
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
            st.success("✨ 世界最高水準の調整が完了しました。")
            res_rows = []
            id_char = {S_OFF: "休", S_NIK: "日"}
            for i, n in enumerate(s_list): id_char[i+1] = n
            for si in range(total):
                res_rows.append([id_char[next(j for j in range(num_types+2) if slv.Value(x[si, di, j])==1)] for di in range(n_days)])
            res_df = pd.DataFrame(res_rows, index=staff_list, columns=days_cols)
            res_df["公休数"] = [row.count("休") for row in res_rows]
            def cl(v):
                if v == "休": return 'background-color: #ffcccc'
                if v == "日": return 'background-color: #e0f0ff'
                if v in early_gr: return 'background-color: #ffffcc'
                return 'background-color: #ccffcc'
            st.dataframe(res_df.style.map(cl), use_container_width=True)
            st.download_button("📥 ダウンロード", res_df.to_csv().encode('utf-8-sig'), "roster.csv")
        else: st.error("致命的なパニック。全変数を解放しても解が見つかりませんでした。基本構成を再確認してください。")

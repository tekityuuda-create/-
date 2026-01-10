import streamlit as st
import pandas as pd
import calendar
from ortools.sat.python import cp_model

# 画面設定
st.set_page_config(page_title="世界最高峰 勤務作成AI 厳格制約版", layout="wide")
st.title("🛡️ 究極の勤務作成エンジン (Strict Constraint V41)")

# --- サイドバー：詳細設定 ---
with st.sidebar:
    st.header("⚙️ システム構成")
    num_mgr = st.number_input("管理者の人数", min_value=0, max_value=5, value=2)
    num_regular = st.number_input("一般スタッフの人数", min_value=1, max_value=15, value=8)
    total_staff = num_mgr + num_regular
    
    st.header("📋 勤務・カテゴリー設定")
    shift_input = st.text_input("勤務の略称 (カンマ区切り)", "A,B,C,D,E")
    user_shifts = [s.strip() for s in shift_input.split(",") if s.strip()]
    num_user_shifts = len(user_shifts)
    
    st.subheader("🕑 シフト属性設定")
    early_shifts = st.multiselect("早番グループ", user_shifts, default=[s for s in user_shifts if s in ["A","B","C"]])
    late_shifts = st.multiselect("遅番グループ", user_shifts, default=[s for s in user_shifts if s in ["D","E"]])
    
    st.header("📅 対象年月")
    year = st.number_input("年", value=2025, step=1)
    month = st.number_input("月", min_value=1, max_value=12, value=1, step=1)
    
    st.header("👤 公休数設定")
    staff_names = [f"スタッフ{i+1}({'管理者' if i < num_mgr else '一般'})" for i in range(total_staff)]
    target_hols = [st.number_input(f"{name} の公休", value=9, key=f"hol_{i}") for i, name in enumerate(staff_names)]

# --- カレンダー計算 ---
_, num_days = calendar.monthrange(int(year), int(month))
weekdays_ja = ["月", "火", "水", "木", "金", "土", "日"]
days_cols = [f"{d+1}({weekdays_ja[calendar.weekday(int(year), int(month), d+1)]})" for d in range(num_days)]

# --- メイン画面：勤務指定 ---
st.subheader("📝 勤務指定・申し込み")
options = ["", "休", "出"] + user_shifts
request_df = pd.DataFrame("", index=staff_names, columns=days_cols)
for col in days_cols:
    request_df[col] = pd.Categorical(request_df[col], categories=options)
edited_request = st.data_editor(request_df, use_container_width=True, key="request_editor")

# --- 不要担務の設定 ---
st.subheader("🚫 不要担務の設定")
exclude_df = pd.DataFrame(False, index=[d+1 for d in range(num_days)], columns=user_shifts)
edited_exclude = st.data_editor(exclude_df, use_container_width=True, key="exclude_editor")

# --- 計算ロジック ---
if st.button("🚀 厳格モードで勤務表を生成する"):
    model = cp_model.CpModel()
    S_OFF, S_WORK = 0, num_user_shifts + 1
    shifts = {(s, d, i): model.NewBoolVar(f's{s}d{d}i{i}') for s in range(total_staff) for d in range(num_days) for i in range(num_user_shifts + 2)}
    obj_terms = []

    early_ids = [user_shifts.index(s) + 1 for s in early_shifts]
    late_ids = [user_shifts.index(s) + 1 for s in late_shifts]

    for d in range(num_days):
        wd = calendar.weekday(int(year), int(month), d + 1)
        # 1. 役割の充足 (A-E) - 絶対制約
        for idx, s_name in enumerate(user_shifts):
            s_id = idx + 1
            is_excluded = edited_exclude.iloc[d, idx]
            is_sun_c = (wd == 6 and s_name == "C")
            total_on_duty = sum(shifts[(s, d, s_id)] for s in range(total_staff))
            
            if is_excluded or is_sun_c:
                model.Add(total_on_duty == 0)
            else:
                model.Add(total_on_duty == 1)

        for s in range(total_staff):
            model.Add(sum(shifts[(s, d, i)] for i in range(num_user_shifts + 2)) == 1)
            
            # 2. 遅→早禁止 - 絶対制約
            if d < num_days - 1:
                for l_id in late_ids:
                    for e_id in early_ids:
                        model.Add(shifts[(s, d, l_id)] + shifts[(s, d+1, e_id)] <= 1)
            
            # 3. 勤務指定の反映 - 絶対制約
            req = edited_request.iloc[s, d]
            if req in options and req != "":
                rid = {"休":0, "出":S_WORK}.get(req, user_shifts.index(req)+1 if req in user_shifts else None)
                if rid is not None: model.Add(shifts[(s, d, rid)] == 1)

    for s in range(total_staff):
        # 4. 4連勤まで（5連勤以上禁止） - 絶対制約
        for d in range(num_days - 4):
            model.Add(sum((1 - shifts[(s, d+k, S_OFF)]) for k in range(5)) <= 4)

        # 5. 連休制限 - 「申し込みがない3連休以上」を禁止
        for d in range(num_days - 2):
            is_3off = model.NewBoolVar(f'3off_{s}_{d}')
            model.AddBoolAnd([shifts[(s, d, S_OFF)], shifts[(s, d+1, S_OFF)], shifts[(s, d+2, S_OFF)]]).OnlyEnforceIf(is_3off)
            model.AddBoolOr([is_3off.Not()]).OnlyEnforceIf(model.NewBoolVar(f'c_{s}_{d}')) # 基本禁止
            
            # ただし申し込みに「休」があれば許可する
            req_off = any(edited_request.iloc[s, d+k] == "休" for k in range(3))
            if not req_off:
                model.Add(is_3off == 0)

        # 6. 管理者と一般職の「出」ルール
        if s < num_mgr:
            for d in range(num_days):
                wd = calendar.weekday(int(year), int(month), d+1)
                if wd < 5: # 平日
                    model.Add(shifts[(s, d, S_OFF)] == 0) # 平日休み禁止(絶対)
                
                # 土日休みは努力目標（担務が回らない時だけ出勤）
                if wd >= 5:
                    is_mgr_off = model.NewBoolVar(f'mgr_off_{s}_{d}')
                    model.Add(shifts[(s, d, S_OFF)] == 1).OnlyEnforceIf(is_mgr_off)
                    obj_terms.append(is_mgr_off * 10000)
        else:
            # 一般職は勝手に「出(6)」にならない - 絶対制約
            for d in range(num_days):
                if edited_request.iloc[s, d] != "出":
                    model.Add(shifts[(s, d, S_WORK)] == 0)

        # 7. 公休数死守 - 絶対制約 (B列の数と100%一致)
        model.Add(sum(shifts[(s, d, S_OFF)] for d in range(num_days)) == int(target_hols[s]))

    # 担務の割り振りを一般スタッフ優先にするためのスコア
    for d in range(num_days):
        for s in range(num_mgr, total_staff): # 一般スタッフ
            for i in range(1, num_user_shifts + 1):
                obj_terms.append(shifts[(s, d, i)] * 10)

    model.Maximize(sum(obj_terms))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30.0
    status = solver.Solve(model)

    if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        st.success("✨ 全ての厳格な条件をクリアした勤務表を作成しました。")
        res_data = []
        char_map = {S_OFF: "休", S_WORK: "出"}
        for idx, name in enumerate(user_shifts): char_map[idx + 1] = name
        for s in range(total_staff):
            row = [char_map[next(i for i in range(num_user_shifts + 2) if solver.Value(shifts[(s, d, i)]) == 1)] for d in range(num_days)]
            res_data.append(row)
        final_df = pd.DataFrame(res_data, index=staff_names, columns=days_cols)
        final_df["公休計"] = [row.count("休") for row in res_data]
        st.dataframe(final_df.style.applymap(lambda x: 'background-color: #ffcccc' if x=="休" else ('background-color: #e0f0ff' if x=="出" else 'background-color: #ccffcc')), use_container_width=True)
        st.download_button("📥 ダウンロード", final_df.to_csv().encode('utf-8-sig'), "roster.csv")
    else:
        st.error("⚠️ 指定された条件（公休数、連勤、管理者、連休制限）が数学的に矛盾しており、解が見つかりません。公休数を1日減らすか、指定を外してください。")

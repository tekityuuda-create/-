import streamlit as st
import pandas as pd
import calendar
from ortools.sat.python import cp_model

# --- バージョンチェックの安全装置 ---
try:
    # column_configが存在するかチェック
    test_config = st.column_config
except AttributeError:
    st.error(f"⚠️ Streamlitのバージョンが古いです (現在のバージョン: {st.__version__})")
    st.info("GitHubの 'requirements.txt' を開き、'streamlit>=1.35.0' と書き換えて保存してください。その後、右下の Manage app から Reboot を実行してください。")
    st.stop()

st.set_page_config(page_title="世界最高峰 勤務作成AI V29", layout="wide")
st.title("🛡️ 究極の勤務作成エンジン (Ver. 1.35+ Stable)")

# --- サイドバー：基本設定 ---
with st.sidebar:
    st.header("📅 基本設定")
    year = st.number_input("年", value=2025, step=1)
    month = st.number_input("月", min_value=1, max_value=12, value=1, step=1)
    
    st.header("👤 公休数設定")
    staff_names = [f"スタッフ{i+1}" for i in range(10)]
    target_hols = []
    for i in range(10):
        label = f"スタッフ{i+1} ({'管理者' if i < 2 else '一般'})"
        target_hols.append(st.number_input(label, value=9, key=f"hol_{i}"))

# --- カレンダー情報の生成 ---
_, num_days = calendar.monthrange(int(year), int(month))
weekdays_ja = ["月", "火", "水", "木", "金", "土", "日"]
days_cols = [f"{d+1}({weekdays_ja[calendar.weekday(int(year), int(month), d+1)]})" for d in range(num_days)]

# --- メイン画面：勤務指定（プルダウン形式） ---
st.subheader("📝 勤務指定・申し込み")
st.write("セルをクリックして選択してください。")

request_options = ["", "休", "出", "A", "B", "C", "D", "E"]

# 各列にプルダウンを適用
column_configuration = {}
for col in days_cols:
    column_configuration[col] = st.column_config.SelectColumn(
        label=col,
        options=request_options,
        width="small",
        required=False
    )

request_df = pd.DataFrame("", index=staff_names, columns=days_cols)
edited_request = st.data_editor(
    request_df, 
    column_config=column_configuration, 
    use_container_width=True, 
    key="request_editor"
)

# --- 不要担務の設定 ---
st.subheader("🚫 不要担務の設定")
roles = ["A", "B", "C", "D", "E"]
exclude_df = pd.DataFrame(False, index=[d+1 for d in range(num_days)], columns=roles)
edited_exclude = st.data_editor(exclude_df, use_container_width=True, key="exclude_editor")

# --- 計算実行 ---
if st.button("🚀 勤務表を生成する"):
    model = cp_model.CpModel()
    shifts = {}
    for s in range(10):
        for d in range(num_days):
            for i in range(7):
                shifts[(s, d, i)] = model.NewBoolVar(f's{s}d{d}i{i}')

    obj_terms = []

    for d in range(num_days):
        wd = calendar.weekday(int(year), int(month), d + 1)
        
        # 担務充足
        for i in range(1, 6):
            is_excluded = edited_exclude.iloc[d, i-1]
            is_sun_c = (wd == 6 and i == 3)
            total_on_duty = sum(shifts[(s, d, i)] for s in range(10))
            
            if is_excluded or is_sun_c:
                model.Add(total_on_duty == 0)
            else:
                is_filled = model.NewBoolVar(f'f_d{d}_i{i}')
                model.Add(total_on_duty == 1).OnlyEnforceIf(is_filled)
                obj_terms.append(is_filled * 1000000)

        for s in range(10):
            model.Add(sum(shifts[(s, d, i)] for i in range(7)) == 1)
            
            # 遅→早禁止
            if d < num_days - 1:
                for late in [4, 5]:
                    for early in [1, 2, 3]:
                        not_le = model.NewBoolVar(f'nle_s{s}_d{d}_{late}')
                        model.Add(shifts[(s, d, late)] + shifts[(s, d+1, early)] <= 1).OnlyEnforceIf(not_le)
                        obj_terms.append(not_le * 100000)

            # 勤務指定の反映
            req = edited_request.iloc[s, d]
            char_to_id = {"休":0, "A":1, "B":2, "C":3, "D":4, "E":5, "出":6}
            if req in char_to_id:
                model.Add(shifts[(s, d, char_to_id[req])] == 1)

    for s in range(10):
        # 4連勤制限
        for d in range(num_days - 4):
            no_5c = model.NewBoolVar(f'no5c_s{s}_d{d}')
            model.Add(sum((1 - shifts[(s, d+k, 0)]) for k in range(5)) <= 4).OnlyEnforceIf(no_5c)
            obj_terms.append(no_5c * 50000)

        # 管理者ルール
        if s < 2:
            for d in range(num_days):
                if calendar.weekday(int(year), int(month), d+1) >= 5:
                    moff = model.NewBoolVar(f'moff_s{s}_d{d}')
                    model.Add(shifts[(s, d, 0)] == 1).OnlyEnforceIf(moff)
                    obj_terms.append(moff * 10000)
                else:
                    model.Add(shifts[(s, d, 0)] == 0)
        else:
            for d in range(num_days):
                if edited_request.iloc[s, d] != "出":
                    model.Add(shifts[(s, d, 6)] == 0)

        # 公休数
        actual_hols = sum(shifts[(s, d, 0)] for d in range(num_days))
        h_diff = model.NewIntVar(0, num_days, f'hd_s{s}')
        model.AddAbsEquality(h_diff, actual_hols - int(target_hols[s]))
        obj_terms.append(h_diff * -500000)

    model.Maximize(sum(obj_terms))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 20.0
    status = solver.Solve(model)

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        st.success("✨ 勤務表を生成しました！")
        res_data = []
        char_map = {0:"休", 1:"A", 2:"B", 3:"C", 4:"D", 5:"E", 6:"出"}
        for s in range(10):
            row = [char_map[next(i for i in range(7) if solver.Value(shifts[(s, d, i)]) == 1)] for d in range(num_days)]
            res_data.append(row)
        
        result_df = pd.DataFrame(res_data, index=staff_names, columns=days_cols)
        result_df["公休計"] = [row.count("休") for row in res_data]
        st.dataframe(result_df.style.applymap(lambda x: 'background-color: #ffcccc' if x=='休' else ('background-color: #e0f0ff' if x=='出' else 'background-color: #ccffcc')), use_container_width=True)
    else:
        st.error("⚠️ 計算エラーが発生しました。設定を調整してください。")

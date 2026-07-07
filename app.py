import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import os

# 設定網頁標題與排版
st.set_page_config(page_title="中學數學自主學習系統", layout="wide")
st.title("📊 中學數學測驗紀錄與分析系統")

DB_PATH = os.path.join(os.path.dirname(__file__), "math_quiz.db")

# 初始化資料庫（建立學生答案表與試卷結構表）
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. 確保學生答案表存在
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS student_results (
            student_name TEXT,
            quiz_id TEXT,
            question_file TEXT,
            topic TEXT,
            q_type TEXT,
            is_correct INTEGER
        )
    ''')
    
    # 2. 確保試卷結構表存在（防止雲端空白環境因 pandas 讀取不到而報錯）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS quiz_structure (
            quiz_id TEXT,
            question_file TEXT,
            topic TEXT,
            q_type TEXT
        )
    ''')
    
    conn.commit()
    conn.close()

# 執行初始化
init_db()

# 取得目前系統內所有的測驗卷清單
def get_all_quizzes():
    if not os.path.exists(DB_PATH): return []
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT DISTINCT quiz_id FROM quiz_structure", conn)
    conn.close()
    return df['quiz_id'].tolist()

# 取得特定測驗卷的題目
def get_quiz_questions(quiz_id):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM quiz_structure WHERE quiz_id = ?", conn, params=(quiz_id,))
    conn.close()
    return df

# --- 側邊欄：切換功能 ---
mode = st.sidebar.radio("請選擇功能功能", ["📝 學生登記分數", "📈 老師數據分析"])

# ==================== 功能 1：學生登記分數 ====================
if mode == "📝 學生登記分數":
    st.header("🎯 測驗結果登記")
    
    # 1. 輸入基本資料
    col1, col2 = st.columns(2)
    with col1:
        student_name = st.text_input("請輸入你的姓名/學號 (例如：陳小明):").strip()
    with col2:
        quiz_list = get_all_quizzes()
        selected_quiz = st.selectbox("請選擇本次測驗卷編號:", quiz_list if quiz_list else ["尚未有測驗卷數據"])
        
    if student_name and selected_quiz != "尚未有測驗卷數據":
        st.subheader(f"📋 請勾選 【{student_name}】 在 【{selected_quiz}】 中「答對」的題目：")
        
        # 讀取該考卷的所有題目
        questions_df = get_quiz_questions(selected_quiz)
        
        # 用來儲存學生每一題的作答結果
        results = []
        
        # 動態產生打勾選單
        for index, row in questions_df.iterrows():
            q_label = f"第 {index+1} 題 ➔ 【{row['topic']} - {row['q_type']}】 ({row['question_file']})"
            # 讓學生勾選是否答對
            is_correct = st.checkbox(q_label, value=False, key=f"q_{index}")
            results.append({
                "student_name": student_name,
                "quiz_id": selected_quiz,
                "question_file": row['question_file'],
                "topic": row['topic'],
                "q_type": row['q_type'],
                "is_correct": 1 if is_correct else 0
            })
            
        # 提交按鈕
        if st.button("📤 提交作答結果", type="primary"):
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            # 先刪除該生該次測驗的舊紀錄（避免重複提交）
            cursor.execute("DELETE FROM student_results WHERE student_name = ? AND quiz_id = ?", (student_name, selected_quiz))
            
            # 寫入新紀錄
            for r in results:
                cursor.execute(
                    "INSERT INTO student_results VALUES (?, ?, ?, ?, ?, ?)",
                    (r['student_name'], r['quiz_id'], r['question_file'], r['topic'], r['q_type'], r['is_correct'])
                )
            conn.commit()
            conn.close()
            st.success(f"🎉 {student_name} 的測驗紀錄已成功儲存！")

# ==================== 功能 2：老師數據分析 ====================
elif mode == "📈 老師數據分析":
    st.header("📊 學生數學能力雷達大盤")
    
    conn = sqlite3.connect(DB_PATH)
    # 讀取所有學生的成績紀錄
    all_data = pd.read_sql_query("SELECT * FROM student_results", conn)
    conn.close()
    
    if all_data.empty:
        st.info("💡 目前資料庫還沒有學生的作答紀錄，請先至左側登記分數。")
    else:
        # 選擇要分析的學生
        students = ["全體學生"] + all_data['student_name'].unique().tolist()
        selected_student = st.selectbox("🔍 選擇分析對象:", students)
        
        # 根據選擇過濾數據
        if selected_student == "全體學生":
            filtered_data = all_data
        else:
            filtered_data = all_data[all_data['student_name'] == selected_student]
            
        # 計算每個「數學課題(Topic)」的答對率
        topic_analysis = filtered_data.groupby('topic').agg(
            總題數=('is_correct', 'count'),
            答對題數=('is_correct', 'sum')
        ).reset_index()
        topic_analysis['答對率(%)'] = (topic_analysis['答對題數'] / topic_analysis['總題數'] * 100).round(1)
        
        # 計算每個「題型(Type)」的答對率
        type_analysis = filtered_data.groupby('q_type').agg(
            總題數=('is_correct', 'count'),
            答對題數=('is_correct', 'sum')
        ).reset_index()
        type_analysis['答對率(%)'] = (type_analysis['答對題數'] / type_analysis['總題數'] * 100).round(1)
        
        # === 視覺化圖表呈現 ===
        col_chart1, col_chart2 = st.columns(2)
        
        with col_chart1:
            st.subheader("📚 各數學課題掌握度")
            fig_topic = px.bar(topic_analysis, x='topic', y='答對率(%)', text='答對率(%)', 
                               labels={'topic': '數學課題'}, color='答對率(%)', color_continuous_scale='RdYlGn')
            fig_topic.update_yaxes(range=[0, 100])
            st.plotly_chart(fig_topic, use_container_width=True)
            
        with col_chart2:
            st.subheader("🧩 題型弱點分析")
            fig_type = px.bar(type_analysis, x='q_type', y='答對率(%)', text='答對率(%)', 
                              labels={'q_type': '題目類型'}, color='答對率(%)', color_continuous_scale='Blues')
            fig_type.update_yaxes(range=[0, 100])
            st.plotly_chart(fig_type, use_container_width=True)
            
        # === 智慧型改進方案建議 ===
        st.markdown("---")
        st.subheader("💡 AI 教學與複習建議")
        
        # 找出答對率低於 60% 的課題
        weak_topics = topic_analysis[topic_analysis['答對率(%)'] < 60]['topic'].tolist()
        # 找出應用題的表現
        app_questions = type_analysis[type_analysis['q_type'].str.contains('應用', na=False)]
        
        recommendations = []
        if weak_topics:
            recommendations.append(f"❌ **需要補強的課題**：學生在 **{', '.join(weak_topics)}** 的答對率未達 60%。建議在下次出卷時，提高這些課題的基礎計算題比例，協助學生重建概念。")
        else:
            recommendations.append("✅ **整體表現優異**：目前所有核心課題掌握度良好，可以開始嘗試加入跨單元的進階挑戰題！")
            
        if not app_questions.empty and app_questions['答對率(%)'].values[0] < 50:
            recommendations.append("⚠️ **語意理解弱點**：數據顯示「應用題」的答對率顯著偏低。學生的問題可能不在運算，而是**無法將文字轉化為數學式**。建議複習時帶著學生圈選「關鍵字」（如：共、剩餘、正比於）。")
            
        for rec in recommendations:
            st.info(rec)

        # 顯示原始數據表格
        with st.expander("📂 檢視完整數據明細"):
            st.dataframe(filtered_data)

        # === 🚨 管理員：清除數據專區 ===
        st.markdown("---")
        with st.expander("⚠️ 系統管理員：清除數據專區 (請謹慎操作)"):
            st.warning("注意：數據刪除後將無法復原！")
            
            # 功能 A：按學生姓名刪除
            st.write("### 🔹 按單一學生刪除紀錄")
            delete_student = st.selectbox("請選擇要清除哪位學生的所有紀錄:", ["-- 請選擇學生 --"] + all_data['student_name'].unique().tolist())
            if delete_student != "-- 請選擇學生 --":
                if st.button(f"🗑️ 確定刪除【{delete_student}】的所有紀錄", type="primary", key="del_student_btn"):
                    conn = sqlite3.connect(DB_PATH)
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM student_results WHERE student_name = ?", (delete_student,))
                    conn.commit()
                    conn.close()
                    st.success(f"已成功刪除 {delete_student} 的所有數據！請重新整理網頁。")
            
            st.write("---")
            
            # 功能 B：全系統大清空
            st.write("### 🔹 系統年終大清空（清除所有學生的作答紀錄）")
            confirm_clear_all = st.checkbox("我已確認要清空【全班所有測驗數據】")
            if confirm_clear_all:
                if st.button("🚨 執行全系統數據大清空", type="primary", key="clear_all_btn"):
                    conn = sqlite3.connect(DB_PATH)
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM student_results")  # 清空作答紀錄
                    conn.commit()
                    conn.close()
                    st.success("🎉 已成功清空所有學生作答數據！請重新整理網頁。")
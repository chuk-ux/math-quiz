import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
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
    
    # 2. 確保試卷結構表存在
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
    
    col1, col2 = st.columns(2)
    with col1:
        student_name = st.text_input("請輸入你的姓名/學號 (例如：陳小明):").strip()
    with col2:
        quiz_list = get_all_quizzes()
        selected_quiz = st.selectbox("請選擇本次測驗卷編號:", quiz_list if quiz_list else ["尚未有測驗卷數據"])
        
    if student_name and selected_quiz != "尚未有測驗卷數據":
        st.subheader(f"📋 請勾選 【{student_name}】 在 【{selected_quiz}】 中「答對」的題目：")
        
        questions_df = get_quiz_questions(selected_quiz)
        results = []
        
        for index, row in questions_df.iterrows():
            q_label = f"第 {index+1} 題 ➔ 【{row['topic']} - {row['q_type']}】 ({row['question_file']})"
            is_correct = st.checkbox(q_label, value=False, key=f"q_{index}")
            results.append({
                "student_name": student_name,
                "quiz_id": selected_quiz,
                "question_file": row['question_file'],
                "topic": row['topic'],
                "q_type": row['q_type'],
                "is_correct": 1 if is_correct else 0
            })
            
        if st.button("📤 提交作答結果", type="primary"):
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM student_results WHERE student_name = ? AND quiz_id = ?", (student_name, selected_quiz))
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
    all_data = pd.read_sql_query("SELECT * FROM student_results", conn)
    conn.close()
    
    if all_data.empty:
        st.info("💡 目前資料庫還沒有學生的作答紀錄，請先至左側登記分數。")
    else:
        # 1. 計算「全體學生」在各課題(Topic)的平均表現，作為基準線
        global_topic = all_data.groupby('topic').agg(
            總題數=('is_correct', 'count'),
            答對題數=('is_correct', 'sum')
        ).reset_index()
        global_topic['全體平均(%)'] = (global_topic['答對題數'] / global_topic['總題數'] * 100).round(1)
        
        # 2. 篩選分析對象
        students = ["全體學生"] + all_data['student_name'].unique().tolist()
        selected_student = st.selectbox("🔍 選擇分析對象:", students)
        
        st.markdown(f"### 📍 【{selected_student}】 核心課題雷達分析")
        
        # 3. 根據選取對象繪製圖表
        if selected_student == "全體學生":
            # 如果是全體學生，畫單一雷達圖
            categories = global_topic['topic'].tolist()
            # 雷達圖需要將最後一個點連回第一個點，所以要把第一個資料複製一份補在最後面
            r_global = global_topic['全體平均(%)'].tolist()
            
            if len(categories) > 0:
                categories_loop = categories + [categories[0]]
                r_global_loop = r_global + [r_global[0]]
                
                fig_radar = go.Figure()
                fig_radar.add_trace(go.Scatterpolar(
                    r=r_global_loop,
                    theta=categories_loop,
                    fill='toself',
                    name='全體平均水準',
                    line_color='#ff7f0e'
                ))
                fig_radar.update_layout(
                    polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                    showlegend=True,
                    height=500
                )
                st.plotly_chart(fig_radar, use_container_width=True)
            
            filtered_data = all_data
            topic_summary = global_topic.rename(columns={'全體平均(%)': '答對率(%)'})
            
        else:
            # 如果選特定學生，做「雙色雷達網重疊對比」（個人 vs 全體）
            student_data = all_data[all_data['student_name'] == selected_student]
            
            student_topic = student_data.groupby('topic').agg(
                個人總題數=('is_correct', 'count'),
                個人答對題數=('is_correct', 'sum')
            ).reset_index()
            student_topic['個人表現(%)'] = (student_topic['個人答對題數'] / student_topic['個人總題數'] * 100).round(1)
            
            # 合併個人與全體數據
            comparison_df = pd.merge(global_topic[['topic', '全體平均(%)']], student_topic[['topic', '個人表現(%)']], on='topic', how='left')
            comparison_df['個人表現(%)'] = comparison_df['個人表現(%)'].fillna(0) # 若該生沒做過該課題，填0
            
            categories = comparison_df['topic'].tolist()
            
            if len(categories) > 0:
                # 頭尾相連閉合迴圈
                categories_loop = categories + [categories[0]]
                r_student_loop = comparison_df['個人表現(%)'].tolist() + [comparison_df['個人表現(%)'].tolist()[0]]
                r_global_loop = comparison_df['全體平均(%)'].tolist() + [comparison_df['全體平均(%)'].tolist()[0]]
                
                # 建立雙色重疊雷達圖
                fig_radar = go.Figure()
                
                # 1. 填入全體平均（放底層，設定半透明）
                fig_radar.add_trace(go.Scatterpolar(
                    r=r_global_loop,
                    theta=categories_loop,
                    fill='toself',
                    name='全體平均水準',
                    fillcolor='rgba(255, 127, 14, 0.3)', # 橘色半透明
                    line=dict(color='#ff7f0e', width=2)
                ))
                
                # 2. 填入個人表現（放頂層）
                fig_radar.add_trace(go.Scatterpolar(
                    r=r_student_loop,
                    theta=categories_loop,
                    fill='toself',
                    name=f'{selected_student} 的表現',
                    fillcolor='rgba(31, 119, 180, 0.5)', # 藍色半透明
                    line=dict(color='#1f77b4', width=3)
                ))
                
                fig_radar.update_layout(
                    polar=dict(
                        radialaxis=dict(visible=True, range=[0, 100], ticksuffix="%"),
                        angularaxis=dict(direction="clockwise") # 順時針排列
                    ),
                    showlegend=True,
                    legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="center", x=0.5),
                    height=550
                )
                st.plotly_chart(fig_radar, use_container_width=True)
            
            filtered_data = student_data
            topic_summary = student_topic.rename(columns={'個人表現(%)': '答對率(%)'})

        # ==================== 🧩 另開分頁/下拉選單：細項類型表現 ====================
        st.markdown("---")
        st.subheader("🔍 課題目錄：點開檢視「題型細項」微觀分析")
        st.write("目前上方主雷達圖僅呈現巨觀課題。若需要針對某一弱點單元進行微觀診斷，請在下方選擇該課題：")
        
        available_topics = filtered_data['topic'].unique().tolist()
        selected_detail_topic = st.selectbox("請選擇欲深入剖析的數學課題:", ["-- 請選擇課題 --"] + available_topics)
        
        if selected_detail_topic != "-- 請選擇課題 --":
            st.markdown(f"#### 📝 課題【{selected_detail_topic}】下的各題型答對率明細")
            
            detail_data = filtered_data[filtered_data['topic'] == selected_detail_topic]
            
            type_analysis = detail_data.groupby('q_type').agg(
                總題數=('is_correct', 'count'),
                答對題數=('is_correct', 'sum')
            ).reset_index()
            type_analysis['答對率(%)'] = (type_analysis['答對題數'] / type_analysis['總題數'] * 100).round(1)
            
            # 題型細項部分依然使用乾淨的單色橫向或縱向長條圖呈現，方便查看具體卡關細節
            fig_type = px.bar(
                type_analysis, x='q_type', y='答對率(%)', text='答對率(%)', 
                labels={'q_type': '題目類型', '答對率(%)': '答對率(%)'},
                color='答對率(%)', color_continuous_scale='Blues'
            )
            fig_type.update_yaxes(range=[0, 100])
            st.plotly_chart(fig_type, use_container_width=True)
            
        # === 智慧型改進方案建議 ===
        st.markdown("---")
        st.subheader("💡 AI 教學與複習建議")
        
        weak_topics = topic_summary[topic_summary['答對率(%)'] < 60]['topic'].tolist()
        recommendations = []
        if weak_topics:
            recommendations.append(f"❌ **需要補強的課題**：目前在 **{', '.join(weak_topics)}** 的掌握度未達 60%（雷達圖出現明顯向內凹陷）。建議點開下方題型，找出是計算還是應用題卡關。")
        else:
            recommendations.append("✅ **整體表現優異**：雷達圖形飽滿，核心課題掌握度良好，可以開始嘗試加入跨單元的綜合進階挑戰題！")
            
        for rec in recommendations:
            st.info(rec)

        # 顯示原始數據表格
        with st.expander("📂 檢視完整數據明細"):
            st.dataframe(filtered_data)

        # === 🚨 管理員：清除數據專區 ===
        st.markdown("---")
        with st.expander("⚠️ 系統管理員：清除數據專區 (請謹慎操作)"):
            st.warning("注意：數據刪除後將無法復原！")
            
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
            
            st.write("### 🔹 系統年終大清空（清除所有學生的作答紀錄）")
            confirm_clear_all = st.checkbox("我已確認要清空【全班所有測驗數據】")
            if confirm_clear_all:
                if st.button("🚨 執行全系統數據大清空", type="primary", key="clear_all_btn"):
                    conn = sqlite3.connect(DB_PATH)
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM student_results")
                    conn.commit()
                    conn.close()
                    st.success("🎉 已成功清空所有學生作答數據！請重新整理網頁。")
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from streamlit_gsheets import GSheetsConnection
import sqlite3
import os

# 設定網頁標題與排版
st.set_page_config(page_title="中學數學自主學習系統", layout="wide")
st.title("📊 中學數學測驗紀錄與分析系統 (GSheets 雲端安全版)")

# [本地保留] quiz_structure 試卷結構依然讀取本地老師出卷的 db 檔案
DB_PATH = os.path.join(os.path.dirname(__file__), "math_quiz.db")

def init_local_db():
    """確保本地試卷結構表存在，防止空白環境報錯"""
    if os.path.exists(DB_PATH):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS quiz_structure (
                quiz_id TEXT, question_file TEXT, topic TEXT, q_type TEXT
            )
        ''')
        conn.commit()
        conn.close()

init_local_db()

# 建立 Google Sheets 連線物件
# 注意：此處連線會自動去讀取後台的 Secrets 設定
conn_gsheet = st.connection("gsheets", type=GSheetsConnection)

def get_student_results_from_cloud():
    """從 Google Sheets 讀取所有學生的作答紀錄"""
    try:
        # worksheet 指定分頁名稱，ttl=0 代表每次都即時讀取不快取
        df = conn_gsheet.read(worksheet="student_results", ttl=0)
        # 如果是剛建好的空白表，可能會讀出空值，需做防呆處理
        if df.empty or df.columns[0].startswith("Unnamed"):
            return pd.DataFrame(columns=["student_name", "quiz_id", "question_file", "topic", "q_type", "is_correct"])
        return df
    except Exception:
        # 若讀取失敗（例如表全新無數據），回傳乾淨的欄位結構
        return pd.DataFrame(columns=["student_name", "quiz_id", "question_file", "topic", "q_type", "is_correct"])

# 取得目前系統內所有的測驗卷清單 (從本地 db 讀取老師出的考卷)
def get_all_quizzes():
    if not os.path.exists(DB_PATH): return []
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT DISTINCT quiz_id FROM quiz_structure", conn)
    conn.close()
    return df['quiz_id'].tolist()

# 取得特定測驗卷的題目 (從本地 db 讀取)
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
            with st.spinner("正在安全同步至雲端 Google Sheets..."):
                # 1. 先讀取雲端現有的全部歷史數據
                current_df = get_student_results_from_cloud()
                
                # 2. 轉換本次新輸入的資料為 DataFrame
                new_df = pd.DataFrame(results)
                
                # 3. 避免重複提交：如果雲端已有該生該次測驗的資料，先將舊資料過濾刪除
                if not current_df.empty:
                    current_df = current_df[~(
                        (current_df['student_name'].astype(str) == str(student_name)) & 
                        (current_df['quiz_id'].astype(str) == str(selected_quiz))
                    )]
                
                # 4. 合併新舊數據
                updated_df = pd.concat([current_df, new_df], ignore_index=True)
                
                # 5. 一鍵強制覆寫回 Google Sheets
                conn_gsheet.update(worksheet="student_results", data=updated_df)
                
                st.success(f"🎉 {student_name} 的測驗紀錄已成功永久儲存在 Google 雲端！")

# ==================== 功能 2：老師數據分析 ====================
elif mode == "📈 老師數據分析":
    st.header("📊 學生數學能力雷達大盤")
    
    # 讀取雲端 Google Sheets 數據，而非本地 sqlite
    all_data = get_student_results_from_cloud()
    
    # 確保 is_correct 欄位是數字型態才能做加總計算
    if not all_data.empty:
        all_data['is_correct'] = pd.to_numeric(all_data['is_correct'], errors='coerce').fillna(0).astype(int)
    
    if all_data.empty or len(all_data) == 0:
        st.info("💡 目前雲端 Google Sheets 還沒有學生的作答紀錄，請先至左側登記分數。")
    else:
        # 1. 計算「全體學生」在各課題(Topic)的平均表現
        global_topic = all_data.groupby('topic').agg(
            總題數=('is_correct', 'count'),
            答對題數=('is_correct', 'sum')
        ).reset_index()
        global_topic['全體平均(%)'] = (global_topic['答對題數'] / global_topic['總題數'] * 100).round(1)
        
        # 2. 篩選分析對象
        students = ["全體學生"] + all_data['student_name'].unique().tolist()
        selected_student = st.selectbox("🔍 選擇分析對象:", students)
        
        st.markdown(f"### 📍 【{selected_student}】 核心課題雷達分析")
        
        if selected_student == "全體學生":
            categories = global_topic['topic'].tolist()
            r_global = global_topic['全體平均(%)'].tolist()
            
            if len(categories) > 0:
                categories_loop = categories + [categories[0]]
                r_global_loop = r_global + [r_global[0]]
                
                fig_radar = go.Figure()
                fig_radar.add_trace(go.Scatterpolar(
                    r=r_global_loop, theta=categories_loop, fill='toself', name='全體平均水準', line_color='#ff7f0e'
                ))
                fig_radar.update_layout(
                    polar=dict(radialaxis=dict(visible=True, range=[0, 100])), showlegend=True, height=500
                )
                st.plotly_chart(fig_radar, use_container_width=True)
            
            filtered_data = all_data
            topic_summary = global_topic.rename(columns={'全體平均(%)': '答對率(%)'})
            
        else:
            student_data = all_data[all_data['student_name'] == selected_student]
            
            student_topic = student_data.groupby('topic').agg(
                個人總題數=('is_correct', 'count'),
                個人答對題數=('is_correct', 'sum')
            ).reset_index()
            student_topic['個人表現(%)'] = (student_topic['個人答對題數'] / student_topic['個人總題數'] * 100).round(1)
            
            comparison_df = pd.merge(global_topic[['topic', '全體平均(%)']], student_topic[['topic', '個人表現(%)']], on='topic', how='left')
            comparison_df['個人表現(%)'] = comparison_df['個人表現(%)'].fillna(0)
            
            categories = comparison_df['topic'].tolist()
            
            if len(categories) > 0:
                categories_loop = categories + [categories[0]]
                r_student_loop = comparison_df['個人表現(%)'].tolist() + [comparison_df['個人表現(%)'].tolist()[0]]
                r_global_loop = comparison_df['全體平均(%)'].tolist() + [comparison_df['全體平均(%)'].tolist()[0]]
                
                fig_radar = go.Figure()
                fig_radar.add_trace(go.Scatterpolar(
                    r=r_global_loop, theta=categories_loop, fill='toself', name='全體平均水準',
                    fillcolor='rgba(255, 127, 14, 0.3)', line=dict(color='#ff7f0e', width=2)
                ))
                fig_radar.add_trace(go.Scatterpolar(
                    r=r_student_loop, theta=categories_loop, fill='toself', name=f'{selected_student} 的表現',
                    fillcolor='rgba(31, 119, 180, 0.5)', line=dict(color='#1f77b4', width=3)
                ))
                fig_radar.update_layout(
                    polar=dict(radialaxis=dict(visible=True, range=[0, 100], ticksuffix="%"), angularaxis=dict(direction="clockwise")),
                    showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="center", x=0.5), height=550
                )
                st.plotly_chart(fig_radar, use_container_width=True)
            
            filtered_data = student_data
            topic_summary = student_topic.rename(columns={'個人表現(%)': '答對率(%)'})

        # ==================== 🧩 另開分頁/下拉選單：細項類型表現 ====================
        st.markdown("---")
        st.subheader("🔍 課題目錄：點開檢視「題型細項」微觀分析")
        
        available_topics = filtered_data['topic'].unique().tolist()
        selected_detail_topic = st.selectbox("請選擇欲深入剖析的數學課題:", ["-- 請選擇課題 --"] + available_topics)
        
        if selected_detail_topic != "-- 請選擇課題 --":
            st.markdown(f"#### 📝 課題【{selected_detail_topic}】下的各題型答對率明細")
            detail_data = filtered_data[filtered_data['topic'] == selected_detail_topic]
            
            type_analysis = detail_data.groupby('q_type').agg(
                總題數=('is_correct', 'count'), 答對題數=('is_correct', 'sum')
            ).reset_index()
            type_analysis['答對率(%)'] = (type_analysis['答對題數'] / type_analysis['總題數'] * 100).round(1)
            
            fig_type = px.bar(
                type_analysis, x='q_type', y='答對率(%)', text='答對率(%)', 
                labels={'q_type': '題目類型', '答對率(%)': '答對率(%)'}, color='答對率(%)', color_continuous_scale='Blues'
            )
            fig_type.update_yaxes(range=[0, 100])
            st.plotly_chart(fig_type, use_container_width=True)
            
        # === 智慧型改進方案建議 ===
        st.markdown("---")
        st.subheader("💡 AI 教學與複習建議")
        weak_topics = topic_summary[topic_summary['答對率(%)'] < 60]['topic'].tolist()
        if weak_topics:
            st.info(f"❌ **需要補強的課題**：目前在 **{', '.join(weak_topics)}** 的掌握度未達 60%（雷達圖向內凹陷）。建議點開下方題型，找出具體卡關原因。")
        else:
            st.info("✅ **整體表現優異**：雷達圖形飽滿，核心課題掌握度良好！")

        # 顯示原始數據表格
        with st.expander("📂 檢視雲端原始數據明細"):
            st.dataframe(all_data)

        # === 🚨 管理員：清除數據專區 (雲端覆寫版) ===
        st.markdown("---")
        with st.expander("⚠️ 系統管理員：清除數據專區 (請謹謹慎操作)"):
            st.warning("注意：數據自 Google Sheets 刪除後將無法復原！")
            
            st.write("### 🔹 按單一學生刪除紀錄")
            delete_student = st.selectbox("請選擇要清除哪位學生的所有紀錄:", ["-- 請選擇學生 --"] + all_data['student_name'].unique().tolist())
            if delete_student != "-- 請選擇學生 --":
                if st.button(f"🗑️ 確定刪除【{delete_student}】的所有紀錄", type="primary", key="del_student_btn"):
                    updated_df = all_data[all_data['student_name'] != delete_student]
                    conn_gsheet.update(worksheet="student_results", data=updated_df)
                    st.success(f"已從 Google Sheets 成功移除 {delete_student} 的數據！網頁即將自動重新整理。")
            
            st.write("---")
            
            st.write("### 🔹 系統年終大清空（清除所有學生的作答紀錄）")
            confirm_clear_all = st.checkbox("我已確認要清空【Google Sheets 上所有全班測驗數據】")
            if confirm_clear_all:
                if st.button("🚨 執行雲端數據大清空", type="primary", key="clear_all_btn"):
                    # 建立一個只有欄位標頭的空表覆寫過去
                    empty_df = pd.DataFrame(columns=["student_name", "quiz_id", "question_file", "topic", "q_type", "is_correct"])
                    conn_gsheet.update(worksheet="student_results", data=empty_df)
                    st.success("🎉 已成功清空 Google 雲端試算表上的所有歷史數據！")
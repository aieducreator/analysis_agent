import streamlit as st
import asyncio
import uuid
import os
import sys
from agent_core import AnalysisApp

# Fix psycopg3 ProactorEventLoop error on Windows
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Setup Page Config
st.set_page_config(page_title="서울시 상권 분석 AI 에이전트", page_icon="🏢", layout="wide")

# Theme / Styling 
st.markdown("""
<style>
    /* Add Custom Premium Styling Here */
    .stApp {
        background-color: #f8f9fa;
    }
    .main-header {
        font-family: 'Inter', sans-serif;
        color: #2b2d42;
        font-weight: 800;
        text-align: center;
        margin-bottom: 2rem;
    }
    .user-msg {
        background-color: #e0f2fe;
        color: #0369a1;
        padding: 1rem;
        border-radius: 10px;
        margin-bottom: 1rem;
    }
    .ai-msg {
        background-color: #ffffff;
        color: #1f2937;
        padding: 1rem;
        border-radius: 10px;
        box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
        margin-bottom: 1rem;
    }
    .step-log {
        font-size: 0.9rem;
        color: #6b7280;
        background-color: #f3f4f6;
        padding: 0.5rem;
        border-radius: 5px;
        margin-bottom: 0.5rem;
        border-left: 3px solid #8b5cf6;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<h1 class="main-header">서울시 상권 분석 AI 에이전트</h1>', unsafe_allow_html=True)

# Initialize Session State
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())

if "messages" not in st.session_state:
    st.session_state.messages = []

# Instantiate App
if "analysis_app" not in st.session_state:
    st.session_state.analysis_app = AnalysisApp()
    
# Setup App
# (AnalysisApp is now stateless regarding db connections)

# Display Chat History
for message in st.session_state.messages:
    if message["role"] == "user":
        with st.chat_message("user"):
            st.markdown(message["content"])
    else:
        with st.chat_message("assistant"):
            if "logs" in message:
                for log in message["logs"]:
                    st.markdown(f'<div class="step-log">{log}</div>', unsafe_allow_html=True)
            st.markdown(message["content"])

# User Input
if prompt := st.chat_input("서울시 상권에 대해 궁금한 점을 질문해보세요..."):
    # Add User Message to History
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    with st.chat_message("user"):
        st.markdown(prompt)

    # Process AI Response
    with st.chat_message("assistant"):
        status_placeholder = st.empty()
        log_placeholder = st.empty()
        
        async def run_agent():
            logs = []
            final_ans = ""
            with status_placeholder.status("데이터 분석 중...", expanded=True) as status:
                async for output in st.session_state.analysis_app.ainvoke_stream(prompt, st.session_state.thread_id):
                    # Output can be from different nodes
                    if "rephrase" in output:
                        rephrased_query = output['rephrase']['rephrased_query']
                        logs.append(f"<b>[Node: Query Rephrasing]</b> => {rephrased_query}")
                        log_placeholder.markdown("<br>".join([f'<div class="step-log">{log}</div>' for log in logs]), unsafe_allow_html=True)
                        
                    elif "generate_sql" in output:
                        sql = output['generate_sql']['sql_query']
                        logs.append(f"<b>[Node: SQL Generation]</b> => <br>```sql\n{sql}\n```")
                        log_placeholder.markdown("<br>".join([f'<div class="step-log">{log}</div>' for log in logs]), unsafe_allow_html=True)
                        
                    elif "execute_sql" in output:
                        logs.append("<b>[Node: SQL Execution]</b> => ✅ 성공")
                        log_placeholder.markdown("<br>".join([f'<div class="step-log">{log}</div>' for log in logs]), unsafe_allow_html=True)
                        
                    elif "generate_report" in output:
                        final_state = output['generate_report']
                        logs.append("<b>[Node: Report Generation]</b> => ✅ 생성 완료")
                        log_placeholder.markdown("<br>".join([f'<div class="step-log">{log}</div>' for log in logs]), unsafe_allow_html=True)
                        final_ans = final_state['messages'][-1].content
                        
                status.update(label="분석 완료", state="complete", expanded=False)
            return logs, final_ans

        logs, final_answer = asyncio.run(run_agent())
        
        st.markdown(final_answer)
        st.session_state.messages.append({
            "role": "assistant", 
            "content": final_answer,
            "logs": logs
        })

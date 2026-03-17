# 필요한 라이브러리 / 모듈 / 함수 임포트
import os
import sqlite3
import json
import asyncio
import uuid
from typing import Annotated
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

# 실행 파일 폴더 경로 가져오기
'''
# 실행 파일: data_analysis_langgraph_upgrade_upgrade.py
'''
folder_path = os.path.dirname(os.path.abspath(__file__))

# API key 가져오기
env_file_path = os.path.join(folder_path, '.env')
load_dotenv(env_file_path)

# db 파일 경로 설정
DB_PATH = os.path.join(folder_path, 'seoul_market_analysis.db')

# PydanticAI에서 사용할 모델 설정 
MODEL_NAME = "openai:gpt-4o-mini"

# 구조화된 출력을 위한 Pydantic 모델 정의
class RephraseResult(BaseModel):
    """질문 재구성 결과 모델"""
    rephrased_query: str = Field(description="맥락이 반영된 구체적인 질문")
    is_data_query: bool = Field(description="데이터 조회가 필요한 질문인지 여부")

class SQLResult(BaseModel):
    """SQL 생성 결과 모델"""
    sql: str = Field(description="실행 가능한 SQLite 쿼리")
    explanation: str | None = Field(default=None, description="쿼리에 대한 짧은 설명")

class ReportResult(BaseModel):
    """최종 보고서 모델"""
    title: str = Field(description="보고서 제목")
    content: str = Field(description="마크다운 형식의 분석 본문")
    conclusion: str = Field(description="핵심 요약 및 제언")

# LangGraph 상태 정의 
class AnalysisState(BaseModel):
    messages: Annotated[list[BaseMessage], add_messages]
    rephrased_query: str = ""
    sql_query: str = ""
    sql_result: list[dict] = Field(default_factory=list)
    final_report: ReportResult | None = None

# 도구 함수 정의
def get_db_schema_info() -> str:
    if not os.path.exists(DB_PATH): return "DB 파일이 없습니다."
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='estimated_sales';")
        result = cursor.fetchone()
        return result[0] if result else "테이블 정보를 찾을 수 없습니다."

def execute_sql_query(sql: str) -> list[dict] | str:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(sql)
            return [dict(row) for row in cursor.fetchall()]
    except sqlite3.Error as e:
        return f"SQL 실행 오류: {e}"

# PydanticAI 에이전트 정의 (각 노드의 '두뇌' 역할) 

## A. 질문 재구성 에이전트
rephrase_agent = Agent(
    model=MODEL_NAME,
    output_type=RephraseResult,
    system_prompt=(
        "당신은 질문 재구성 전문가입니다. 대화 기록을 바탕으로 사용자의 모호한 질문을 "
        "데이터베이스 조회가 가능한 독립적이고 구체적인 질문으로 재구성하세요."
    )
)

## B. SQL 생성 에이전트

sql_agent_system_prompt=f"""
당신은 대한민국 서울시 상권분석 전문가이자 SQL 마스터입니다. 
제공된 DB 스키마와 아래의 **정확한 컬럼 매핑 정보**을 참고하여 사용자 질문에 최적화된 SQLite 쿼리를 작성하세요.

**1. 필독: 정확한 컬럼 매핑**
  - STDR_YYQU_CD: 기준_년분기_코드 (예: '20241' = 2024년 1분기, '2024%' = 2024년 전체)
  - TRDAR_SE_CD_NM: 상권_구분_코드_명 (예: '골목상권', '발달상권', '전통시장', '관광특구')
  - TRDAR_CD_NM: 상권_코드_명 (상권의 실제 이름, 예: '성수동카페거리', '흑리단길', '가로수길' 등)
  - SVC_INDUTY_CD_NM: 서비스_업종_코드_명 (예: '한식음식점', '커피-음료' 등)
  - THSMON_SELNG_AMT: 당월_매출_금액 (분기별 총 매출액)
  - THSMON_SELNG_CO: 당월_매출_건수 (분기별 총 매출건수)
  - MDWK_SELNG_AMT: 주중_매출_금액 (분기별 주중 총 매출액)
  - WKEND_SELNG_AMT: 주말_매출_금액 (분기별 주말 총 매출액, 주의: WKND가 아닌 WKEND입니다)
  - TMZON_11_14_SELNG_AMT: 점심시간(11시~14시) 매출액 (분기별 점심시간 총 매출액)
  - TMZON_17_21_SELNG_AMT: 저녁시간(17시~21시) 매출액 (분기별 저녁시간 총 매출액)
  - ML_SELNG_AMT: 남성_매출_금액 (분기별 남성 총 매출액)
  - FML_SELNG_AMT: 여성_매출_금액 (분기별 여성 총 매출액)
  - AGRDE_10_SELNG_AMT: 10대 연련층의 매출액 (분기별 10대 연령층 총 매출액)
  - AGRDE_20_SELNG_AMT: 20대 연령층의 매출액 (분기별 20대 연령층 총 매출액)
  - AGRDE_30_SELNG_AMT: 30대 연령층의 매출액 (분기별 30대 연령층 총 매출액)
  - AGRDE_40_SELNG_AMT: 40대 연령층의 매출액 (분기별 40대 연령층 총 매출액)
  - AGRDE_50_SELNG_AMT: 50대 연령층의 매출액 (분기별 50대 연령층 총 매출액)
  - AGRDE_60_ABOVE_SELNG_AMT: 60대 이상 연령층의 매출액 (분기별 60대 이상 연령층 총 매출액)
  - 예를 들어, 사용자가 '점심 시간'을 언급하면 `TMZON_11_14_SELNG_AMT` 컬럼을 사용해야 합니다.  

**2. 상권 비교 및 기간 조회 규칙**
  - **상권 비교**: "A와 B 상권을 비교해줘"라는 질문에는 `TRDAR_CD_NM IN ('A', 'B')` 또는 `(TRDAR_CD_NM = 'A' OR TRDAR_CD_NM = 'B')` 구문을 사용하세요.
  - **연간 데이터**: "2024년도" 전체를 물으면 `STDR_YYQU_CD LIKE '2024%'`를 사용하여 1~4분기 데이터를 모두 포함시키세요.
  - **상권 종류 교정**: 사용자가 '골목 상권'(공백 포함)이라고 말해도 DB 값인 '골목상권'으로 조회하세요.

**3. 작성 규칙**
  - 테이블 이름은 반드시 `estimated_sales`를 사용하세요.
  - 결과에는 상권 이름(`TRDAR_CD_NM`)과 질문에서 요구한 수치 컬럼을 반드시 포함하세요.
  - 마크다운 코드 블록 없이 순수한 SQL만 반환하세요.
"""

sql_agent = Agent(
    model=MODEL_NAME,
    output_type=SQLResult,
    system_prompt=sql_agent_system_prompt
)

# C. 보고서 생성 에이전트
report_agent = Agent(
    model=MODEL_NAME,
    output_type=ReportResult,
    system_prompt="당신은 데이터 분석가입니다. 조회된 데이터를 바탕으로 전문적인 마크다운 보고서를 작성하세요."
)

# LangGraph 노드 정의 (PydanticAI 에이전트 활용)

## A. 질문 재구성 노드: 대화 기록을 보고 모호한 질문을 구체화함
async def rephrase_node(state: AnalysisState) -> dict:
    print("\n[Node: Query Rephrasing (PydanticAI)]")
    user_input = state.messages[-1].content
    # 대화 내역을 컨텍스트로 전달
    history_str = "\n".join([f"{m.type}: {m.content}" for m in state.messages[:-1]])
    
    result = await rephrase_agent.run(
        f"이전 대화:\n{history_str}\n\n최신 질문: {user_input}"
    )
    print(f"-> 재구성된 질문: {result.output.rephrased_query}")
    return {"rephrased_query": result.output.rephrased_query}

## B. SQL 생성 노드: 재구성된 질문(rephrased_query)을 바탕으로 SQL 작성
async def sql_generation_node(state: AnalysisState) -> dict:
    print("\n[Node: SQL Generation (PydanticAI)]")
    schema = get_db_schema_info()
    result = await sql_agent.run(
        f"스키마: {schema}\n질문: {state.rephrased_query}"
    )
    print(f"-> 생성된 SQL: {result.output.sql}")
    return {"sql_query": result.output.sql}

## C. SQL 실행 노드
async def sql_execution_node(state: AnalysisState) -> dict:
    print("\n[Node: SQL Execution]")
    result = await asyncio.to_thread(execute_sql_query, state.sql_query)
    return {"sql_result": result if isinstance(result, list) else []}

## D. 보고서 생성 노드 (재구성된 맥락 반영)
async def report_generation_node(state: AnalysisState) -> dict:
    print("\n[Node: Report Generation (PydanticAI)]")
    data_json = json.dumps(state.sql_result, indent=2, ensure_ascii=False)
    result = await report_agent.run(
        f"질문: {state.rephrased_query}\n데이터: {data_json}"
    )
    
    final_content = (
        f"### {result.output.title}\n\n{result.output.content}\n\n"
        f"**요약:** {result.output.conclusion}\n\n"
        f"---\n**실행 쿼리:** `{state.sql_query}`"
    )
    return {"messages": [AIMessage(content=final_content)], "final_report": result.output}

# 그래프 구성 및 실행 

async def main():
    db_file = os.path.join(folder_path, "agent_checkpoint_pydanticai.sqlite")
    
    async with AsyncSqliteSaver.from_conn_string(db_file) as memory:
        builder = StateGraph(AnalysisState)
        
        builder.add_node("rephrase", rephrase_node)
        builder.add_node("generate_sql", sql_generation_node)
        builder.add_node("execute_sql", sql_execution_node)
        builder.add_node("generate_report", report_generation_node)
        
        builder.set_entry_point("rephrase")
        builder.add_edge("rephrase", "generate_sql")
        builder.add_edge("generate_sql", "execute_sql")
        builder.add_edge("execute_sql", "generate_report")
        builder.add_edge("generate_report", END)

        app = builder.compile(checkpointer=memory)
        config = {"configurable": {"thread_id": str(uuid.uuid4())}}

        print("🚀 PydanticAI + LangGraph 하이브리드 에이전트 가동...")

        while True:
            user_input = input("\n사용자: ")
            if user_input.lower() in ["exit", "종료"]: break

            final_state = await app.ainvoke(
                {"messages": [HumanMessage(content=user_input)]}, 
                config=config
            )
            print(f"\nAI: {final_state['messages'][-1].content}")

if __name__ == "__main__":
    asyncio.run(main())
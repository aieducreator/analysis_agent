import os
import sqlite3 # Keep this only if needed, but we migrate to Postgres
import json
import asyncio
import uuid
import psycopg
from psycopg.rows import dict_row
from typing import Annotated, Any
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from sqlalchemy import create_engine, text

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
import sys
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

# Windows asyncio workaround is needed per-thread in Streamlit
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

load_dotenv()

# Supabase URL for PostgreSQL connection
SUPABASE_URL = os.getenv('SUPABASE_URL')
# For psycopg3, we use postgresql://, which Supabase provides
if not SUPABASE_URL:
    raise ValueError("SUPABASE_URL is not set in .env")

# PydanticAI Model Setting
MODEL_NAME = "openai:gpt-4o-mini"

# Structured output models
class RephraseResult(BaseModel):
    rephrased_query: str = Field(description="맥락이 반영된 구체적인 질문")
    is_data_query: bool = Field(description="데이터 조회가 필요한 질문인지 여부")

class SQLResult(BaseModel):
    sql: str = Field(description="실행 가능한 PostgreSQL 쿼리")
    explanation: str | None = Field(default=None, description="쿼리에 대한 짧은 설명")

class ReportResult(BaseModel):
    title: str = Field(description="보고서 제목")
    content: str = Field(description="마크다운 형식의 분석 본문")
    conclusion: str = Field(description="핵심 요약 및 제언")

# LangGraph State
class AnalysisState(BaseModel):
    messages: Annotated[list[BaseMessage], add_messages]
    rephrased_query: str = ""
    sql_query: str = ""
    sql_result: list[dict] = Field(default_factory=list)
    final_report: ReportResult | None = None

# Tool Functions
def get_db_schema_info() -> str:
    schema = """
    Table: estimated_sales
    Columns:
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
    - AGRDE_10_SELNG_AMT: 10대 연령층의 매출액 (분기별 10대 연령층 총 매출액)
    - AGRDE_20_SELNG_AMT: 20대 연령층의 매출액 (분기별 20대 연령층 총 매출액)
    - AGRDE_30_SELNG_AMT: 30대 연령층의 매출액 (분기별 30대 연령층 총 매출액)
    - AGRDE_40_SELNG_AMT: 40대 연령층의 매출액 (분기별 40대 연령층 총 매출액)
    - AGRDE_50_SELNG_AMT: 50대 연령층의 매출액 (분기별 50대 연령층 총 매출액)
    - AGRDE_60_ABOVE_SELNG_AMT: 60대 이상 연령층의 매출액 (분기별 60대 이상 연령층 총 매출액)
    """
    return schema

async def execute_sql_query(sql: str) -> list[dict] | str:
    try:
        # Connect asynchronously using psycopg
        async with await psycopg.AsyncConnection.connect(SUPABASE_URL, autocommit=True, row_factory=dict_row, prepare_threshold=None) as aconn:
            async with aconn.cursor() as acur:
                await acur.execute(sql)
                records = await acur.fetchall()
                if not records:
                    return []
                # Handle Decimal objects for JSON serialization
                processed_records = []
                for idx, record in enumerate(records):
                    processed_record = {}
                    for k, v in record.items():
                        processed_record[k] = float(v) if isinstance(v, (int, float)) else str(v)
                    processed_records.append(processed_record)
                return processed_records

    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"SQL 실행 오류: {e}"

# Agents
rephrase_agent = Agent(
    model=MODEL_NAME,
    output_type=RephraseResult,
    system_prompt=(
        "당신은 질문 재구성 전문가입니다. 대화 기록을 바탕으로 사용자의 모호한 질문을 "
        "데이터베이스 조회가 가능한 독립적이고 구체적인 질문으로 재구성하세요."
    )
)

sql_agent_system_prompt="""
당신은 대한민국 서울시 상권분석 전문가이자 PostgreSQL 마스터입니다.
제공된 DB 스키마와 아래의 **정확한 컬럼 매핑 정보**을 참고하여 사용자 질문에 최적화된 PostgreSQL 쿼리를 작성하세요.

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
  - AGRDE_10_SELNG_AMT: 10대 연령층의 매출액 (분기별 10대 연령층 총 매출액)
  - AGRDE_20_SELNG_AMT: 20대 연령층의 매출액 (분기별 20대 연령층 총 매출액)
  - AGRDE_30_SELNG_AMT: 30대 연령층의 매출액 (분기별 30대 연령층 총 매출액)
  - AGRDE_40_SELNG_AMT: 40대 연령층의 매출액 (분기별 40대 연령층 총 매출액)
  - AGRDE_50_SELNG_AMT: 50대 연령층의 매출액 (분기별 50대 연령층 총 매출액)
  - AGRDE_60_ABOVE_SELNG_AMT: 60대 이상 연령층의 매출액 (분기별 60대 이상 연령층 총 매출액)

**2. 상권 비교 및 기간 조회 규칙**
  - **상권 비교**: "A와 B 상권을 비교해줘"라는 질문에는 `"TRDAR_CD_NM" IN ('A', 'B')` 구문을 사용하세요.
  - **연간 데이터**: "2024년도" 전체를 물으면 `"STDR_YYQU_CD" LIKE '2024%'`를 사용하여 1~4분기 데이터를 모두 포함시키세요.
  - **상권 종류 교정**: 사용자가 '골목 상권'(공백 포함)이라고 말해도 데이터베이스 값인 '골목상권'으로 조회해야 합니다.

**3. 작성 규칙**
  - 테이블 이름은 `public.estimated_sales` (또는 `estimated_sales`)를 사용하세요.
  - PostgreSQL의 대소문자 구분 규칙을 준수하세요. 대문자로 혼합된 컬럼명은 반드시 쌍따옴표(`"`)로 감싸세요 (예: `"TRDAR_CD_NM"`).
  - 결과에는 상권 이름(`"TRDAR_CD_NM"`)과 질문에서 요구한 수치 컬럼을 반드시 포함하세요.
  - **LIMIT** 절을 사용하여 필요시 상위 N개를 제한하세요.
  - 마크다운 코드 블록(예: ```sql ... ```) 없이 순수한 SQL 파싱 가능한 텍스트만 반환하세요.
"""

sql_agent = Agent(
    model=MODEL_NAME,
    output_type=SQLResult,
    system_prompt=sql_agent_system_prompt
)

report_agent = Agent(
    model=MODEL_NAME,
    output_type=ReportResult,
    system_prompt="당신은 데이터 분석가입니다. 조회된 데이터를 바탕으로 전문적인 마크다운 보고서를 작성하세요."
)

# Nodes
async def rephrase_node(state: AnalysisState) -> dict:
    user_input = state.messages[-1].content
    history_str = "\n".join([f"{m.type}: {m.content}" for m in state.messages[:-1]])
    
    result = await rephrase_agent.run(
        f"이전 대화:\n{history_str}\n\n최신 질문: {user_input}"
    )
    return {"rephrased_query": result.output.rephrased_query}

async def sql_generation_node(state: AnalysisState) -> dict:
    schema = get_db_schema_info()
    result = await sql_agent.run(
        f"스키마: {schema}\n질문: {state.rephrased_query}"
    )
    # Ensure there are no markdown quotes around the sql
    clean_sql = result.output.sql.replace("```sql", "").replace("```", "").strip()
    return {"sql_query": clean_sql}

async def sql_execution_node(state: AnalysisState) -> dict:
    result = await execute_sql_query(state.sql_query)
    return {"sql_result": result if isinstance(result, list) else []}

async def report_generation_node(state: AnalysisState) -> dict:
    data_json = json.dumps(state.sql_result, indent=2, ensure_ascii=False)
    result = await report_agent.run(
        f"질문: {state.rephrased_query}\n데이터: {data_json}"
    )
    
    final_content = (
        f"### {result.output.title}\n\n{result.output.content}\n\n"
        f"**요약:** {result.output.conclusion}\n\n"
        # We don't necessarily need to print the query here unless we want to in Streamlit
    )
    return {"messages": [AIMessage(content=final_content)], "final_report": result.output}


# Graph Builder Function
def build_graph():
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
    
    return builder

# App wrapper
class AnalysisApp:
    def __init__(self):
        self.pool = None
        self.checkpointer = None
        self.app = None
        
import sys
import psycopg

# Windows asyncio workaround is needed per-thread in Streamlit
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ... [The app and node definitions up to AnalysisApp]

class AnalysisApp:
    def __init__(self):
        pass
        
    async def ainvoke_stream(self, user_input: str, thread_id: str):
        config = {"configurable": {"thread_id": thread_id}}
        
        # Dynamically create the connection, checkpointer, and graph on each stream request
        # This guarantees they are bound to the current thread's active asyncio Event Loop
        async with await psycopg.AsyncConnection.connect(
            SUPABASE_URL,
            autocommit=True,
            prepare_threshold=None
        ) as conn:
            checkpointer = AsyncPostgresSaver(conn)
            await checkpointer.setup() # create Checkpointer tables if they don't exist
            
            builder = build_graph()
            app = builder.compile(checkpointer=checkpointer)
            
            # Async generator that streams the states
            async for output in app.astream({"messages": [HumanMessage(content=user_input)]}, config=config):
                yield output

    async def close(self):
        pass

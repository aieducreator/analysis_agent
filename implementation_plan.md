# Goal Description

The objective of this project is to upgrade the existing Seoul Commercial Sales Analysis Agent by migrating its local SQLite database to a cloud-based Supabase PostgreSQL database. Additionally, we will develop a Streamlit web application that provides a modern chat interface visualizing the LangGraph node execution process, as specified in the provided presentation. The agent will support multi-user sessions using `thread_id` and a PostgreSQL Checkpointer. Finally, we will prepare the application for deployment to Hugging Face Spaces.

## User Review Required

> [!IMPORTANT]
> The Supabase connection string provided in the `.env` file (`SUPABASE_URL`) will be used for both the SQL database engine and the LangGraph `AsyncPostgresSaver` checkpointer. We will install `langgraph-checkpoint-postgres` and `psycopg-binary` for this purpose. 

> [!NOTE]
> We will create a new file `app.py` for the Streamlit UI, and we'll separate the agent logic into `agent_core.py` to keep the codebase modular, or we can just adapt the existing `data_analysis_langgraph_upgrade_upgrade.py`. For clarity, I propose refactoring the agent code into `agent_core.py`.

## Proposed Changes

### Environment & Setup
- Install required packages: `langgraph`, `langgraph-checkpoint-postgres`, `pydantic-ai`, `streamlit`, `psycopg[binary]`, `psycopg2-binary`, `python-dotenv`.

---

### Database Migration
#### [MODIFY] [seoul_commercial_sales_db.py](file:///c:/Users/gon09/test2/seoul_commercial_sales_db.py)
- Change `DATABASE_URL` to load `SUPABASE_URL` from the `.env` file.
- Adjust SQLAlchemy `create_engine` connection arguments if necessary for Supabase's Transaction Pooler (e.g., `poolclass=NullPool`).
- Run the script to migrate data and report the inserted row counts.

---

### Agent Refactoring
#### [NEW] [agent_core.py](file:///c:/Users/gon09/test2/agent_core.py)
- Refactor the logic from `data_analysis_langgraph_upgrade_upgrade.py`.
- Replace `AsyncSqliteSaver` with `AsyncPostgresSaver` from `langgraph-checkpoint-postgres` to manage session state (`thread_id`) in PostgreSQL.
- Update the SQL Generation Agent System Prompt to strictly generate PostgreSQL-compatible queries targeting the `public` schema and handling case-sensitive columns (using double quotes if needed, though they are uppercase so `\"COLUMN\"` is preferred).
- Update `execute_sql_query` and `get_db_schema_info` to use `psycopg` (v3) to connect to Supabase asynchronously.

---

### UI Development
#### [NEW] [app.py](file:///c:/Users/gon09/test2/app.py)
- Create a Streamlit chat interface.
- Manage `thread_id` in `st.session_state` (generate UUID on first load).
- Input from user -> call `agent_core.py` async LangGraph app.
- Use `st.status()` or expands to visually show the LangGraph steps: `[Node: Query Rephrasing]`, `[Node: SQL Generation]`, `[Node: SQL Execution]`, `[Node: Report Generation]`.
- Render the final Response (Markdown content).

---

### Deployment Configuration
#### [NEW] [Dockerfile](file:///c:/Users/gon09/test2/Dockerfile)
- Python 3.11/3.12 slim image.
- Expose Streamlit port 8501.
- Run `streamlit run app.py`.

#### [NEW] [.github/workflows/sync.yml](file:///c:/Users/gon09/test2/.github/workflows/sync.yml)
- Template to sync Code to Hugging Face Spaces.

## Verification Plan

### Automated Tests
1. **Migration Verification**: Run `seoul_commercial_sales_db.py` directly. Verify the log output shows records perfectly matching the API fetch counts. Then, execute a `COUNT(*)` query directly via the Supabase SQL tool or an ad-hoc python script to confirm 0 data loss.

### Manual Verification
1. **Streamlit UI Testing**: 
   - Start Streamlit locally: `streamlit run app.py`.
   - Ask: `"2024년 전체 기간 동안, '골목 상권' 유형의 상권들 중에서 30대 매출액 총합이 가장 높은 곳을 알려줘"`.
   - Verify the UI displays the sub-steps (Rephrasing, SQL generation, etc.) and outputs the correct report indicating '성수동카페거리' (based on the PPTX example).
   - Provide screenshots/logs via Verification Artifact.

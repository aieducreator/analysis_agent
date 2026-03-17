import os
import requests
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
from dotenv import load_dotenv
import time

load_dotenv()
API_KEY = os.getenv('SEOUL_DATA_API_KEY')
BASE_URL = "http://openapi.seoul.go.kr:8088"
SERVICE_NAME = "VwsmTrdarSelngQq"

# Supabase PostgreSQL 연결 설정
SUPABASE_URL = os.getenv('SUPABASE_URL')
# SQLAlchemy uses postgresql+psycopg2:// scheme, so we need to replace it if it's just postgresql://
if SUPABASE_URL and SUPABASE_URL.startswith("postgresql://"):
    DATABASE_URL = SUPABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)
else:
    DATABASE_URL = SUPABASE_URL
TABLE_NAME = "estimated_sales"
QUARTERS = ['20241', '20242', '20243', '20244', '20251', '20252', '20253']

def fetch_seoul_api_data(quarter):
    all_data = []
    start_idx = 1
    end_idx = 1000
    print(f"--- [{quarter}] Fetching Data ---")
    while True:
        url = f"{BASE_URL}/{API_KEY}/json/{SERVICE_NAME}/{start_idx}/{end_idx}/{quarter}"
        try:
            response = requests.get(url)
            data = response.json()
            if SERVICE_NAME in data:
                total_count = data[SERVICE_NAME]['list_total_count']
                rows = data[SERVICE_NAME]['row']
                all_data.extend(rows)
                print(f"Progress: {len(all_data)} / {total_count}")
                if len(all_data) >= total_count:
                    break
                start_idx += 1000
                end_idx += 1000
                time.sleep(0.1)
            else:
                error_msg = data.get('RESULT', {}).get('MESSAGE', 'No Data')
                print(f"Alert: {quarter} Fetch failed ({error_msg})")
                break
        except Exception as e:
            print(f"Error: {e}")
            break
    return pd.DataFrame(all_data)

def save_to_postgres(df, engine, table_name, q_idx):
    if df.empty:
        return 0
    try:
        # 첫 번째 분기면 replace로 테이블 정의, 이후는 append
        if_exists_arg = 'replace' if q_idx == 0 else 'append'
        df.to_sql(table_name, engine, if_exists=if_exists_arg, index=False)
        return len(df)
    except Exception as e:
        print(f"Save error: {e}")
        return 0

def verify_storage(engine, table_name, expected_counts):
    print("\n" + "="*30)
    print("Data Storage Verification Report")
    print("="*30)
    try:
        for quarter, exp_cnt in expected_counts.items():
            query = f"SELECT COUNT(*) FROM {table_name} WHERE \"STDR_YYQU_CD\" = '{quarter}'"
            db_cnt = pd.read_sql_query(query, engine).iloc[0, 0]
            status = "Match" if exp_cnt == db_cnt else "Mismatch"
            print(f"Quarter: {quarter} | API: {exp_cnt:5d} | DB: {db_cnt:5d} | Result: {status}")
    except Exception as e:
        print(f"Verify error: {e}")

if __name__ == "__main__":
    total_expected = {}
    
    # Supabase Transaction Pooler에 최적화된 엔진 설정
    engine = create_engine(DATABASE_URL, poolclass=NullPool)
    
    try:
        # 수집 시도
        all_dfs = []
        for i, q in enumerate(QUARTERS):
            df_quarter = fetch_seoul_api_data(q)
            if not df_quarter.empty:
                # 데이터를 한 번에 넣기 위해 메모리에 쌓기 (선택 사항)
                saved_count = save_to_postgres(df_quarter, engine, TABLE_NAME, i)
                total_expected[q] = saved_count
            else:
                total_expected[q] = 0

        # 검증 실행
        verify_storage(engine, TABLE_NAME, total_expected)
    finally:
        engine.dispose()
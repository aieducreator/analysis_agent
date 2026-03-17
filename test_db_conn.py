import asyncio
import os
import sys
import psycopg
from dotenv import load_dotenv

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

load_dotenv()

async def test_conn():
    url = os.getenv("SUPABASE_URL")
    print(f"URL: {url}")
    try:
        async with await psycopg.AsyncConnection.connect(url, prepare_threshold=None) as conn:
            print("Successfully connected!")
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1")
                print("Query executed!")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_conn())

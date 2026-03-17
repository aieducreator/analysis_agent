import sys
import asyncio
import os
import streamlit as st
from psycopg_pool import AsyncConnectionPool
from dotenv import load_dotenv

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

load_dotenv()

st.title("Connection Pool Test")

async def test_pool():
    url = os.getenv("SUPABASE_URL")
    st.write("Initializing pool...")
    try:
        pool = AsyncConnectionPool(
            conninfo=url,
            max_size=2,
            kwargs={'autocommit': True, 'prepare_threshold': None},
            open=False
        )
        await pool.open()
        st.write("Pool opened successfully!")
        
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1")
                res = await cur.fetchone()
                st.write(f"Query Result: {res}")
        await pool.close()
    except Exception as e:
        import traceback
        st.error(f"Error: {e}")
        st.text(traceback.format_exc())

if st.button("Test Pool"):
    asyncio.run(test_pool())

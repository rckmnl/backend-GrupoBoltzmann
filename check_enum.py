import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

async def check_enum():
    engine = create_async_engine(DATABASE_URL)
    async with engine.connect() as conn:
        # Consulta para ver los valores actuales del ENUM en PostgreSQL
        result = await conn.execute(text("""
            SELECT n.nspname AS schema, t.typname AS type, e.enumlabel AS value
            FROM pg_type t 
            JOIN pg_enum e ON t.oid = e.enumtypid  
            JOIN pg_catalog.pg_namespace n ON n.oid = t.typnamespace
            WHERE t.typname = 'appointmentstatus';
        """))
        rows = result.fetchall()
        print("--- Current values in 'appointmentstatus' ENUM ---")
        for row in rows:
            print(f"Value: '{row[2]}'")
            
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check_enum())

import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = "postgresql://boltzman_db_user:M8kjsyKFYGVY3bNRFyzRPFiQStaGURV1@dpg-d5ik0dh5pdvs73c3skg0-a.oregon-postgres.render.com/boltzman_db"

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://") and "+asyncpg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

async def check_enum():
    engine = create_async_engine(DATABASE_URL)
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT enumlabel FROM pg_enum JOIN pg_type ON pg_enum.enumtypid = pg_type.oid WHERE pg_type.typname = 'appointmentstatus';"))
        labels = [row[0] for row in result]
        print(f"Current labels in appointmentstatus: {labels}")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check_enum())

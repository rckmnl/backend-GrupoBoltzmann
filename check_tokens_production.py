import asyncio
import os
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from app.models.models import User
from dotenv import load_dotenv

load_dotenv()

# Fix para Windows Event Loop
if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

DATABASE_URL = "postgresql://boltzman_db_user:M8kjsyKFYGVY3bNRFyzRPFiQStaGURV1@dpg-d5ik0dh5pdvs73c3skg0-a.oregon-postgres.render.com/boltzman_db"

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://") and "+asyncpg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(DATABASE_URL)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def check_tokens():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.push_token != None))
        users = result.scalars().all()
        print(f"\n--- USUARIOS CON PUSH TOKEN ({len(users)}) ---")
        for u in users:
            print(f"User: {u.email} | Role: {u.role} | Token: {u.push_token[:20]}...")

if __name__ == "__main__":
    asyncio.run(check_tokens())

import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from app.models.models import User

DATABASE_URL = "sqlite+aiosqlite:///./boltzman_local.db"
engine = create_async_engine(DATABASE_URL)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def check_tokens():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.push_token != None))
        users = result.scalars().all()
        print(f"--- Users with push tokens ({len(users)}) ---")
        for u in users:
            print(f"Email: {u.email} | Role: {u.role} | Token: {u.push_token[:20]}...")

if __name__ == "__main__":
    asyncio.run(check_tokens())

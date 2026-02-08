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

async def fix_enum():
    # Creamos el motor con isolation_level="AUTOCOMMIT" directamente
    engine = create_async_engine(DATABASE_URL, isolation_level="AUTOCOMMIT")
    
    uppercase_labels = [
        "PENDING", "SCHEDULED", "IN_PROGRESS", "COMPLETED", 
        "PENDING_PAYMENT", "PAYMENT_VERIFYING", "PAID", "CANCELLED"
    ]
    
    async with engine.connect() as conn:
        for label in uppercase_labels:
            try:
                await conn.execute(text(f"ALTER TYPE appointmentstatus ADD VALUE '{label}';"))
                print(f"✅ Added {label}")
            except Exception as e:
                if "already exists" in str(e).lower():
                    print(f"ℹ️  {label} already exists.")
                else:
                    print(f"❌ Error adding {label}: {e}")

    await engine.dispose()
    print("\n🎉 Enum update finished.")

if __name__ == "__main__":
    asyncio.run(fix_enum())

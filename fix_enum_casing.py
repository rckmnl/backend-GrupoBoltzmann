import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

async def update_enum():
    engine = create_async_engine(DATABASE_URL)
    # ALTER TYPE ADD VALUE no puede correr en transaccion en PG
    # SQLAlchemy engine.begin() abre transaccion. Usamos connect() sin transaccion manual.
    async with engine.connect() as conn:
        print("\n--- Adding UPPERCASE versions of new statuses to ENUM ---")
        # SQLAlchemys usually sends the member NAME if not told otherwise.
        # Original members in DB are uppercase (PENDING, etc.)
        new_statuses = ["PENDING_PAYMENT", "PAYMENT_VERIFYING", "PAID"]
        for status in new_statuses:
            try:
                # Corremos fuera de transaccion implícita si es posible
                await conn.execute(text(f"ALTER TYPE appointmentstatus ADD VALUE '{status}';"))
                # Hacemos commit explícito para cada uno si es necesario (asyncpg connect suele auto-commit si no hay transaccion)
                await conn.commit() 
                print(f"✅ Added {status} to appointmentstatus enum")
            except Exception as e:
                print(f"⚠️  Could not add {status} (maybe exists): {e}")
            
    await engine.dispose()
    print("\n🎉 Enum update finished.")

if __name__ == "__main__":
    asyncio.run(update_enum())

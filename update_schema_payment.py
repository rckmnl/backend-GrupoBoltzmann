import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
# Asegurar driver asyncpg
if DATABASE_URL and DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

async def update_schema():
    print(f"Connecting to DB: {DATABASE_URL}")
    engine = create_async_engine(DATABASE_URL, echo=True)
    
    async with engine.begin() as conn:
        print("\n--- Updating 'appointmentstatus' ENUM ---")
        new_statuses = ["pending_payment", "payment_verifying", "paid"]
        for status in new_statuses:
            try:
                # PostgreSQL no permite ejecutar ALTER TYPE dentro de bloques TRANSACTIONAL de sqlalchemy de forma simple si falla uno
                # Usamos engine.begin() que abre transaccion, pero ALTER TYPE ADD VALUE no puede correr en transaccion en algunas versiones de PG
                # Sin embargo, con asyncpg/sqlalchemy suele funcionar si se maneja error
                await conn.execute(text(f"ALTER TYPE appointmentstatus ADD VALUE '{status}';"))
                print(f"✅ Added {status} to appointmentstatus enum")
            except Exception as e:
                print(f"⚠️  Could not add {status} (maybe exists): {e}")

        print("\n--- Adding Payment Columns to 'service_appointments' table ---")
        
        try:
            await conn.execute(text("ALTER TABLE service_appointments ADD COLUMN total_cost FLOAT DEFAULT 0.0;"))
            print("✅ Added total_cost column")
        except Exception as e:
            print(f"⚠️  Could not add total_cost: {e}")

        try:
            await conn.execute(text("ALTER TABLE service_appointments ADD COLUMN payment_reference VARCHAR;"))
            print("✅ Added payment_reference column")
        except Exception as e:
            print(f"⚠️  Could not add payment_reference: {e}")

        try:
            await conn.execute(text("ALTER TABLE service_appointments ADD COLUMN payment_screenshot_url VARCHAR;"))
            print("✅ Added payment_screenshot_url column")
        except Exception as e:
            print(f"⚠️  Could not add payment_screenshot_url: {e}")

    await engine.dispose()
    print("\n🎉 Schema update for payments finished.")

if __name__ == "__main__":
    asyncio.run(update_schema())

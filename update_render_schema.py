import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
import os

# URL de Render (reemplaza con tu URL real de la variable RENDER_DB_URL)
RENDER_DB_URL = os.getenv("RENDER_DB_URL") or "postgresql+asyncpg://boltzman_db_user:M8kjsyKFYGVY3bNRFyzRPFiQStaGURV1@dpg-d5ik0dh5pdvs73c3skg0-a.oregon-postgres.render.com/boltzman_db"

async def update_schema():
    print(f"🔗 Conectando a Render DB...")
    engine = create_async_engine(RENDER_DB_URL, echo=True)
    
    async with engine.begin() as conn:
        print("\n--- Añadiendo columnas a 'users' ---")
        try:
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS photo_url VARCHAR;"))
            print("✅ photo_url añadida")
        except Exception as e:
            print(f"⚠️  {e}")

        try:
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_number VARCHAR;"))
            print("✅ phone_number añadida")
        except Exception as e:
            print(f"⚠️  {e}")

        print("\n--- Creando tabla 'password_reset_tokens' ---")
        try:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS password_reset_tokens (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    token VARCHAR UNIQUE NOT NULL,
                    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (now() at time zone 'utc'),
                    expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
                    used BOOLEAN DEFAULT FALSE
                );
            """))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_password_reset_tokens_token ON password_reset_tokens (token);"))
            print("✅ Tabla creada")
        except Exception as e:
            print(f"❌ {e}")

    await engine.dispose()
    print("\n🎉 Actualización de Render completada.")

if __name__ == "__main__":
    asyncio.run(update_schema())

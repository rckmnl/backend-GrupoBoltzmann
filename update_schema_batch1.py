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
        print("--- Adding Columns to 'users' table ---")
        try:
            await conn.execute(text("ALTER TABLE users ADD COLUMN photo_url VARCHAR;"))
            print("✅ Added photo_url column")
        except Exception as e:
            print(f"⚠️  Could not add photo_url (maybe exists): {e}")

        try:
            await conn.execute(text("ALTER TABLE users ADD COLUMN phone_number VARCHAR;"))
            print("✅ Added phone_number column")
        except Exception as e:
            print(f"⚠️  Could not add phone_number (maybe exists): {e}")

        print("\n--- Creating 'password_reset_tokens' table ---")
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
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_password_reset_tokens_id ON password_reset_tokens (id);"))
            print("✅ Created password_reset_tokens table")
        except Exception as e:
            print(f"❌ Error creating table: {e}")

    await engine.dispose()
    print("\n🎉 Schema update finished.")

if __name__ == "__main__":
    asyncio.run(update_schema())

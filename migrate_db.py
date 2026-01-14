import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

async def migrate():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        print("Migrating service_appointments...")
        try:
            # Add technician_id
            await conn.execute(text("ALTER TABLE service_appointments ADD COLUMN IF NOT EXISTS technician_id INTEGER REFERENCES users(id);"))
            # Add scheduled_date
            await conn.execute(text("ALTER TABLE service_appointments ADD COLUMN IF NOT EXISTS scheduled_date TIMESTAMP;"))
            # Add admin_notes
            await conn.execute(text("ALTER TABLE service_appointments ADD COLUMN IF NOT EXISTS admin_notes VARCHAR;"))
            
            # --- NUEVO: Add appointment_id to maintenance_logs
            await conn.execute(text("ALTER TABLE maintenance_logs ADD COLUMN IF NOT EXISTS appointment_id INTEGER REFERENCES service_appointments(id);"))
            # --- NUEVO 2: Campos de Timer y Firma
            await conn.execute(text("ALTER TABLE service_appointments ADD COLUMN IF NOT EXISTS start_travel_at TIMESTAMP;"))
            await conn.execute(text("ALTER TABLE service_appointments ADD COLUMN IF NOT EXISTS arrived_at TIMESTAMP;"))
            await conn.execute(text("ALTER TABLE maintenance_logs ADD COLUMN IF NOT EXISTS client_signature_url VARCHAR;"))
            
            # --- NUEVO: Add push_token to users
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS push_token VARCHAR;"))

            # --- NUEVO: Rating columns
            await conn.execute(text("ALTER TABLE service_appointments ADD COLUMN IF NOT EXISTS rating INTEGER;"))
            await conn.execute(text("ALTER TABLE service_appointments ADD COLUMN IF NOT EXISTS rating_comments VARCHAR;"))

            # --- NUEVO: Bitácora de Trabajo (Timestamps)
            await conn.execute(text("ALTER TABLE service_appointments ADD COLUMN IF NOT EXISTS accepted_at TIMESTAMP;"))
            await conn.execute(text("ALTER TABLE service_appointments ADD COLUMN IF NOT EXISTS started_at TIMESTAMP;"))
            await conn.execute(text("ALTER TABLE service_appointments ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP;"))
            
            # --- NUEVO: Múltiples Fotos
            await conn.execute(text("ALTER TABLE maintenance_logs ADD COLUMN IF NOT EXISTS photo_urls JSON;"))

            # --- NUEVO: Ubicación en Mapa (Equipos)
            await conn.execute(text("ALTER TABLE devices ADD COLUMN IF NOT EXISTS latitude FLOAT;"))
            await conn.execute(text("ALTER TABLE devices ADD COLUMN IF NOT EXISTS longitude FLOAT;"))

            print("Successfully updated tables with new columns.")
        except Exception as e:
            print(f"Error migrating: {e}")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(migrate())

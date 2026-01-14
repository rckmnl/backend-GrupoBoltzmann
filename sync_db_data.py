import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

# Import your models
from app.models.models import Base, Organization, User, Device, MaintenanceLog, ServiceAppointment, TechnicianInvitation

load_dotenv()

# CONFIGURATION
LOCAL_DB_URL = os.getenv("DATABASE_URL") # Currently set to local
RENDER_DB_URL = "postgresql://boltzman_db_user:M8kjsyKFYGVY3bNRFyzRPFiQStaGURV1@dpg-d5ik0dh5pdvs73c3skg0-a.oregon-postgres.render.com/boltzman_db" # Added common suffix for external access if missing

async def copy_table(source_session, dest_session, model):
    print(f"Copying {model.__tablename__}...")
    result = await source_session.execute(select(model))
    items = result.scalars().all()
    
    for item in items:
        # Create a new instance with the same data to avoid session attachment issues
        data = {c.name: getattr(item, c.name) for c in item.__table__.columns}
        new_item = model(**data)
        dest_session.add(new_item)
    
    await dest_session.commit()
    print(f"Successfully copied {len(items)} items from {model.__tablename__}.")

async def migrate_data():
    if RENDER_DB_URL == "PORE_AQUI_TU_EXTERNAL_URL_DE_RENDER":
        print("ERROR: Por favor, pon tu URL externa de Render en la variable RENDER_DB_URL dentro del script.")
        return

    # Engines
    def fix_url(url):
        if not url: return url
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    local_url = fix_url(LOCAL_DB_URL)
    render_url = fix_url(RENDER_DB_URL)

    source_engine = create_async_engine(local_url)
    dest_engine = create_async_engine(render_url)

    # Sessions
    SourceSession = sessionmaker(source_engine, class_=AsyncSession, expire_on_commit=False)
    DestSession = sessionmaker(dest_engine, class_=AsyncSession, expire_on_commit=False)

    async with SourceSession() as source_session:
        async with DestSession() as dest_session:
            # Table order matters for Foreign Keys
            tables = [
                Organization,
                User,
                Device,
                ServiceAppointment,
                MaintenanceLog,
                TechnicianInvitation
            ]
            
            for table in tables:
                try:
                    await copy_table(source_session, dest_session, table)
                except Exception as e:
                    print(f"Error copying {table.__tablename__}: {e}")
                    await dest_session.rollback()

    await source_engine.dispose()
    await dest_engine.dispose()
    print("\nMigración completada. Ya puedes usar tu backend en Render con los datos actualizados.")

if __name__ == "__main__":
    asyncio.run(migrate_data())

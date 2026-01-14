import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
import os
from dotenv import load_dotenv

load_dotenv()

# CONFIGURATION
# Usa la misma URL que usaste en sync_db_data.py
RENDER_DB_URL = "postgresql://boltzman_db_user:M8kjsyKFYGVY3bNRFyzRPFiQStaGURV1@dpg-d5ik0dh5pdvs73c3skg0-a.oregon-postgres.render.com/boltzman_db"

async def fix_sequences():
    def fix_url(url):
        if not url: return url
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    render_url = fix_url(RENDER_DB_URL)
    engine = create_async_engine(render_url)

    tables = [
        "organizations",
        "users",
        "devices",
        "service_appointments",
        "maintenance_logs",
        "technician_invitations"
    ]

    print("Fixing sequences on Render database...")
    async with engine.begin() as conn:
        for table in tables:
            try:
                # Esta sentencia busca el valor máximo actual del ID y ajusta el contador automático (sequence)
                query = text(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), coalesce(max(id), 1), max(id) IS NOT null) FROM {table};")
                await conn.execute(query)
                print(f"  - Sequence for '{table}' synchronized.")
            except Exception as e:
                print(f"  - Error fixing sequence for '{table}': {e}")

    await engine.dispose()
    print("\n¡Listo! Las secuencias han sido corregidas. Intenta registrarte de nuevo.")

if __name__ == "__main__":
    asyncio.run(fix_sequences())

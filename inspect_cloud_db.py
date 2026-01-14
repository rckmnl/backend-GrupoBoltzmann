import asyncio
import sys
import os
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from app.models.models import User, Organization, Device, ServiceAppointment, MaintenanceLog
from dotenv import load_dotenv

# Configuración para Windows
if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# URL de Producción (Render)
DATABASE_URL = "postgresql://boltzman_db_user:M8kjsyKFYGVY3bNRFyzRPFiQStaGURV1@dpg-d5ik0dh5pdvs73c3skg0-a.oregon-postgres.render.com/boltzman_db"

if not DATABASE_URL:
    print("❌ Error: No se tiene la URL de la base de datos.")
    sys.exit(1)

# Fix para asyncpg
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://") and "+asyncpg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

print(f"☁️  Conectando a la NUBE: {DATABASE_URL.split('@')[1]}")

engine = create_async_engine(DATABASE_URL)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def inspectex():
    async with AsyncSessionLocal() as db:
        print("\n" + "="*50)
        print("          REPORTE DE ESTADO (RENDER CLOUD)          ")
        print("="*50)

        # 1. ORGANIZACIONES
        print("\n🏢 ORGANIZACIONES:")
        result = await db.execute(select(Organization))
        orgs = result.scalars().all()
        for org in orgs:
            print(f"   - [ID: {org.id}] {org.name} ({'Corporativo' if org.is_corporate else 'Residencial'})")
        if not orgs: print("   (Vacío)")

        # 2. USUARIOS
        print("\n👥 USUARIOS:")
        result = await db.execute(select(User))
        users = result.scalars().all()
        for u in users:
            print(f"   - [ID: {u.id}] {u.email} | Rol: {u.role.value} | Org: {u.organization_id}")
        if not users: print("   (Vacío)")

        # 3. DISPOSITIVOS
        print("\n❄️  EQUIPOS (Aires Acondicionados):")
        result = await db.execute(select(Device))
        devices = result.scalars().all()
        for d in devices:
            print(f"   - [ID: {d.id}] {d.brand} {d.model} ({d.device_type}) | QR: {d.qr_code}")
        if not devices: print("   (Vacío)")

        # 4. TRABAJOS / CITAS
        print("\n📅 CITAS Y TRABAJOS:")
        result = await db.execute(select(ServiceAppointment))
        jobs = result.scalars().all()
        for j in jobs:
            print(f"   - [ID: {j.id}] Estado: {j.status.value} | Tec: {j.technician_id or 'Pendiente'} | Cliente: {j.client_id}")
            print(f"     Desc: {(j.notes or '')[:50]}...")
        if not jobs: print("   (Vacío)")
        
        print("\n" + "="*50)
        print("                 FIN DEL REPORTE                    ")
        print("="*50)

if __name__ == "__main__":
    try:
        asyncio.run(inspectex())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Error: {e}")

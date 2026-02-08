import asyncio
import sys
import os
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from app.models.models import User, UserRole, Organization
from app.core.security import get_password_hash
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Fix para Windows Event Loop
if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# URL de la base de datos de Render
DATABASE_URL = "postgresql://boltzman_db_user:M8kjsyKFYGVY3bNRFyzRPFiQStaGURV1@dpg-d5ik0dh5pdvs73c3skg0-a.oregon-postgres.render.com/boltzman_db"

# Fix para asyncpg
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://") and "+asyncpg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(DATABASE_URL)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def create_jefe():
    admin_email = "jefe@jefe.com"
    admin_pass = "123456"
    admin_name = "Administrador Boltzman"

    print(f"\n--- 🛡️  REGISTRANDO ADMIN: {admin_email} 🛡️  ---")

    async with AsyncSessionLocal() as db:
        # 1. Verificar si ya existe
        result = await db.execute(select(User).where(User.email == admin_email))
        existing_user = result.scalars().first()
        
        if existing_user:
            print(f"🔧 Usuario {admin_email} ya existe. Actualizando rol y contraseña...")
            existing_user.role = UserRole.ADMIN
            existing_user.hashed_password = get_password_hash(admin_pass)
            await db.commit()
            print(f"✅ Usuario {admin_email} actualizado como ADMIN con contraseña '{admin_pass}'.")
            return

        # 2. Verificar/Crear Organización Madre (ID 1)
        result_org = await db.execute(select(Organization).where(Organization.id == 1))
        org = result_org.scalars().first()
        
        if not org:
            print("⚠️ Creando Organización ID 1...")
            new_org = Organization(id=1, name="Boltzman HQ", is_corporate=True)
            db.add(new_org)
            await db.flush()
            org_id = 1
        else:
            org_id = org.id

        # 3. Crear Admin
        hashed_pw = get_password_hash(admin_pass)
        new_admin = User(
            email=admin_email,
            hashed_password=hashed_pw,
            full_name=admin_name,
            role=UserRole.ADMIN,
            organization_id=org_id
        )
        
        try:
            db.add(new_admin)
            await db.commit()
            print(f"\n✅ ¡ÉXITO! Administrador '{admin_email}' creado correctamente con contraseña '{admin_pass}'.")
        except Exception as e:
            print(f"❌ Error al guardar en base de datos: {e}")

if __name__ == "__main__":
    asyncio.run(create_jefe())

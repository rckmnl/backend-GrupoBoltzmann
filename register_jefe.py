import asyncio
import sys
import os
from sqlalchemy import text
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from app.models.models import Base, User, UserRole, Organization
from app.core.security import get_password_hash
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Fix para Windows Event Loop
if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("❌ Error: No se encontró DATABASE_URL en el archivo .env")
    sys.exit(1)

# Fix para asyncpg
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://") and "+asyncpg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

async def super_setup():
    print(f"\n--- 🚀 INICIANDO SETUP PROFUNDO EN RENDER ---")
    
    # Motor con AUTOCOMMIT para migraciones de esquemas
    engine = create_async_engine(DATABASE_URL, isolation_level="AUTOCOMMIT")
    
    # 1. CREACIÓN DE TABLAS (IMPORTANTE SI LA BD ESTÁ VACÍA)
    print("\n[1/4] Creando tablas en la base de datos...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        print("   ✅ Tablas creadas (u omitidas si ya existían).")

    # 2. FIX DE ENUMS (MAYÚSCULAS)
    print("\n[2/4] Sincronizando estados (Enums)...")
    uppercase_labels = [
        "PENDING", "SCHEDULED", "IN_PROGRESS", "COMPLETED", 
        "PENDING_PAYMENT", "PAYMENT_VERIFYING", "PAID", "CANCELLED"
    ]
    
    async with engine.connect() as conn:
        for label in uppercase_labels:
            try:
                await conn.execution_options(isolation_level="AUTOCOMMIT").execute(
                    text(f"ALTER TYPE appointmentstatus ADD VALUE '{label}';")
                )
                print(f"   ✅ Agregado al Enum: {label}")
            except Exception:
                print(f"   ℹ️  {label} ya existe en el Enum.")

    # 3. CREACIÓN DE DATOS
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with AsyncSessionLocal() as db:
        print("\n[3/4] Asegurando Organización ID 1...")
        result_org = await db.execute(select(Organization).where(Organization.id == 1))
        org = result_org.scalars().first()
        
        if not org:
            org = Organization(id=1, name="Boltzman Services", is_corporate=True)
            db.add(org)
            await db.flush()
            print("   ✅ Organización Boltzman creada.")
        else:
            print("   ℹ️  Organización ya existe.")

        print("\n[4/4] Asegurando Usuario Administrador...")
        admin_email = "jefe@jefe.com"
        admin_pass = "123456"
        
        result = await db.execute(select(User).where(User.email == admin_email))
        admin = result.scalars().first()
        
        if not admin:
            hashed_pw = get_password_hash(admin_pass)
            admin = User(
                email=admin_email,
                hashed_password=hashed_pw,
                full_name="Administrador Boltzman",
                role=UserRole.ADMIN,
                organization_id=org.id
            )
            db.add(admin)
            print(f"   ✅ Usuario '{admin_email}' creado.")
        else:
            admin.role = UserRole.ADMIN
            admin.hashed_password = get_password_hash(admin_pass)
            print(f"   ✅ Usuario '{admin_email}' actualizado.")
        
        await db.commit()

    await engine.dispose()
    print("\n🎉 ¡SETUP FINALIZADO CON ÉXITO! 🎉")
    print("La base de datos está lista y el administrador registrado.")

if __name__ == "__main__":
    asyncio.run(super_setup())

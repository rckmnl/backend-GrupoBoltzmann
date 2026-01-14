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

# Fix para Windows Event Loop - IMPRESCINDIBLE en Windows + Async
if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# URL de la base de datos (Render o Local)
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("❌ Error: No se encontró DATABASE_URL en el archivo .env")
    sys.exit(1)

# Fix para asyncpg
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://") and "+asyncpg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(DATABASE_URL)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def create_admin():
    print("\n--- 🛡️  CREACIÓN DE ADMIN DE BOLTZMAN (Fixed) 🛡️  ---")
    email = input("Email del Admin: ").strip()
    
    if "@" not in email:
        print("❌ Email inválido.")
        return

    full_name = input("Nombre completo: ").strip()
    password = input("Contraseña (VISIBLE): ").strip()
    confirm_password = input("Confirmar contraseña (VISIBLE): ").strip()

    if password != confirm_password:
        print("❌ Las contraseñas no coinciden.")
        return

    async with AsyncSessionLocal() as db:
        # 1. Verificar si ya existe
        result = await db.execute(select(User).where(User.email == email))
        existing_user = result.scalars().first()
        
        if existing_user:
            print(f"❌ El usuario {email} ya existe (Rol: {existing_user.role}).")
            return

        # 2. Verificar/Crear Organización Madre (ID 1)
        result_org = await db.execute(select(Organization).where(Organization.id == 1))
        org = result_org.scalars().first()
        
        if not org:
            print("⚠️ No existe la Organización ID 1. Creándola como 'Boltzman HQ'...")
            new_org = Organization(id=1, name="Boltzman HQ", is_corporate=True)
            db.add(new_org)
            await db.flush()
            print("✅ Organización ID 1 creada.")
            org_id = 1
        else:
            org_id = org.id

        # 3. Crear Admin
        hashed_pw = get_password_hash(password)
        print(f"DEBUG: Contraseña '{password}' hasheada a: {hashed_pw[:10]}...")

        new_admin = User(
            email=email,
            hashed_password=hashed_pw,
            full_name=full_name,
            role=UserRole.ADMIN,
            organization_id=org_id
        )
        
        try:
            db.add(new_admin)
            await db.commit()
            await db.refresh(new_admin) # Forzamos la lectura inmediata
            
            print(f"\n✅ ¡ÉXITO! Administrador creado correctamente.")
            print(f"📧 Email: {new_admin.email}")
            print(f"🆔 ID BD: {new_admin.id}")
            print(f"🏢 Org ID: {new_admin.organization_id}")
            print(f"🔐 TEST LOGIN: Intenta iniciar sesión ahora.")

        except Exception as e:
            print(f"❌ Error al guardar en base de datos: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(create_admin())
    except KeyboardInterrupt:
        print("\nCancelado por el usuario.")
    except Exception as e:
        print(f"\n❌ Error inesperado: {e}")

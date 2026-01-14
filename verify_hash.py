import asyncio
import sys
import os
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from app.models.models import User
from app.core.security import verify_password, get_password_hash
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Fix para Windows Event Loop
if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# URL de la base de datos
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

async def check_user_pass():
    email = input("Email a verificar: ").strip()
    password_attempt = input("Contraseña a probar: ").strip()
    
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalars().first()
        
        if not user:
            print(f"❌ El usuario {email} NO existe en la base de datos.")
            return

        print(f"\n--- 🔍 DIAGNÓSTICO PARA {email} ---")
        print(f"ID: {user.id}")
        print(f"Hash guardado en BD: {user.hashed_password}")
        
        # Prueba de verificación
        is_valid = verify_password(password_attempt, user.hashed_password)
        
        if is_valid:
            print("✅ verify_password() devolvió TRUE. La contraseña es correcta localmente.")
        else:
            print("❌ verify_password() devolvió FALSE. No coinciden.")
            
            # Generar hash nuevo para comparar
            new_hash = get_password_hash(password_attempt)
            print(f"Hash generado aquí: {new_hash}")
            print("Diferencia: El hash de la BD podría usar una versión (salt) diferente.")

if __name__ == "__main__":
    try:
        asyncio.run(check_user_pass())
    except Exception as e:
        print(f"Error: {e}")

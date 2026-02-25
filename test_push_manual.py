import asyncio
import os
import requests
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from app.models.models import User
from dotenv import load_dotenv

load_dotenv()

# Fix para Windows Event Loop
if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("❌ Error: No se encontró DATABASE_URL en el archivo .env")
    exit(1)

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://") and "+asyncpg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(DATABASE_URL)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def send_test():
    async with AsyncSessionLocal() as db:
        # Intentamos con el usuario que vimos en logs
        email = "arcangel@gmail.com"
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalars().first()
        
        if not user or not user.push_token:
            result = await db.execute(select(User).where(User.push_token != None).limit(1))
            user = result.scalars().first()
            if not user:
                print("❌ No se encontró ningún usuario con token.")
                return

        print(f"🚀 Enviando prueba a: {user.email}")
        print(f"Token: {user.push_token}")

        expo_url = "https://exp.host/--/api/v2/push/send"
        payload = [{
            "to": user.push_token,
            "title": "🚨 PRUEBA DE BOLTZMAN",
            "body": "Si lees esto, las notificaciones están funcionando perfectamente.",
            "sound": "default",
            "data": {"type": "TEST"}
        }]

        response = requests.post(expo_url, json=payload)
        print(f"Respuesta de Expo: {response.status_code} - {response.text}")

if __name__ == "__main__":
    asyncio.run(send_test())

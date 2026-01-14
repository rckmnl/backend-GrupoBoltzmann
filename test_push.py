import asyncio
import os
import firebase_admin
from firebase_admin import credentials, messaging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# URL de la base de datos en Render
RENDER_DB_URL = "postgresql://boltzman_db_user:M8kjsyKFYGVY3bNRFyzRPFiQStaGURV1@dpg-d5ik0dh5pdvs73c3skg0-a.oregon-postgres.render.com/boltzman_db"

def get_async_url(url: str):
    if not url: return url
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://") and "+asyncpg" not in url:
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url

async_url = get_async_url(RENDER_DB_URL)
engine = create_async_engine(async_url)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

if not firebase_admin._apps:
    try:
        firebase_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
        if firebase_json:
            service_account_info = json.loads(firebase_json)
            cred = credentials.Certificate(service_account_info)
            firebase_admin.initialize_app(cred)
        elif os.path.exists("service-account.json"):
            cred = credentials.Certificate("service-account.json")
            firebase_admin.initialize_app(cred)
        else:
            print("❌ Error: No se encontraron credenciales de Firebase (ENV o Archivo).")
    except Exception as e:
        print(f"❌ Error inicializando Firebase: {e}")

async def test_push():
    from app.models.models import User
    
    email = input("Introduce el email del usuario para la prueba DIRECTA (FCM V1): ")
    
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalars().first()
        
        if not user:
            print(f"❌ Error: El usuario {email} no existe.")
            return
            
        if not user.push_token:
            print(f"⚠️ El usuario {email} no tiene un token registrado.")
            return
            
        token = user.push_token
        print(f"✅ Token encontrado: {token}")

        if "ExponentPushToken" in token:
            print("❌ ATENCIÓN: Este usuario tiene un token de EXPO antiguo.")
            return

        print("Enviando notificación DIRECTA vía FCM V1...")
        
        try:
            message = messaging.Message(
                notification=messaging.Notification(
                    title="🚀 Directo desde Firebase V1",
                    body="¡Funciona! Esta notificación saltó el proxy de Expo. 🔥",
                ),
                token=token,
            )
            response = messaging.send(message)
            print(f"🚀 Notificación enviada con éxito. ID: {response}")
        except Exception as e:
            print(f"❌ Error al enviar vía Firebase: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(test_push())
    except Exception as e:
        print(f"Ocurrió un error: {e}")

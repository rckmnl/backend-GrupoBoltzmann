from datetime import timedelta
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from fastapi.security import OAuth2PasswordRequestForm
import os
from pydantic import BaseModel
from datetime import datetime
from fastapi.staticfiles import StaticFiles

# Importaciones de tus propios módulos
from app.db.session import engine, get_db
from app.models.models import Base, User, Organization, UserRole
from app.schemas.user import UserCreate, UserOut, LoginRequest, Token
from app.core.security import get_password_hash, verify_password, create_access_token
from app.core.config import settings
from app.api.v1.endpoints import devices, users, organizations, maintenance, appointments
from fastapi.middleware.cors import CORSMiddleware

import firebase_admin
from firebase_admin import credentials
import json

# Initialize Firebase Admin
try:
    # Try to load from environment variable (for Render)
    firebase_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
    if firebase_json:
        # If it's a JSON string, load it
        try:
            service_account_info = json.loads(firebase_json)
            cred = credentials.Certificate(service_account_info)
            firebase_admin.initialize_app(cred)
            print("[INFO] Firebase Admin initialized using ENV VAR.")
        except Exception as e:
            print(f"[ERROR] Found ENV VAR but failed to parse: {e}")
    else:
        # Fallback to local file (for local development)
        if os.path.exists("service-account.json"):
            cred = credentials.Certificate("service-account.json")
            firebase_admin.initialize_app(cred)
            print("[INFO] Firebase Admin initialized using local file.")
        else:
            print("[WARNING] No Firebase credentials found (ENV or File). Notifications may fail.")
except Exception as e:
    print(f"[ERROR] Failed to initialize Firebase Admin: {e}")

app = FastAPI(title="Grupo Boltzman API")

# Asegurar que existan las carpetas para evitar errores al montar archivos estáticos
os.makedirs("static", exist_ok=True)
os.makedirs("static/uploads/devices", exist_ok=True)
os.makedirs("static/uploads/maintenance", exist_ok=True)
os.makedirs("static/uploads/payments", exist_ok=True)

# Configuración de CORS para permitir conexiones desde el iPhone
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. EVENTO DE INICIO
@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        # Asegura que las tablas existan
        await conn.run_sync(Base.metadata.create_all)

# 3. RUTAS DE INFORMACIÓN
@app.get("/")
async def read_root():
    return {"status": "success", "message": "Backend de Boltzman funcionando"}

# 4. RUTAS DE AUTENTICACIÓN (REGISTRO Y LOGIN)

@app.post("/register", response_model=Token)
async def register_user(
    user_data: UserCreate, 
    invite_token: str = None, 
    db: AsyncSession = Depends(get_db)
):
    # 1. Verificar si el email ya existe
    result = await db.execute(select(User).where(User.email == user_data.email))
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="El email ya está registrado")

    # 2. Restricción de Técnicos: Solo pueden registrarse con un token válido enviado por Admin
    # (Para simplificar, permitiremos que el token sea 'BOLTZMAN_TECH_2025' por ahora)
    if user_data.role == UserRole.TECHNICIAN:
        if invite_token != "BOLTZMAN_TECH_2025":
            raise HTTPException(
                status_code=403, 
                detail="El registro de técnicos requiere una invitación válida del administrador"
            )

    # 3. Crear Organización (si es cliente)
    # Los técnicos se asocian a la organización principal (asumimos ID 1)
    if user_data.role == UserRole.TECHNICIAN:
        org_id = 1 # ID de la empresa madre
    else:
        new_org = Organization(
            name=user_data.organization_name,
            is_corporate=user_data.is_corporate
        )
        db.add(new_org)
        await db.flush()
        org_id = new_org.id

    # 4. Crear Usuario
    new_user = User(
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        full_name=user_data.full_name,
        organization_id=org_id,
        phone_number=user_data.phone_number,
        role=user_data.role if user_data.role else (UserRole.CLIENT_CORPORATE if user_data.is_corporate else UserRole.CLIENT_RESIDENTIAL)
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    # Generar token automáticamente después del registro
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": new_user.email, "role": new_user.role.value}, 
        expires_delta=access_token_expires
    )

    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "user": new_user
    }

@app.post("/login", response_model=Token)
async def login(
    login_data: LoginRequest, 
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).where(User.email == login_data.email))
    user = result.scalars().first()
    
    if not user or not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=401, 
            detail="Email o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email, "role": user.role.value}, 
        expires_delta=access_token_expires
    )

    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "user": user
    }

# --- PASSWORD RECOVERY FLOW ---

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

@app.post("/auth/forgot-password")
async def forgot_password(
    data: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db)
):
    # 1. Verificar si existe el usuario
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalars().first()
    
    if not user:
        # Por seguridad, no decimos si el email existe o no, pero logueamos
        print(f"[SECURITY] Forgot password requested for unexisting email: {data.email}")
        return {"message": "Si el correo existe, recibirás un código de recuperación."}
    
    # 2. Generar Token (6 dígitos)
    import random
    token_str = f"{random.randint(100000, 999999)}"
    
    # 3. Guardar en DB
    from app.models.models import PasswordResetToken
    new_token = PasswordResetToken(
        user_id=user.id,
        token=token_str,
        expires_at=datetime.utcnow() + timedelta(minutes=15),
        used=False
    )
    db.add(new_token)
    await db.commit()
    
    # 4. Enviar Email
    smtp_email = os.getenv("SMTP_EMAIL", "noreply@boltzman.com")
    smtp_password = os.getenv("SMTP_PASSWORD")

    if smtp_email and smtp_password:
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            msg = MIMEMultipart("alternative")
            msg["Subject"] = "Recuperación de Contraseña - Boltzman"
            msg["From"] = smtp_email
            msg["To"] = data.email

            html = f"""
            <html>
                <body>
                    <div style="font-family: sans-serif; padding: 20px;">
                        <h2>Hola,</h2>
                        <p>Has solicitado restablecer tu contraseña en <strong>Boltzman</strong>.</p>
                        <p style="font-size: 24px; font-weight: bold; color: #4A90E2;">{token_str}</p>
                        <p>Este código expirará en 15 minutos por tu seguridad.</p>
                        <hr>
                        <p style="font-size: 12px; color: #888;">Si no solicitaste este cambio, puedes ignorar este correo de forma segura.</p>
                    </div>
                </body>
            </html>
            """
            msg.attach(MIMEText(html, "html"))

            # Gmail SMTP config
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(smtp_email, smtp_password)
                server.sendmail(smtp_email, data.email, msg.as_string())
            
            print(f"[INFO] Email enviado correctamente a {data.email} via Gmail SMTP")
                
        except Exception as e:
            print(f"[ERROR] Falló el envío de email SMTP: {e}")
            # Fallback a consola
            print(f"\n" + "="*50)
            print(f"📧 [MOCK EMAIL] To: {data.email}")
            print(f"📧 Body: Tu código de recuperación es: {token_str}")
            print("="*50 + "\n")
    else:
        # Mock si no hay config
        print(f"\n" + "="*50)
        print(f"📧 [MOCK EMAIL] To: {data.email}")
        print(f"📧 Subject: Recuperación de Contraseña - Boltzman")
        print(f"📧 Body: Tu código de recuperación es: {token_str}")
        print("="*50 + "\n")
    
    return {"message": "Si el correo existe, recibirás un código de recuperación."}

@app.post("/auth/reset-password")
async def reset_password(
    data: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db)
):
    from app.models.models import PasswordResetToken
    
    # 1. Buscar el token
    result = await db.execute(select(PasswordResetToken).where(PasswordResetToken.token == data.token))
    reset_token = result.scalars().first()
    
    if not reset_token:
        raise HTTPException(status_code=400, detail="Código inválido")
        
    if reset_token.used:
        raise HTTPException(status_code=400, detail="Este código ya fue usado")
        
    if reset_token.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="El código ha expirado")
        
    # 2. Buscar usuario asociado
    result_user = await db.execute(select(User).where(User.id == reset_token.user_id))
    user = result_user.scalars().first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
    # 3. Actualizar contraseña
    user.hashed_password = get_password_hash(data.new_password)
    
    # 4. Marcar token como usado
    reset_token.used = True
    
    await db.commit()
    
    return {"message": "Contraseña actualizada exitosamente"}

# 5. REGISTRO DE ROUTERS Y ARCHIVOS ESTÁTICOS
app.include_router(users.router, prefix="/users", tags=["Gestión de Usuarios"])
app.include_router(devices.router, prefix="/devices", tags=["Equipos AC"])
app.include_router(organizations.router, prefix="/organizations", tags=["Organizaciones"])
app.include_router(maintenance.router, prefix="/maintenance", tags=["Mantenimiento"])
app.include_router(appointments.router, prefix="/appointments", tags=["Appointments"])
app.include_router(appointments.router, prefix="/jobs", tags=["Trabajos"]) # Alias para mayor facilidad

# Servir la carpeta static para que las fotos sean accesibles vía URL
app.mount("/static", StaticFiles(directory="static"), name="static")
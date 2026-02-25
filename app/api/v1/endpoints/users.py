from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List, Optional
from pydantic import BaseModel

from app.db.session import get_db
from app.models.models import User, UserRole, Organization
from app.schemas.user import UserCreate, UserOut, UserUpdate, Token
from app.api.auth_utils import get_current_user
from app.core.security import get_password_hash, create_access_token
from app.core.config import settings
from datetime import datetime, timedelta

router = APIRouter()

# FUNCIÓN DE APOYO: Verifica si es Admin
def check_is_admin(user: User):
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos suficientes para realizar esta acción"
        )

@router.post("/technicians", response_model=UserOut)
async def create_technician(
    user_data: UserCreate, 
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Solo el ADMIN puede crear Técnicos."""
    check_is_admin(current_user)
    
    # 1. Verificar si el email ya existe
    result = await db.execute(select(User).where(User.email == user_data.email))
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="El email ya está registrado")

    # 2. BUSCAR O CREAR la organización para el técnico
    # Buscamos si ya existe una organización con ese nombre
    org_result = await db.execute(
        select(Organization).where(Organization.name == user_data.organization_name)
    )
    db_org = org_result.scalars().first()

    if not db_org:
        # Si no existe (ej. Boltzman Services), la creamos primero
        db_org = Organization(
            name=user_data.organization_name,
            is_corporate=True
        )
        db.add(db_org)
        await db.flush() # Esto genera el ID de la organización sin cerrar la transacción

    # 3. Crear el técnico vinculado al ID real de la organización
    new_user = User(
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        full_name=user_data.full_name,
        organization_id=db_org.id, # <--- Usamos el ID dinámico
        phone_number=user_data.phone_number,
        role=UserRole.TECHNICIAN
    )
    
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user

@router.get("/role/technician", response_model=List[UserOut])
async def list_technicians(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Lista solo los técnicos (Útil para asignar trabajos)."""
    check_is_admin(current_user)
    result = await db.execute(select(User).where(User.role == UserRole.TECHNICIAN))
    return result.scalars().all()

@router.get("/", response_model=List[UserOut])
async def list_all_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Lista todos los usuarios del sistema (Solo para Admins)."""
    check_is_admin(current_user)
    
    result = await db.execute(select(User))
    return result.scalars().all()

@router.patch("/me", response_model=UserOut)
async def update_my_profile(
    user_data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Permite que el usuario actual actualice su propio perfil."""
    # Solo permitir actualizar campos específicos si el usuario no es admin
    # (Evitar que se cambie el rol a sí mismo si ya es admin, o que un no-admin se asigne rol)
    data = user_data.model_dump(exclude_unset=True)
    
    # Si no es admin, eliminar campos sensibles
    if current_user.role != UserRole.ADMIN:
        data.pop("role", None)
        data.pop("email", None) # No permitimos cambio de email por ahora para evitar problemas de login
    
    for key, value in data.items():
        setattr(current_user, key, value)
        
    await db.commit()
    await db.refresh(current_user)
    return current_user

@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    check_is_admin(current_user) # Solo el jefe de Boltzman puede editar otros usuarios
    
    result = await db.execute(select(User).where(User.id == user_id))
    db_user = result.scalars().first()
    
    if not db_user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    data = user_data.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(db_user, key, value)
        
    await db.commit()
    await db.refresh(db_user)
    return db_user

class PushTokenUpdate(BaseModel):
    push_token: str

@router.post("/me/push-token")
async def register_push_token(
    data: PushTokenUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Registra el token de Expo para el usuario actual."""
    print(f"[DEBUG] Registering push token for user {current_user.email}: {data.push_token}")
    current_user.push_token = data.push_token
    await db.commit()
    return {"status": "success", "message": "Push token registrado"}

@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    check_is_admin(current_user)
    
    result = await db.execute(select(User).where(User.id == user_id))
    db_user = result.scalars().first()
    
    if not db_user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
    await db.delete(db_user)
    await db.commit()
    return None

import shutil
import os
from fastapi import File, UploadFile

@router.post("/me/photo")
async def upload_profile_photo(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Sube una foto de perfil para el usuario actual."""
    # 1. Crear directorio si no existe
    upload_dir = "static/uploads/profiles"
    os.makedirs(upload_dir, exist_ok=True)
    
    # 2. Generar nombre único
    import time
    timestamp = int(time.time())
    file_extension = file.filename.split('.')[-1]
    file_name = f"user_{current_user.id}_{timestamp}.{file_extension}"
    file_path = os.path.join(upload_dir, file_name)
    
    # 3. Guardar archivo
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # 4. Actualizar usuario
    relative_path = f"/static/uploads/profiles/{file_name}"
    current_user.photo_url = relative_path
    
    await db.commit()
    await db.refresh(current_user)
    
    return {"status": "success", "photo_url": relative_path}

# ========== SISTEMA DE INVITACIONES ==========
import secrets
from datetime import timedelta

class InvitationCreate(BaseModel):

    email: str

class InvitationResponse(BaseModel):
    invitation_link: str
    email: str
    expires_at: str

@router.post("/invite", response_model=InvitationResponse)
async def create_invitation(
    data: InvitationCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Admin genera una invitación para un técnico"""
    check_is_admin(current_user)
    
    from app.models.models import TechnicianInvitation
    from datetime import datetime
    
    # Generar token único
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(days=7)
    
    invitation = TechnicianInvitation(
        email=data.email,
        token=token,
        expires_at=expires_at,
        created_by_id=current_user.id
    )
    db.add(invitation)
    await db.commit()
    
    # Construir link HTTP que servirá como puente hacia la app
    host = request.headers.get("host", "boltzman-backend-94r7.onrender.com")
    protocol = "https" if "render" in host else "http"
    invitation_link = f"{protocol}://{host}/users/invite/link/{token}"
    
    return {
        "invitation_link": invitation_link,
        "email": data.email,
        "expires_at": expires_at.isoformat()
    }

@router.get("/invite/{token}")
async def validate_invitation(
    token: str,
    db: AsyncSession = Depends(get_db)
):
    """Valida si un token de invitación es válido"""
    from app.models.models import TechnicianInvitation
    from datetime import datetime
    
    result = await db.execute(
        select(TechnicianInvitation).where(TechnicianInvitation.token == token)
    )
    invitation = result.scalars().first()
    
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitación no encontrada")
    
    if invitation.used:
        raise HTTPException(status_code=400, detail="Esta invitación ya fue usada")
    
    if invitation.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Esta invitación ha expirado")
    
    return {"valid": True, "email": invitation.email}

@router.get("/invite/link/{token}", response_class=HTMLResponse)
async def bridge_invitation(token: str):
    """Interfaz puente para abrir la app desde un link HTTP (cliqueable en WhatsApp/Email)"""
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Boltzmann - Registro de Técnico</title>
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; text-align: center; padding: 60px 20px; background: #fafafa; color: #333; margin: 0; }}
            .container {{ display: flex; align-items: center; justify-content: center; min-height: 100vh; }}
            .card {{ background: white; padding: 40px; border-radius: 32px; box-shadow: 0 10px 30px rgba(0,0,0,0.05); max-width: 420px; width: 100%; border: 1px solid #f0f0f0; }}
            .logo {{ font-size: 42px; font-weight: bold; color: #EC7324; margin-bottom: 8px; }}
            .status-tag {{ background: #fff7ed; color: #ea580c; display: inline-block; padding: 6px 16px; border-radius: 100px; font-size: 13px; font-weight: 600; margin-bottom: 24px; border: 1px solid #ffedd5; }}
            h2 {{ margin-top: 0; font-size: 24px; color: #111; }}
            p {{ color: #666; line-height: 1.6; font-size: 15px; margin-bottom: 30px; }}
            .btn {{ display: block; background: #EC7324; color: white; padding: 20px 24px; border-radius: 18px; text-decoration: none; font-weight: 700; font-size: 17px; box-shadow: 0 8px 20px rgba(236, 115, 36, 0.25); transition: transform 0.2s; }}
            .btn:active {{ transform: scale(0.98); }}
            .footer {{ margin-top: 35px; font-size: 12px; color: #999; border-top: 1px solid #f0f0f0; padding-top: 20px; }}
            .download-link {{ color: #EC7324; text-decoration: none; font-weight: 600; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="card">
                <div class="logo">🔧 Boltzmann</div>
                <div class="status-tag">Invitación de Técnico</div>
                <h2>¡Casi listo!</h2>
                <p>Para completar tu registro, necesitas abrir este enlace en la aplicación oficial de Boltzmann.</p>
                
                <a href="boltzman://register-technician?token={token}" class="btn">ABRIR EN LA APLICACIÓN</a>
                
                <div class="footer">
                    <p>¿No tienes la app? <a href="#" class="download-link">Descarga el APK aquí</a></p>
                    <p style="font-size: 11px;">Nota: Solo compatible con Android. Este enlace expira pronto.</p>
                </div>
            </div>
        </div>
        <script>
            // Intentar redirección automática inmediata
            window.location.href = "boltzman://register-technician?token={token}";
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)



class TechnicianRegister(BaseModel):
    token: str
    full_name: str
    password: str
    phone_number: Optional[str] = None

@router.post("/register-technician", response_model=Token)
async def register_technician_with_invitation(
    data: TechnicianRegister,
    db: AsyncSession = Depends(get_db)
):
    """Registra un técnico usando un token de invitación válido"""
    from app.models.models import TechnicianInvitation
    from datetime import datetime
    
    # Validar token
    result = await db.execute(
        select(TechnicianInvitation).where(TechnicianInvitation.token == data.token)
    )
    invitation = result.scalars().first()
    
    if not invitation or invitation.used or invitation.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invitación inválida o expirada")
    
    # Verificar que el email no esté registrado
    email_check = await db.execute(select(User).where(User.email == invitation.email))
    if email_check.scalars().first():
        raise HTTPException(status_code=400, detail="Este email ya está registrado")
    
    # Crear el técnico
    new_technician = User(
        email=invitation.email,
        hashed_password=get_password_hash(data.password),
        full_name=data.full_name,
        organization_id=1,  # Organización principal de Boltzman
        phone_number=data.phone_number,
        role=UserRole.TECHNICIAN
    )
    db.add(new_technician)
    # Marcar invitación como usada
    invitation.used = True
    
    await db.commit()
    await db.refresh(new_technician)
    
    # Generar token automáticamente después del registro
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": new_technician.email, "role": new_technician.role.value}, 
        expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "user": new_technician
    }

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
from pydantic import BaseModel

from app.db.session import get_db
from app.models.models import User, UserRole, Organization
from app.schemas.user import UserCreate, UserOut, UserUpdate
from app.api.auth_utils import get_current_user
from app.core.security import get_password_hash

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
    
    # Construir link (el frontend lo mostrará al admin)
    base_url = "boltzman://register-technician"
    invitation_link = f"{base_url}?token={token}"
    
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

class TechnicianRegister(BaseModel):
    token: str
    full_name: str
    password: str

@router.post("/register-technician")
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
        role=UserRole.TECHNICIAN
    )
    db.add(new_technician)
    
    # Marcar invitación como usada
    invitation.used = True
    
    await db.commit()
    await db.refresh(new_technician)
    
    return {"status": "success", "message": "Técnico registrado correctamente", "user_id": new_technician.id}

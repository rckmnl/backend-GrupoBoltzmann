from pydantic import BaseModel, EmailStr
from typing import Optional
from app.models.models import UserRole

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    organization_name: str # Para crear la organización al registrarse
    is_corporate: bool = False
    phone_number: Optional[str] = None
    role: Optional[UserRole] = UserRole.CLIENT_RESIDENTIAL

class UserOut(BaseModel):
    id: int
    email: EmailStr
    full_name: Optional[str]
    phone_number: Optional[str] = None
    role: UserRole
    organization_id: Optional[int] = None
    push_token: Optional[str] = None
    photo_url: Optional[str] = None
    
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserOut # Cambiado de user_role: str para enviar todo el objeto

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[UserRole] = None # Solo el Admin enviará esto
    push_token: Optional[str] = None
    phone_number: Optional[str] = None
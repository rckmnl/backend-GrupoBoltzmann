from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, DateTime, Enum, Float, JSON
from sqlalchemy.orm import relationship, declarative_base
import enum
from datetime import datetime

Base = declarative_base()

class UserRole(enum.Enum):
    ADMIN = "admin"
    TECHNICIAN = "technician"
    CLIENT_CORPORATE = "client_corporate"
    CLIENT_RESIDENTIAL = "client_residential"

class Organization(Base):
    __tablename__ = "organizations"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    is_corporate = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    contact_email = Column(String, nullable=True) 
    
    users = relationship("User", back_populates="organization")
    devices = relationship("Device", back_populates="owner")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String)
    role = Column(Enum(UserRole), default=UserRole.CLIENT_RESIDENTIAL)
    organization_id = Column(Integer, ForeignKey("organizations.id"))
    push_token = Column(String, nullable=True) # Token para notificaciones push
    photo_url = Column(String, nullable=True) # --- NUEVO: Foto de perfil
    phone_number = Column(String, nullable=True) # --- NUEVO: Teléfono de contacto

    organization = relationship("Organization", back_populates="users")

class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    token = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)
    
    user = relationship("User")

class Device(Base):
    __tablename__ = "devices"
    id = Column(Integer, primary_key=True, index=True)
    device_type = Column(String)
    brand = Column(String)
    model = Column(String)
    serial_number = Column(String, unique=True, index=True)
    capacity = Column(String)
    location_details = Column(String) 
    latitude = Column(Float, nullable=True) # --- NUEVO: Ubicación GPS
    longitude = Column(Float, nullable=True) # --- NUEVO: Ubicación GPS
    qr_code = Column(String, unique=True)
    installation_date = Column(DateTime, default=datetime.utcnow)
    image_url = Column(String, nullable=True)
    
    organization_id = Column(Integer, ForeignKey("organizations.id"))
    owner = relationship("Organization", back_populates="devices")
    maintenance_history = relationship("MaintenanceLog", back_populates="device")

class MaintenanceLog(Base):
    __tablename__ = "maintenance_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"))
    service_date = Column(DateTime, default=datetime.utcnow)
    description = Column(String, nullable=False)
    technician_name = Column(String)
    # --- NUEVO CAMPO PARA LA FOTO ---
    photo_url = Column(String, nullable=True)  # MANTENER para compatibilidad
    photo_urls = Column(JSON, nullable=True)   # NUEVO: múltiples fotos
    
    client_signature_url = Column(String, nullable=True) # --- NUEVO: Firma del cliente
    
    # Relación con la cita que generó este log
    appointment_id = Column(Integer, ForeignKey("service_appointments.id"), nullable=True)

    device = relationship("Device", back_populates="maintenance_history")
    appointment = relationship("ServiceAppointment", back_populates="maintenance_logs")

class AppointmentStatus(enum.Enum):
    PENDING = "pending"      # El cliente la pidió, pero no ha sido confirmada
    SCHEDULED = "scheduled"  # Ya tiene técnico y hora confirmada
    IN_PROGRESS = "in_progress" # El técnico está trabajando
    COMPLETED = "completed"  # El servicio se realizó
    CANCELLED = "cancelled"

class ServiceAppointment(Base):
    __tablename__ = "service_appointments"
    
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"))
    client_id = Column(Integer, ForeignKey("users.id"))
    technician_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    requested_date = Column(DateTime, nullable=False) # Fecha que pide el cliente
    scheduled_date = Column(DateTime, nullable=True) # Fecha confirmada por Admin
    
    # --- NUEVO: Tiempos de Servicio ---
    start_travel_at = Column(DateTime, nullable=True)
    arrived_at = Column(DateTime, nullable=True)
    
    # --- NUEVO: Bitácora de Trabajo ---
    accepted_at = Column(DateTime, nullable=True)  # Cuando técnico acepta
    started_at = Column(DateTime, nullable=True)   # Cuando inicia trabajo
    completed_at = Column(DateTime, nullable=True) # Cuando finaliza trabajo
    
    service_type = Column(String) 
    priority = Column(String, default="medium") 
    status = Column(Enum(AppointmentStatus), default=AppointmentStatus.PENDING)
    
    notes = Column(String, nullable=True) # Notas del cliente
    admin_notes = Column(String, nullable=True) # Notas del administrador/despacho
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # --- NUEVO: Calificación del Servicio ---
    rating = Column(Integer, nullable=True) # 1 a 5 estrellas
    rating_comments = Column(String, nullable=True)

    # Relaciones
    device = relationship("Device")
    client = relationship("User", foreign_keys=[client_id])
    technician = relationship("User", foreign_keys=[technician_id])
    maintenance_logs = relationship("MaintenanceLog", back_populates="appointment")

class TechnicianInvitation(Base):
    """Invitaciones para registro de técnicos"""
    __tablename__ = "technician_invitations"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, nullable=False)
    token = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)
    created_by_id = Column(Integer, ForeignKey("users.id"))
    
    created_by = relationship("User")

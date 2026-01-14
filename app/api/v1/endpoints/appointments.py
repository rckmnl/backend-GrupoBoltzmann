from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.models.models import ServiceAppointment, User, AppointmentStatus, UserRole, Device
from app.api.auth_utils import get_current_user
from pydantic import BaseModel
from datetime import datetime
from sqlalchemy import select
from typing import Optional

router = APIRouter()

class AppointmentCreate(BaseModel):
    device_id: int
    requested_date: datetime
    service_type: str 
    priority: str = "medium"
    notes: str = None

@router.post("/")
async def create_appointment(
    data: AppointmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from app.models.models import Device
    res_device = await db.execute(select(Device).where(Device.id == data.device_id))
    device = res_device.scalars().first()
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")

    new_appo = ServiceAppointment(
        device_id=data.device_id,
        client_id=current_user.id,
        requested_date=data.requested_date,
        service_type=data.service_type,
        priority=data.priority,
        notes=data.notes,
        status=AppointmentStatus.PENDING
    )
    db.add(new_appo)
    await db.commit()

    # NOTIFICACIÓN A TÉCNICOS: Nuevo trabajo disponible
    try:
        from app.api.v1.notifications import send_push_notification
        # Buscar tokens de todos los técnicos
        tech_result = await db.execute(select(User.push_token).where(User.role == UserRole.TECHNICIAN).where(User.push_token != None))
        tech_tokens = tech_result.scalars().all()
        print(f"[DEBUG] Found {len(tech_tokens)} technician(s) with push tokens: {list(tech_tokens)}")
        if tech_tokens:
            await send_push_notification(
                tokens=list(tech_tokens),
                title="🛠️ Nuevo Trabajo Disponible",
                body=f"Se ha solicitado un {data.service_type} para el equipo {device.brand} {device.model}.",
                data={"appointment_id": new_appo.id, "type": "NEW_JOB"}
            )
        else:
            print("[DEBUG] No technician tokens found in DB.")
    except Exception as e:
        print(f"Error notifying technicians: {e}")

    return {"status": "success", "message": "Mantenimiento programado correctamente"}

@router.get("/my-appointments")
async def get_my_appointments(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from sqlalchemy.orm import selectinload
    query = select(ServiceAppointment).options(
        selectinload(ServiceAppointment.device).selectinload(Device.owner),
        selectinload(ServiceAppointment.technician)
    ).order_by(ServiceAppointment.requested_date.desc())
    
    if current_user.role != UserRole.ADMIN:
        query = query.where(ServiceAppointment.client_id == current_user.id)
        
    result = await db.execute(query)
    return result.scalars().all()

@router.get("/technician/jobs")
async def get_technician_jobs(
    filter_type: str = "my_jobs", # "pending" | "my_jobs"
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from sqlalchemy.orm import selectinload
    if current_user.role != UserRole.TECHNICIAN and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Solo técnicos pueden ver trabajos")
    
    query = select(ServiceAppointment).options(
        selectinload(ServiceAppointment.device).selectinload(Device.owner),
        selectinload(ServiceAppointment.technician)
    ).order_by(ServiceAppointment.requested_date.desc())

    if filter_type == "pending":
        # Mostrar solo pendientes y sin asignar
        query = query.where(ServiceAppointment.status == AppointmentStatus.PENDING).where(ServiceAppointment.technician_id == None)
    else:
        # "my_jobs" (default): Mostrar asignados a mí (Scheduled, InProgress, Completed)
        # O Jobs aceptados por mi usuario
        query = query.where(ServiceAppointment.technician_id == current_user.id)

    result = await db.execute(query)
    return result.scalars().all()

class TimerUpdate(BaseModel):
    action: str # "start_travel" | "arrive"

@router.patch("/{id}/timer")
async def update_job_timer(
    id: int,
    data: TimerUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != UserRole.TECHNICIAN:
        raise HTTPException(status_code=403, detail="Solo técnicos pueden actualizar tiempos")

    result = await db.execute(select(ServiceAppointment).where(ServiceAppointment.id == id))
    appo = result.scalars().first()

    if not appo:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
        
    if appo.technician_id != current_user.id:
        raise HTTPException(status_code=403, detail="No tienes asignado este trabajo")

    if data.action == "start_travel":
        if appo.start_travel_at:
             raise HTTPException(status_code=400, detail="El viaje ya fue iniciado")
        appo.start_travel_at = datetime.utcnow()
        
        # NOTIFICACIÓN AL CLIENTE: Técnico en camino
        try:
            from app.api.v1.notifications import send_push_notification
            # Necesitamos cargar el cliente para obtener su token
            from sqlalchemy.orm import selectinload
            # Recargar con cliente
            # (En una app real haríamos esto más eficiente cargándolo desde antes)
            result_client = await db.execute(select(User).where(User.id == appo.client_id))
            client_user = result_client.scalars().first()
            if client_user and client_user.push_token:
                await send_push_notification(
                    tokens=client_user.push_token,
                    title="🚚 Técnico en camino",
                    body=f"El técnico ya va hacia tu ubicación para el servicio de {appo.service_type}.",
                    data={"appointment_id": appo.id, "type": "TRAVEL_START"}
                )
        except Exception as e:
            print(f"Error notifying client (start_travel): {e}")

    elif data.action == "arrive":
        if not appo.start_travel_at:
             raise HTTPException(status_code=400, detail="Debes iniciar el viaje primero")
        if appo.arrived_at:
             raise HTTPException(status_code=400, detail="La llegada ya fue registrada")
        appo.arrived_at = datetime.utcnow()
    
    await db.commit()
    return {
        "status": "success", 
        "start_travel_at": appo.start_travel_at, 
        "arrived_at": appo.arrived_at
    }

@router.get("/{id}")
async def get_appointment_by_id(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(ServiceAppointment)
        .options(
            selectinload(ServiceAppointment.device).selectinload(Device.owner),
            selectinload(ServiceAppointment.technician),
            selectinload(ServiceAppointment.maintenance_logs)
        )
        .where(ServiceAppointment.id == id)
    )
    appo = result.scalars().first()
    if not appo:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    return appo

class AppointmentStatusUpdate(BaseModel):
    status: AppointmentStatus
    technician_id: Optional[int] = None
    scheduled_date: Optional[datetime] = None
    admin_notes: Optional[str] = None

@router.patch("/{id}/status")
async def update_appointment_status(
    id: int,
    data: AppointmentStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(ServiceAppointment).where(ServiceAppointment.id == id))
    appo = result.scalars().first()
    
    if not appo:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
        
    if current_user.role not in [UserRole.ADMIN, UserRole.TECHNICIAN]:
        raise HTTPException(status_code=403, detail="No autorizado")
        
    # Lógica de asignación
    if data.technician_id:
        appo.technician_id = data.technician_id
    
    if data.scheduled_date:
        # Normalizar a naive datetime para evitar errores con PostgreSQL TIMESTAMP WITHOUT TIME ZONE
        appo.scheduled_date = data.scheduled_date.replace(tzinfo=None) if data.scheduled_date.tzinfo else data.scheduled_date
        
    if data.admin_notes:
        appo.admin_notes = data.admin_notes

    appo.status = data.status
    
    # --- NUEVO: Guardar timestamps automáticamente según el estado ---
    if data.status == AppointmentStatus.SCHEDULED and not appo.accepted_at:
        appo.accepted_at = datetime.utcnow()  # Cuando se programa (técnico asignado)
    elif data.status == AppointmentStatus.IN_PROGRESS and not appo.started_at:
        appo.started_at = datetime.utcnow()  # Cuando inicia el trabajo
    elif data.status == AppointmentStatus.COMPLETED and not appo.completed_at:
        appo.completed_at = datetime.utcnow()  # Cuando finaliza
    
    await db.commit()

    # NOTIFICACIÓN AL CLIENTE: Trabajo completado (Invitar a calificar)
    if data.status == AppointmentStatus.COMPLETED:
        print(f"[DEBUG] Status changed to COMPLETED for appointment {appo.id}. Notifying client...")
        try:
            from app.api.v1.notifications import send_push_notification
            # Obtener el cliente
            res_client = await db.execute(select(User).where(User.id == appo.client_id))
            client_user = res_client.scalars().first()
            if client_user and client_user.push_token:
                print(f"[DEBUG] Found client token: {client_user.push_token}. Sending notification...")
                await send_push_notification(
                    tokens=client_user.push_token,
                    title="🎉 ¡Trabajo Finalizado!",
                    body=f"El servicio de {appo.service_type} ha concluido. Por favor, califica a tu técnico.",
                    data={"appointment_id": appo.id, "type": "JOB_COMPLETED"}
                )
            else:
                print(f"[DEBUG] Client {appo.client_id} has no push token registered.")
        except Exception as e:
            print(f"Error notifying client (completed): {e}")

    return {"status": "success", "new_status": data.status.value}

class AppointmentRating(BaseModel):
    rating: int # 1-5
    comments: Optional[str] = None

@router.post("/{id}/rate")
async def rate_service(
    id: int,
    data: AppointmentRating,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Permite al cliente calificar el servicio finalizado."""
    result = await db.execute(select(ServiceAppointment).where(ServiceAppointment.id == id))
    appo = result.scalars().first()
    
    if not appo:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    
    if appo.client_id != current_user.id:
        raise HTTPException(status_code=403, detail="Solo el cliente que solicitó el servicio puede calificar")
        
    if appo.status != AppointmentStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Solo se pueden calificar trabajos finalizados")

    if data.rating < 1 or data.rating > 5:
        raise HTTPException(status_code=400, detail="La calificación debe estar entre 1 y 5 estrellas")

    appo.rating = data.rating
    appo.rating_comments = data.comments
    
    await db.commit()
    return {"status": "success", "message": "¡Gracias por tu calificación!"}

@router.post("/{id}/accept")
async def accept_job(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Técnico acepta un trabajo pendiente (Cola FIFO)"""
    if current_user.role != UserRole.TECHNICIAN:
        raise HTTPException(status_code=403, detail="Solo técnicos pueden aceptar trabajos")
    
    result = await db.execute(select(ServiceAppointment).where(ServiceAppointment.id == id))
    appo = result.scalars().first()
    
    if not appo:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
    
    if appo.status != AppointmentStatus.PENDING:
        raise HTTPException(status_code=400, detail="Este trabajo ya fue asignado")
    
    if appo.technician_id is not None:
        raise HTTPException(status_code=400, detail="Este trabajo ya tiene técnico asignado")
    
    # Asignar al técnico actual
    appo.technician_id = current_user.id
    appo.status = AppointmentStatus.SCHEDULED
    
    await db.commit()

    # NOTIFICACIÓN AL CLIENTE: Trabajo aceptado
    try:
        from app.api.v1.notifications import send_push_notification
        result_client = await db.execute(select(User).where(User.id == appo.client_id))
        client_user = result_client.scalars().first()
        if client_user and client_user.push_token:
            await send_push_notification(
                tokens=client_user.push_token,
                title="✅ Cita Confirmada",
                body=f"El técnico {current_user.full_name} ha aceptado tu solicitud de servicio.",
                data={"appointment_id": appo.id, "type": "JOB_ACCEPTED"}
            )
    except Exception as e:
        print(f"Error notifying client (accept_job): {e}")

    return {"status": "success", "message": "Trabajo aceptado correctamente"}

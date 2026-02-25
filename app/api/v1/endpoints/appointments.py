from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form
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
    notes: Optional[str] = None
    total_cost: float = 0.0

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
        total_cost=data.total_cost,
        status=AppointmentStatus.PENDING
    )
    db.add(new_appo)
    await db.flush() # Para obtener el ID

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

@router.get("/finance/pending")
async def get_pending_payments(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Lista de trabajos que requieren pago o verificación (Solo Admins)."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="No autorizado")
    
    from sqlalchemy import cast, String, or_
    from sqlalchemy.orm import selectinload
    
    # Buscamos estados que indiquen que el trabajo terminó pero el pago está pendiente o en curso
    # Usamos comparación de strings para ser más robustos ante variaciones de mayúsculas/minúsculas en DB
    target_statuses = [
        "pending_payment", "PENDING_PAYMENT",
        "payment_verifying", "PAYMENT_VERIFYING",
        "completed", "COMPLETED" # Por si acaso quedaron algunos en completed sin transicionar
    ]
    
    query = select(ServiceAppointment).options(
        selectinload(ServiceAppointment.device).selectinload(Device.owner)
    ).where(
        or_(*(cast(ServiceAppointment.status, String).ilike(s) for s in target_statuses))
    ).order_by(ServiceAppointment.requested_date.desc())
    
    result = await db.execute(query)
    appointments = result.scalars().all()
    
    # Cargar relaciones manualmente si es necesario (para evitar errores de lazy loading)
    # Aunque async session suele requerir esto si no está en el query
    return appointments

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

    # --- PROTECCIÓN DE DATOS FINANCIEROS ---
    if current_user.role == UserRole.TECHNICIAN:
        # Usamos 0.0 en lugar de None para evitar que el frontend explote si hace .toFixed()
        appo.total_cost = 0.0
        appo.payment_reference = "PROTECTED"
        appo.payment_screenshot_url = None
        
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
    technician_changed = False
    if data.technician_id and appo.technician_id != data.technician_id:
        appo.technician_id = data.technician_id
        technician_changed = True
    
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
    elif data.status == AppointmentStatus.COMPLETED:
        if not appo.completed_at:
            appo.completed_at = datetime.utcnow()  # Cuando finaliza
        appo.status = AppointmentStatus.PENDING_PAYMENT # Asegurar que siempre pase a esperando pago
    
    await db.commit()

    # --- NOTIFICACIONES DE ASIGNACIÓN ---
    if technician_changed:
        from app.api.v1.notifications import send_push_notification
        # 1. Notificar al Técnico
        try:
            res_tech = await db.execute(select(User).where(User.id == appo.technician_id))
            tech_user = res_tech.scalars().first()
            if tech_user and tech_user.push_token:
                await send_push_notification(
                    tokens=tech_user.push_token,
                    title="🔧 Nuevo Servicio Asignado",
                    body=f"El administrador te ha asignado un nuevo servicio de {appo.service_type}.",
                    data={"appointment_id": appo.id, "type": "ASSIGNED_JOB"}
                )
        except Exception as e:
            print(f"Error notifying technician (assigned): {e}")

        # 2. Notificar al Cliente
        try:
            res_client = await db.execute(select(User).where(User.id == appo.client_id))
            client_user = res_client.scalars().first()
            if client_user and client_user.push_token:
                # Obtener nombre del técnico para personalizar el mensaje
                tech_name = tech_user.full_name if tech_user else "un técnico"
                await send_push_notification(
                    tokens=client_user.push_token,
                    title="✅ Técnico Asignado",
                    body=f"Se ha asignado a {tech_name} para tu servicio de {appo.service_type}.",
                    data={"appointment_id": appo.id, "type": "TECH_ASSIGNED"}
                )
        except Exception as e:
            print(f"Error notifying client (tech_assigned): {e}")

    # --- NOTIFICACIONES AL CLIENTE ---
    from app.api.v1.notifications import send_push_notification
    
    # 1. Técnico ya va en camino (IN_PROGRESS)
    if data.status == AppointmentStatus.IN_PROGRESS:
        try:
            res_client = await db.execute(select(User).where(User.id == appo.client_id))
            client_user = res_client.scalars().first()
            if client_user and client_user.push_token:
                await send_push_notification(
                    tokens=client_user.push_token,
                    title="⚡ Servicio Iniciado",
                    body=f"El técnico ha comenzado el trabajo de {appo.service_type} en tu equipo.",
                    data={"appointment_id": appo.id, "type": "JOB_STARTED"}
                )
        except Exception as e:
            print(f"Error notifying client (in_progress): {e}")

    # 2. Trabajo completado -> Notificar Pago
    elif data.status == AppointmentStatus.COMPLETED:
        print(f"[DEBUG] Status changed to COMPLETED/PENDING_PAYMENT for appointment {appo.id}. Notifying client...")
        try:
            res_client = await db.execute(select(User).where(User.id == appo.client_id))
            client_user = res_client.scalars().first()
            if client_user and client_user.push_token:
                await send_push_notification(
                    tokens=client_user.push_token,
                    title="🎉 ¡Trabajo Finalizado!",
                    body=f"El servicio de {appo.service_type} ha concluido. Por favor, procede con el pago de ${appo.total_cost}.",
                    data={"appointment_id": appo.id, "type": "PAYMENT_REQUIRED", "cost": appo.total_cost}
                )
        except Exception as e:
            print(f"Error notifying client (completed): {e}")

    # 3. Pago validado -> Notificar Calificación
    elif data.status == AppointmentStatus.PAID:
        try:
            res_client = await db.execute(select(User).where(User.id == appo.client_id))
            client_user = res_client.scalars().first()
            if client_user and client_user.push_token:
                await send_push_notification(
                    tokens=client_user.push_token,
                    title="✅ Pago Verificado",
                    body="Tu pago ha sido validado con éxito. Ya puedes calificar el servicio del técnico.",
                    data={"appointment_id": appo.id, "type": "PAYMENT_VERIFIED"}
                )
        except Exception as e:
            print(f"Error notifying client (paid): {e}")

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
        
    if appo.status != AppointmentStatus.PAID:
        raise HTTPException(status_code=400, detail="Solo se pueden calificar trabajos con pago verificado")

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
@router.post("/{id}/report-payment")
async def report_payment(
    id: int,
    payment_reference: str = Form(...),
    screenshot: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """El cliente reporta su pago subiendo un capture."""
    result = await db.execute(select(ServiceAppointment).where(ServiceAppointment.id == id))
    appo = result.scalars().first()
    
    if not appo:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    
    if appo.client_id != current_user.id:
        raise HTTPException(status_code=403, detail="No autorizado")

    # Guardar imagen
    upload_dir = "static/uploads/payments"
    import os, shutil
    os.makedirs(upload_dir, exist_ok=True)
    file_name = f"pay_{id}_{int(datetime.utcnow().timestamp())}_{screenshot.filename}"
    file_path = os.path.join(upload_dir, file_name)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(screenshot.file, buffer)
    
    appo.payment_reference = payment_reference
    appo.payment_screenshot_url = f"/static/uploads/payments/{file_name}"
    appo.status = AppointmentStatus.PAYMENT_VERIFYING
    
    await db.commit()

    # NOTIFICAR ADMINS
    try:
        from app.api.v1.notifications import send_push_notification
        admin_result = await db.execute(select(User.push_token).where(User.role == UserRole.ADMIN).where(User.push_token != None))
        admin_tokens = admin_result.scalars().all()
        if admin_tokens:
            await send_push_notification(
                tokens=list(admin_tokens),
                title="💰 Nuevo Pago Reportado",
                body=f"El cliente {current_user.full_name} reportó el pago por ${appo.total_cost}.",
                data={"appointment_id": id, "type": "PAYMENT_REPORTED"}
            )
    except Exception as e:
        print(f"Error notifying admins: {e}")

    return {"status": "success", "message": "Pago reportado correctamente. Esperando validación."}

@router.post("/{id}/verify-payment")
async def verify_payment(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Admin valida el pago."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Solo administradores pueden validar pagos")

    result = await db.execute(select(ServiceAppointment).where(ServiceAppointment.id == id))
    appo = result.scalars().first()
    
    if not appo:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    
    appo.status = AppointmentStatus.PAID
    await db.commit()

    # NOTIFICACIÓN AL CLIENTE: Pago validado -> Notificar Calificación
    try:
        from app.api.v1.notifications import send_push_notification
        res_client = await db.execute(select(User).where(User.id == appo.client_id))
        client_user = res_client.scalars().first()
        if client_user and client_user.push_token:
            await send_push_notification(
                tokens=client_user.push_token,
                title="✅ Pago Verificado",
                body="Tu pago ha sido validado con éxito. Ya puedes calificar el servicio del técnico.",
                data={"appointment_id": appo.id, "type": "PAYMENT_VERIFIED"}
            )
    except Exception as e:
        print(f"Error notifying client (verify_payment): {e}")
    
    return {"status": "success", "message": "Pago verificado correctamente"}

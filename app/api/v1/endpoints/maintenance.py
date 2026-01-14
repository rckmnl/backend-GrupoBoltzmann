from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.models.models import MaintenanceLog, User, UserRole
from app.api.auth_utils import get_current_user
from datetime import datetime
import os
import shutil

router = APIRouter()

import base64

from typing import List

@router.post("/")
async def create_maintenance_log(
    device_id: int = Form(...),
    description: str = Form(...),
    technician_name: str = Form(...),
    appointment_id: int = Form(None), # Nuevo campo opcional
    signature_base64: str = Form(None), # Nuevo: Firma en base64
    image: UploadFile = File(None),  # MANTENER: Para compatibilidad
    images: List[UploadFile] = File(None),  # NUEVO: Múltiples fotos
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role not in [UserRole.ADMIN, UserRole.TECHNICIAN]:
        raise HTTPException(status_code=403, detail="No autorizado")

    # --- Procesar fotos (compatibilidad con 1 o múltiples) ---
    photo_path = None
    photo_paths = []
    
    # Si viene 'image' (formato antiguo), procesarla
    if image:
        upload_dir = "static/uploads/maintenance"
        os.makedirs(upload_dir, exist_ok=True)
        timestamp = int(datetime.utcnow().timestamp())
        file_name = f"{device_id}_{timestamp}_{image.filename}"
        file_path = os.path.join(upload_dir, file_name)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
        photo_path = f"/static/uploads/maintenance/{file_name}"
        photo_paths.append(photo_path)
    
    # Si vienen 'images' (formato nuevo con múltiples fotos)
    if images:
        upload_dir = "static/uploads/maintenance"
        os.makedirs(upload_dir, exist_ok=True)
        for idx, img in enumerate(images):
            timestamp = int(datetime.utcnow().timestamp())
            file_name = f"{device_id}_{timestamp}_{idx}_{img.filename}"
            file_path = os.path.join(upload_dir, file_name)
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(img.file, buffer)
            img_path = f"/static/uploads/maintenance/{file_name}"
            photo_paths.append(img_path)
            # Si es la primera foto y no había 'image', usarla como photo_path principal
            if not photo_path and idx == 0:
                photo_path = img_path
    
    signature_path = None
    if signature_base64:
        try:
            # signature_base64 usually comes as "data:image/png;base64,....."
            # We need to strip the header if present
            header, encoded = signature_base64.split(",", 1) if "," in signature_base64 else (None, signature_base64)
            
            data = base64.b64decode(encoded)
            
            sig_dir = "static/uploads/signatures"
            os.makedirs(sig_dir, exist_ok=True)
            timestamp = int(datetime.utcnow().timestamp())
            sig_name = f"sig_{device_id}_{timestamp}.png"
            sig_path = os.path.join(sig_dir, sig_name)
            
            with open(sig_path, "wb") as f:
                f.write(data)
                
            signature_path = f"/static/uploads/signatures/{sig_name}"
        except Exception as e:
            print(f"Error saving signature: {e}")
            # Non-blocking, just log it. Or raise error? Let's log and continue for now.

    new_log = MaintenanceLog(
        device_id=device_id,
        description=description,
        technician_name=technician_name,
        photo_url=photo_path,  # MANTENER: Primera foto para compatibilidad
        photo_urls=photo_paths if photo_paths else None,  # NUEVO: Todas las fotos
        client_signature_url=signature_path,
        appointment_id=appointment_id,
        service_date=datetime.utcnow()
    )
    
    db.add(new_log)
    try:
        await db.commit()
        await db.refresh(new_log)
        return {"status": "success", "id": new_log.id, "photo_url": photo_path}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al guardar: {str(e)}")

@router.patch("/{log_id}")
async def update_maintenance_log(
    log_id: int,
    description: str = Form(None),
    technician_name: str = Form(None),
    status: str = Form(None), # Nuevo campo para cambiar estatus
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.models import ServiceAppointment, AppointmentStatus # Import necesario

    if current_user.role not in [UserRole.ADMIN, UserRole.TECHNICIAN]:
        raise HTTPException(status_code=403, detail="No autorizado")

    result = await db.execute(
        select(MaintenanceLog).options(selectinload(MaintenanceLog.device)).where(MaintenanceLog.id == log_id)
    )
    db_log = result.scalars().first()
    if not db_log:
        raise HTTPException(status_code=404, detail="Registro no encontrado")

    if current_user.role == UserRole.TECHNICIAN and db_log.device.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="No puedes editar registros de otras organizaciones")

    # Lógica de Cambio de Estatus (Revertir completado)
    if status and status != "completed" and db_log.appointment_id:
        # Buscar la cita original
        app_res = await db.execute(select(ServiceAppointment).where(ServiceAppointment.id == db_log.appointment_id))
        appointment = app_res.scalars().first()
        
        if appointment:
            # Revertir estado de la cita
            # Si el nuevo estado es válido en el enum, usarlo, si no, default a IN_PROGRESS
            try:
                new_status = AppointmentStatus(status)
            except ValueError:
                new_status = AppointmentStatus.IN_PROGRESS
                
            appointment.status = new_status
            appointment.admin_notes = (appointment.admin_notes or "") + f" [Reabierto desde Historial: {description or 'Sin cambio en desc'}]"
            
            # ELIMINAR EL LOG actual ya que deja de ser un historial "completado"
            await db.delete(db_log)
            await db.commit()
            return {"status": "success", "message": "Trabajo reabierto y log eliminado", "reopened": True}

    if description: db_log.description = description
    if technician_name: db_log.technician_name = technician_name

    await db.commit()
    return {"status": "success", "message": "Registro actualizado"}

@router.delete("/{log_id}")
async def delete_maintenance_log(
    log_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    if current_user.role not in [UserRole.ADMIN, UserRole.TECHNICIAN]:
        raise HTTPException(status_code=403, detail="No autorizado")

    result = await db.execute(
        select(MaintenanceLog).options(selectinload(MaintenanceLog.device)).where(MaintenanceLog.id == log_id)
    )
    db_log = result.scalars().first()
    if not db_log:
        raise HTTPException(status_code=404, detail="Registro no encontrado")

    if current_user.role == UserRole.TECHNICIAN and db_log.device.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="No puedes eliminar registros de otras organizaciones")

    await db.delete(db_log)
    await db.commit()
    return {"status": "success", "message": "Registro eliminado"}
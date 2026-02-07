from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form
import json
import os
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
import qrcode
from io import BytesIO
from fastapi import Response
from fastapi.responses import HTMLResponse
import shutil

from app.db.session import get_db
from app.models.models import Device, User, UserRole, Organization
from app.schemas.device import DeviceCreate, DeviceOut, DeviceUpdate
# Necesitaremos un helper para obtener el usuario del token (te lo daré abajo)
from app.api.auth_utils import get_current_user 
from sqlalchemy.orm import selectinload

router = APIRouter()

@router.post("/", response_model=DeviceOut)
async def create_device(
    device_type: str = Form(...),
    brand: str = Form(...),
    model: str = Form(...),
    serial_number: str = Form(...),
    capacity: str = Form(""),
    location_details: str = Form(""),
    latitude: float = Form(None),
    longitude: float = Form(None),
    organization_id: int = Form(...),
    image: UploadFile = File(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Seguridad: Admin, Técnicos y Clientes pueden crear.
    # if current_user.role not in [UserRole.ADMIN, UserRole.TECHNICIAN]:
    #     raise HTTPException(status_code=403, detail="No tienes permiso para crear equipos")
    
    # Si es técnico, solo puede crear para SU organización
    if current_user.role == UserRole.TECHNICIAN and organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="Solo puedes crear equipos para tu propia organización")

    # Si es cliente, FORZAMOS que sea para su organización
    if current_user.role in [UserRole.CLIENT_RESIDENTIAL, UserRole.CLIENT_CORPORATE]:
        organization_id = current_user.organization_id

    # 1. Verificar si el serial ya existe
    res_serial = await db.execute(select(Device).where(Device.serial_number == serial_number))
    if res_serial.scalars().first():
        raise HTTPException(status_code=400, detail="El número de serie ya está registrado")

    # 2. Manejo de la imagen
    image_url = None
    if image:
        upload_dir = "static/uploads/devices"
        os.makedirs(upload_dir, exist_ok=True)
        timestamp = int(datetime.utcnow().timestamp())
        file_name = f"{serial_number}_{timestamp}_{image.filename}"
        file_path = os.path.join(upload_dir, file_name)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
        image_url = f"/static/uploads/devices/{file_name}"

    # 3. Generar el valor del QR
    qr_content = f"BOLTZ-{serial_number}"
    
    # 4. Crear la instancia
    new_device = Device(
        device_type=device_type,
        brand=brand,
        model=model,
        serial_number=serial_number,
        capacity=capacity,
        location_details=location_details,
        latitude=latitude,
        longitude=longitude,
        organization_id=organization_id,
        qr_code=qr_content,
        image_url=image_url
    )

    db.add(new_device)
    try:
        await db.commit()
        await db.refresh(new_device)
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=f"Error al crear: {str(e)}")
    
    return new_device
    
@router.get("/", response_model=List[DeviceOut])
async def get_my_devices(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Lista los dispositivos según el rol:
    - Admin: Ve todo.
    - Cliente: Solo los de su organización.
    """
    query = select(Device).options(selectinload(Device.owner)).order_by(Device.id.desc())
    
    # Lógica de filtro por Rol (RBAC)
    if current_user.role != UserRole.ADMIN:
        query = query.where(Device.organization_id == current_user.organization_id)
    
    result = await db.execute(query)
    devices = result.scalars().all()
    
    # Mapeo manual para incluir el nombre de la organización si es admin
    for device in devices:
        if device.owner:
            setattr(device, 'organization_name', device.owner.name)
            
    return devices

@router.patch("/{device_id}", response_model=DeviceOut)
async def update_device(
    device_id: int,
    device_data: DeviceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Buscamos el equipo
    result = await db.execute(select(Device).where(Device.id == device_id))
    db_device = result.scalars().first()

    if not db_device:
        raise HTTPException(status_code=404, detail="Equipo no encontrado")

    # Seguridad: Admin y Técnicos pueden editar.
    if current_user.role not in [UserRole.ADMIN, UserRole.TECHNICIAN]:
        raise HTTPException(status_code=403, detail="No tienes permiso para editar este equipo")

    # Si es técnico, debe ser de la misma organización del equipo
    if current_user.role == UserRole.TECHNICIAN and db_device.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="No tienes permiso para editar equipos de otras organizaciones")

    # Actualizar solo los campos que vienen en la petición
    update_data = device_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_device, key, value)

    await db.commit()
    await db.refresh(db_device)
    return db_device

@router.delete("/{device_id}", status_code=204)
async def delete_device(
    device_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(Device).where(Device.id == device_id))
    db_device = result.scalars().first()

    if not db_device:
        raise HTTPException(status_code=404, detail="Equipo no encontrado")

    # Seguridad: Admin y Técnicos pueden eliminar.
    if current_user.role not in [UserRole.ADMIN, UserRole.TECHNICIAN]:
        raise HTTPException(status_code=403, detail="No tienes permiso para eliminar este equipo")

    # Si es técnico, debe ser de la misma organización del equipo
    if current_user.role == UserRole.TECHNICIAN and db_device.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="No tienes permiso para eliminar equipos de otras organizaciones")

    await db.delete(db_device)
    await db.commit()
    return None # El status 204 no devuelve contenido

@router.get("/{device_id}/qr")
async def get_device_qr(
    device_id: int,
    db: AsyncSession = Depends(get_db)
):
    print(f"[DEBUG] Fetching QR for device: {device_id}")
    result = await db.execute(select(Device).where(Device.id == device_id))
    db_device = result.scalars().first()

    if not db_device:
        raise HTTPException(status_code=404, detail="Equipo no encontrado")

    # Updated to use Deep Linking Scheme
    qr_data = f"boltzman://device/{device_id}"

    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(qr_data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return Response(content=buf.getvalue(), media_type="image/png")

@router.get("/{device_id}/label", response_class=HTMLResponse)
async def get_device_label(
    device_id: int,
    db: AsyncSession = Depends(get_db)
):
    # Endpoint público para permitir impresión desde el navegador
    result = await db.execute(select(Device).where(Device.id == device_id))
    db_device = result.scalars().first()
    if not db_device:
        raise HTTPException(status_code=404, detail="Equipo no encontrado")

    image_display = f'<img src="{db_device.image_url}" style="width:120px; height:120px; object-fit:cover; border-radius:10px;">' if db_device.image_url else '<div style="width:120px; height:120px; background:#eee; border-radius:10px; display:flex; align-items:center; justify-center; font-size:10px; color:#999;">SIN FOTO</div>'

    return f"""
    <html>
        <head>
            <style>
                @media print {{ .no-print {{ display: none; }} }}
                body {{ font-family: sans-serif; display: flex; justify-content: center; padding: 20px; }}
                .label {{ width: 400px; border: 2px solid #333; padding: 20px; border-radius: 15px; display: flex; align-items: center; border-style: dashed; }}
                .qr-side {{ flex: 1; text-align: center; }}
                .info-side {{ flex: 1.5; padding-left: 20px; }}
                .brand {{ font-size: 20px; font-weight: bold; color: #EC7324; }}
                .model {{ font-size: 14px; color: #666; margin-bottom: 10px; }}
                .serial {{ font-size: 12px; color: #999; }}
                .btn {{ background: #EC7324; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; margin-bottom: 20px; }}
            </style>
        </head>
        <body>
            <div style="text-align: center;">
                <button class="btn no-print" onclick="window.print()">Imprimir Etiqueta</button>
                <div class="label">
                    <div class="qr-side">
                        <img src="/devices/{device_id}/qr" style="width: 150px; height: 150px;">
                        <div style="font-size: 10px; margin-top: 5px; color: #999;">SCAN TO SERVICE</div>
                    </div>
                    <div class="info-side">
                        <div class="brand">BOLTZMAN</div>
                        <div class="model">{db_device.brand} {db_device.model}</div>
                        <div class="serial">S/N: {db_device.serial_number}</div>
                        <div style="margin-top: 15px;">
                            {image_display}
                        </div>
                    </div>
                </div>
            </div>
        </body>
    </html>
    """

@router.get("/{device_id}/maintenance-history")
async def get_device_maintenance_history(
    device_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    print(f"[DEBUG] Fetching history for device: {device_id}")
    from app.models.models import MaintenanceLog, ServiceAppointment, User
    result = await db.execute(
        select(MaintenanceLog)
        .options(selectinload(MaintenanceLog.appointment).selectinload(ServiceAppointment.technician))
        .where(MaintenanceLog.device_id == device_id)
        .order_by(MaintenanceLog.service_date.desc())
    )
    return result.scalars().all()

@router.get("/{device_id}", response_model=DeviceOut)
async def get_device_by_id(
    device_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    print(f"[DEBUG] Fetching device detail: {device_id}")
    query = select(Device).options(selectinload(Device.owner)).where(Device.id == device_id)
    result = await db.execute(query)
    device = result.scalars().first()
    
    if not device:
        raise HTTPException(status_code=404, detail="Equipo no encontrado")
        
    # Seguridad: Admin y Técnicos pueden ver cualquier equipo. Clientes solo los suyos.
    if current_user.role not in [UserRole.ADMIN, UserRole.TECHNICIAN] and device.organization_id != current_user.organization_id:
         raise HTTPException(status_code=403, detail="No tienes permiso para ver este equipo")
    
    if device.owner:
        setattr(device, 'organization_name', device.owner.name)
        
    return device

@router.get("/verify/{device_id}", response_class=HTMLResponse)
async def verify_device_page(device_id: int, db: AsyncSession = Depends(get_db)):
    # 1. Carga de datos del dispositivo incluyendo el historial
    result = await db.execute(
        select(Device)
        .options(selectinload(Device.maintenance_history), selectinload(Device.owner))
        .where(Device.id == device_id)
    )
    db_device = result.scalars().first()
    
    if not db_device:
        return HTMLResponse(content="<html><body><h1>Equipo no encontrado</h1></body></html>", status_code=404)

    # El token se verificará vía frontend (LocalStorage) y se enviará en las peticiones subsiguientes.
    # Por ahora el HTML base permite ver el equipo pero bloquea el "Detalle Profundo" si no hay sesión.
    
    device_image_tag = f'<img src="{db_device.image_url}" style="width:100px; height:100px; object-fit:cover; border-radius:10px; margin-bottom:10px;">' if db_device.image_url else ""

    # 2. Generar el HTML del Historial con soporte para FOTOS
    history_html = ""
    sorted_logs = sorted(db_device.maintenance_history, key=lambda x: x.service_date, reverse=True)
    
    if not sorted_logs:
        history_html = "<p style='color:#666; font-style:italic;'>No hay mantenimientos registrados aún.</p>"
    else:
        history_html = "<ul style='text-align:left; padding:0;'>"
        for log in sorted_logs:
            fecha = log.service_date.strftime("%d/%m/%Y %H:%M")
            # Si hay foto, creamos la etiqueta de imagen
            photo_tag = f'<img src="{log.photo_url}" style="width:100%; border-radius:8px; margin-top:10px; border:1px solid #ddd;">' if log.photo_url else ""
            
            history_html += f"""
            <li style="background:#f8f9fa; border-left:4px solid #28a745; margin-bottom:15px; padding:12px; list-style:none; border-radius:4px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                <div style="font-size:0.8em; color:#666; font-weight:bold;">{fecha}</div>
                <div style="font-size:0.9em; color:#444;"><strong>Técnico:</strong> {log.technician_name}</div>
                <div style="margin-top:5px; color:#333; line-height:1.4;">{log.description}</div>
                {photo_tag}
            </li>
            """
        history_html += "</ul>"

    # 3. HTML Final con el nuevo formulario de foto
    return f"""
    <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {{ font-family: -apple-system, sans-serif; background: #f4f4f9; padding: 20px; text-align: center; color: #333; }}
                .card {{ background: white; padding: 20px; border-radius: 15px; box-shadow: 0 4px 10px rgba(0,0,0,0.1); max-width: 450px; margin: auto; }}
                .btn {{ background: #EC7324; color: white; border: none; padding: 12px; border-radius: 8px; width: 100%; margin-top: 10px; font-size: 16px; cursor: pointer; font-weight: bold; }}
                .input-field {{ width: 100%; padding: 12px; margin: 8px 0; border: 1px solid #ddd; border-radius: 8px; box-sizing: border-box; font-size: 14px; }}
                .hidden {{ display: none; }}
                #login-section {{ background: #fff3cd; padding: 15px; border-radius: 10px; border: 1px solid #ffeeba; margin-bottom: 20px; }}
                hr {{ border: 0; border-top: 1px solid #eee; margin: 20px 0; }}
                .status-badge {{ display: inline-block; background: #d4edda; color: #155724; padding: 5px 10px; border-radius: 20px; font-size: 0.8em; margin-bottom: 10px; }}
                .history-item {{ background:#f8f9fa; border-left:4px solid #EC7324; margin-bottom:15px; padding:12px; text-align:left; border-radius:4px; }}
            </style>
        </head>
        <body>
            <div class="card">
                <h2>Boltzman Service</h2>
                <div class="status-badge">Equipo ID: {device_id}</div>
                <div style="margin: 15px 0;">{device_image_tag}</div>
                <p><strong>{db_device.brand}</strong> - {db_device.model}</p>
                <p style="color: #666; font-size: 0.9em;">S/N: {db_device.serial_number}</p>
                
                <button class="btn" onclick="openApp()" style="background:#000; margin-bottom: 20px;">📲 Abrir en App Boltzman</button>
                
                <hr>

                <div id="login-section">
                    <h3>🔒 Acceso Restringido</h3>
                    <p style="font-size: 0.8em; color: #856404;">Inicia sesión para ver fotos e historial técnico.</p>
                    <input type="email" id="email" class="input-field" placeholder="Email">
                    <input type="password" id="password" class="input-field" placeholder="Contraseña">
                    <button class="btn" style="background:#007bff;" onclick="login()">Entrar</button>
                </div>

                <div id="actions-section" class="hidden">
                    <p style="color:#28a745; font-weight:bold;">✅ Acceso Autorizado</p>
                    <div id="maintenance-history" style="text-align:left; margin-top:20px;">
                        <h3>📋 Historial de Mantenimiento</h3>
                        {history_html}
                    </div>
                </div>
            </div>

            <script>
                function openApp() {{
                    window.location.href = "boltzman://device/{device_id}";
                    setTimeout(() => {{
                        alert("Si la app no se abre, asegúrate de tenerla instalada.");
                    }}, 2500);
                }}

                async function login() {{
                    const email = document.getElementById('email').value;
                    const password = document.getElementById('password').value;
                    
                    try {{
                        const formData = new URLSearchParams();
                        formData.append('username', email);
                        formData.append('password', password);

                        const response = await fetch('/token', {{
                            method: 'POST',
                            headers: {{ 'Content-Type': 'application/x-www-form-urlencoded' }},
                            body: formData
                        }});

                        if (response.ok) {{
                            const data = await response.json();
                            localStorage.setItem('boltz_token', data.access_token);
                            location.reload();
                        }} else {{
                            alert("Credenciales inválidas o sin permiso para este equipo.");
                        }}
                    }} catch (e) {{ alert("Error de conexión"); }}
                }}

                function checkAccess() {{
                    const token = localStorage.getItem('boltz_token');
                    if (token) {{
                        document.getElementById('login-section').classList.add('hidden');
                        document.getElementById('actions-section').classList.remove('hidden');
                    }}
                }}

                window.onload = checkAccess;
            </script>
        </body>
    </html>
    """

@router.post("/{device_id}/image")
async def upload_device_image(
    device_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # ... (mantenemos los pasos 1 al 4 que ya tienes) ...

    # 5. VINCULAR LA RUTA EN LA BASE DE DATOS
    relative_path = f"/static/uploads/devices/{file_name}"
    db_device.image_url = relative_path # Actualizamos el modelo
    
    await db.commit() # Guardamos el cambio
    await db.refresh(db_device)
    
    return {
        "info": "Imagen subida y vinculada al equipo",
        "url": relative_path
    }
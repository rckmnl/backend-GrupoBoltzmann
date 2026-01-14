from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class DeviceCreate(BaseModel):
    device_type: str
    brand: str
    model: str
    serial_number: str
    capacity: str
    location_details: str 
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    organization_id: int

class DeviceOut(DeviceCreate):
    id: int
    qr_code: Optional[str]
    image_url: Optional[str] = None
    installation_date: Optional[datetime] = None
    organization_name: Optional[str] = None
    
    class Config:
        from_attributes = True

class DeviceUpdate(BaseModel):
    device_type: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    capacity: Optional[str] = None
    location_details: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
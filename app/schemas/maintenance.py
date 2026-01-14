from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class MaintenanceCreate(BaseModel):
    device_id: int
    description: str
    technician_name: str

class MaintenanceOut(MaintenanceCreate):
    id: int
    service_date: datetime

    class Config:
        from_attributes = True
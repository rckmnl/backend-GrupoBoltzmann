from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.models.models import Organization
from pydantic import BaseModel

router = APIRouter()

# Esquema rápido para la creación
class OrgCreate(BaseModel):
    name: str
    contact_email: str

@router.get("/")
async def get_organizations(db: AsyncSession = Depends(get_db)):
    from sqlalchemy.future import select
    result = await db.execute(select(Organization))
    return result.scalars().all()

@router.post("/")
async def create_organization(org_data: OrgCreate, db: AsyncSession = Depends(get_db)):
    new_org = Organization(name=org_data.name, contact_email=org_data.contact_email)
    db.add(new_org)
    await db.commit()
    await db.refresh(new_org)
    return new_org
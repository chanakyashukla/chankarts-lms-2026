from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from uuid import UUID
from app.database import get_db
from app.models.instrument import Instrument
from app.schemas.student import InstrumentCreate, InstrumentResponse
from app.core.roles import UserRole
from app.api.deps import require_role
from app.models.user import User

router = APIRouter()


@router.post("/", response_model=InstrumentResponse)
async def create_instrument(
    instrument_data: InstrumentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN]))
):
    # Check if instrument already exists
    result = await db.execute(
        select(Instrument).where(Instrument.name == instrument_data.name)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Instrument already exists"
        )
    
    db_instrument = Instrument(**instrument_data.model_dump())
    db.add(db_instrument)
    await db.flush()
    
    return db_instrument


@router.get("/", response_model=List[InstrumentResponse])
async def list_instruments(
    instrument_type: str = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    query = select(Instrument).where(Instrument.is_active == True)
    
    if instrument_type:
        query = query.where(Instrument.instrument_type == instrument_type)
    
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    instruments = result.scalars().all()
    return instruments


@router.get("/{instrument_id}", response_model=InstrumentResponse)
async def get_instrument(
    instrument_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Instrument).where(Instrument.id == instrument_id)
    )
    instrument = result.scalar_one_or_none()
    
    if not instrument:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Instrument not found"
        )
    
    return instrument


@router.put("/{instrument_id}", response_model=InstrumentResponse)
async def update_instrument(
    instrument_id: UUID,
    instrument_data: InstrumentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN]))
):
    result = await db.execute(
        select(Instrument).where(Instrument.id == instrument_id)
    )
    instrument = result.scalar_one_or_none()
    
    if not instrument:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Instrument not found"
        )
    
    update_data = instrument_data.model_dump()
    for field, value in update_data.items():
        setattr(instrument, field, value)
    
    await db.flush()
    await db.refresh(instrument)
    
    return instrument


@router.delete("/{instrument_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_instrument(
    instrument_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN]))
):
    result = await db.execute(
        select(Instrument).where(Instrument.id == instrument_id)
    )
    instrument = result.scalar_one_or_none()
    
    if not instrument:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Instrument not found"
        )
    
    # Soft delete - set is_active to False
    instrument.is_active = False
    await db.flush()

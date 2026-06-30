"""
Master Data CRUD endpoints.
Provides Brand, Dosage, Mode of Shipment, and Therapeutic Category management.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_active_user
from src.domain.entities.user import User
from src.infrastructure.database.session import get_db_session
from src.infrastructure.database.models.masters.brand_model import BrandMasterModel
from src.infrastructure.database.models.masters.dosage_model import DosageMasterModel
from src.infrastructure.database.models.masters.mode_of_shipment_model import (
    ModeOfShipmentMasterModel,
)
from src.infrastructure.database.models.masters.therapeutic_category_model import (
    TherapeuticCategoryMasterModel,
)
from src.api.v1.endpoints.masters.schemas import (
    BrandCreate,
    BrandUpdate,
    BrandResponse,
    DosageCreate,
    DosageUpdate,
    DosageResponse,
    ModeOfShipmentCreate,
    ModeOfShipmentUpdate,
    ModeOfShipmentResponse,
    TherapeuticCategoryCreate,
    TherapeuticCategoryUpdate,
    TherapeuticCategoryResponse,
)

router = APIRouter(prefix="/masters", tags=["Master Data"])


# ============================================================
# BRAND MASTER — CRUD
# ============================================================


@router.get("/brands", response_model=list[BrandResponse])
async def list_brands(
    include_inactive: bool = False,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
) -> list[BrandResponse]:
    """List all brands, optionally including inactive ones."""
    query = select(BrandMasterModel).order_by(BrandMasterModel.brand_name)
    if not include_inactive:
        query = query.where(BrandMasterModel.is_active == True)  # noqa: E712
    result = await session.execute(query)
    return [BrandResponse.model_validate(r) for r in result.scalars().all()]


@router.post("/brands", response_model=BrandResponse, status_code=status.HTTP_201_CREATED)
async def create_brand(
    request: BrandCreate,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
) -> BrandResponse:
    """Create a new brand."""
    existing = await session.execute(
        select(BrandMasterModel).where(
            BrandMasterModel.brand_name.ilike(request.brand_name)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Brand already exists.")
    record = BrandMasterModel(
        brand_name=request.brand_name,
        is_active=True,
        created_by=current_user.username,
        modified_by=current_user.username,
    )
    session.add(record)
    await session.flush()
    return BrandResponse.model_validate(record)


@router.put("/brands/{rid}", response_model=BrandResponse)
async def update_brand(
    rid: UUID,
    request: BrandUpdate,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
) -> BrandResponse:
    """Update an existing brand."""
    result = await session.execute(
        select(BrandMasterModel).where(BrandMasterModel.id == rid)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Not found")
    if request.brand_name is not None and request.brand_name != record.brand_name:
        dup = await session.execute(
            select(BrandMasterModel).where(
                BrandMasterModel.brand_name.ilike(request.brand_name),
                BrandMasterModel.id != rid,
            )
        )
        if dup.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Brand already exists.")
        record.brand_name = request.brand_name
    if request.is_active is not None:
        record.is_active = request.is_active
    record.modified_by = current_user.username
    await session.flush()
    return BrandResponse.model_validate(record)


@router.delete("/brands/{rid}", status_code=200)
async def delete_brand(
    rid: UUID,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """Soft-delete (deactivate) a brand."""
    result = await session.execute(
        select(BrandMasterModel).where(BrandMasterModel.id == rid)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Not found")
    record.is_active = False
    record.modified_by = current_user.username
    await session.flush()
    return {"message": "Brand deactivated successfully"}


# ============================================================
# DOSAGE MASTER — CRUD
# ============================================================


@router.get("/dosages", response_model=list[DosageResponse])
async def list_dosages(
    include_inactive: bool = False,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
) -> list[DosageResponse]:
    """List all dosages, optionally including inactive ones."""
    query = select(DosageMasterModel).order_by(DosageMasterModel.dosage)
    if not include_inactive:
        query = query.where(DosageMasterModel.is_active == True)  # noqa: E712
    result = await session.execute(query)
    return [DosageResponse.model_validate(r) for r in result.scalars().all()]


@router.post("/dosages", response_model=DosageResponse, status_code=status.HTTP_201_CREATED)
async def create_dosage(
    request: DosageCreate,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
) -> DosageResponse:
    """Create a new dosage."""
    existing = await session.execute(
        select(DosageMasterModel).where(
            DosageMasterModel.dosage.ilike(request.dosage)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Dosage already exists.")
    record = DosageMasterModel(
        dosage=request.dosage,
        is_active=True,
        created_by=current_user.username,
        modified_by=current_user.username,
    )
    session.add(record)
    await session.flush()
    return DosageResponse.model_validate(record)


@router.put("/dosages/{rid}", response_model=DosageResponse)
async def update_dosage(
    rid: UUID,
    request: DosageUpdate,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
) -> DosageResponse:
    """Update an existing dosage."""
    result = await session.execute(
        select(DosageMasterModel).where(DosageMasterModel.id == rid)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Not found")
    if request.dosage is not None and request.dosage != record.dosage:
        dup = await session.execute(
            select(DosageMasterModel).where(
                DosageMasterModel.dosage.ilike(request.dosage),
                DosageMasterModel.id != rid,
            )
        )
        if dup.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Dosage already exists.")
        record.dosage = request.dosage
    if request.is_active is not None:
        record.is_active = request.is_active
    record.modified_by = current_user.username
    await session.flush()
    return DosageResponse.model_validate(record)


@router.delete("/dosages/{rid}", status_code=200)
async def delete_dosage(
    rid: UUID,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """Soft-delete (deactivate) a dosage."""
    result = await session.execute(
        select(DosageMasterModel).where(DosageMasterModel.id == rid)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Not found")
    record.is_active = False
    record.modified_by = current_user.username
    await session.flush()
    return {"message": "Dosage deactivated successfully"}


# ============================================================
# MODE OF SHIPMENT MASTER — CRUD
# ============================================================


@router.get("/modes-of-shipment", response_model=list[ModeOfShipmentResponse])
async def list_modes_of_shipment(
    include_inactive: bool = False,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
) -> list[ModeOfShipmentResponse]:
    """List all modes of shipment, optionally including inactive ones."""
    query = select(ModeOfShipmentMasterModel).order_by(
        ModeOfShipmentMasterModel.mode_name
    )
    if not include_inactive:
        query = query.where(ModeOfShipmentMasterModel.is_active == True)  # noqa: E712
    result = await session.execute(query)
    return [ModeOfShipmentResponse.model_validate(r) for r in result.scalars().all()]


@router.post(
    "/modes-of-shipment",
    response_model=ModeOfShipmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_mode_of_shipment(
    request: ModeOfShipmentCreate,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
) -> ModeOfShipmentResponse:
    """Create a new mode of shipment."""
    existing = await session.execute(
        select(ModeOfShipmentMasterModel).where(
            ModeOfShipmentMasterModel.mode_name.ilike(request.mode_name)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Mode of Shipment already exists.")
    record = ModeOfShipmentMasterModel(
        mode_name=request.mode_name,
        is_active=True,
        created_by=current_user.username,
        modified_by=current_user.username,
    )
    session.add(record)
    await session.flush()
    return ModeOfShipmentResponse.model_validate(record)


@router.put("/modes-of-shipment/{rid}", response_model=ModeOfShipmentResponse)
async def update_mode_of_shipment(
    rid: UUID,
    request: ModeOfShipmentUpdate,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
) -> ModeOfShipmentResponse:
    """Update an existing mode of shipment."""
    result = await session.execute(
        select(ModeOfShipmentMasterModel).where(ModeOfShipmentMasterModel.id == rid)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Not found")
    if request.mode_name is not None and request.mode_name != record.mode_name:
        dup = await session.execute(
            select(ModeOfShipmentMasterModel).where(
                ModeOfShipmentMasterModel.mode_name.ilike(request.mode_name),
                ModeOfShipmentMasterModel.id != rid,
            )
        )
        if dup.scalar_one_or_none():
            raise HTTPException(
                status_code=400, detail="Mode of Shipment already exists."
            )
        record.mode_name = request.mode_name
    if request.is_active is not None:
        record.is_active = request.is_active
    record.modified_by = current_user.username
    await session.flush()
    return ModeOfShipmentResponse.model_validate(record)


@router.delete("/modes-of-shipment/{rid}", status_code=200)
async def delete_mode_of_shipment(
    rid: UUID,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """Soft-delete (deactivate) a mode of shipment."""
    result = await session.execute(
        select(ModeOfShipmentMasterModel).where(ModeOfShipmentMasterModel.id == rid)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Not found")
    record.is_active = False
    record.modified_by = current_user.username
    await session.flush()
    return {"message": "Mode of Shipment deactivated successfully"}


# ============================================================
# THERAPEUTIC CATEGORY MASTER — CRUD
# ============================================================


@router.get("/therapeutic-categories", response_model=list[TherapeuticCategoryResponse])
async def list_therapeutic_categories(
    include_inactive: bool = False,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
) -> list[TherapeuticCategoryResponse]:
    """List all therapeutic categories, optionally including inactive ones."""
    query = select(TherapeuticCategoryMasterModel).order_by(
        TherapeuticCategoryMasterModel.therapeutic_category_name
    )
    if not include_inactive:
        query = query.where(
            TherapeuticCategoryMasterModel.is_active == True  # noqa: E712
        )
    result = await session.execute(query)
    return [
        TherapeuticCategoryResponse.model_validate(r) for r in result.scalars().all()
    ]


@router.post(
    "/therapeutic-categories",
    response_model=TherapeuticCategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_therapeutic_category(
    request: TherapeuticCategoryCreate,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
) -> TherapeuticCategoryResponse:
    """Create a new therapeutic category."""
    existing = await session.execute(
        select(TherapeuticCategoryMasterModel).where(
            TherapeuticCategoryMasterModel.therapeutic_category_name.ilike(
                request.therapeutic_category_name
            )
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400, detail="Therapeutic Category already exists."
        )
    record = TherapeuticCategoryMasterModel(
        therapeutic_category_name=request.therapeutic_category_name,
        is_active=True,
        created_by=current_user.username,
        modified_by=current_user.username,
    )
    session.add(record)
    await session.flush()
    return TherapeuticCategoryResponse.model_validate(record)


@router.put(
    "/therapeutic-categories/{rid}", response_model=TherapeuticCategoryResponse
)
async def update_therapeutic_category(
    rid: UUID,
    request: TherapeuticCategoryUpdate,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
) -> TherapeuticCategoryResponse:
    """Update an existing therapeutic category."""
    result = await session.execute(
        select(TherapeuticCategoryMasterModel).where(
            TherapeuticCategoryMasterModel.id == rid
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Not found")
    if (
        request.therapeutic_category_name is not None
        and request.therapeutic_category_name != record.therapeutic_category_name
    ):
        dup = await session.execute(
            select(TherapeuticCategoryMasterModel).where(
                TherapeuticCategoryMasterModel.therapeutic_category_name.ilike(
                    request.therapeutic_category_name
                ),
                TherapeuticCategoryMasterModel.id != rid,
            )
        )
        if dup.scalar_one_or_none():
            raise HTTPException(
                status_code=400, detail="Therapeutic Category already exists."
            )
        record.therapeutic_category_name = request.therapeutic_category_name
    if request.is_active is not None:
        record.is_active = request.is_active
    record.modified_by = current_user.username
    await session.flush()
    return TherapeuticCategoryResponse.model_validate(record)


@router.delete("/therapeutic-categories/{rid}", status_code=200)
async def delete_therapeutic_category(
    rid: UUID,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """Soft-delete (deactivate) a therapeutic category."""
    result = await session.execute(
        select(TherapeuticCategoryMasterModel).where(
            TherapeuticCategoryMasterModel.id == rid
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Not found")
    record.is_active = False
    record.modified_by = current_user.username
    await session.flush()
    return {"message": "Therapeutic Category deactivated successfully"}

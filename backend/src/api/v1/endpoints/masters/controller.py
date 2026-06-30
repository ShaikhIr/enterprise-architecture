"""
Master Data API Controller — CRUD for Product Type, Pack Style, Type of Pallet.

Follows the same pattern as O2C: soft-delete, duplicate validation (case-insensitive),
include_inactive query parameter, and Excel import for pallets.
"""

import io
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select, text as _text
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_active_user
from src.domain.entities.user import User
from src.infrastructure.database.session import get_db_session
from src.infrastructure.database.models.masters.product_type_model import ProductTypeMasterModel
from src.infrastructure.database.models.masters.pack_size_model import PackStyleMasterModel
from src.infrastructure.database.models.masters.type_of_pallet_model import TypeOfPalletMasterModel
from src.api.v1.endpoints.masters.schemas import (
    ProductTypeCreateRequest,
    ProductTypeUpdateRequest,
    ProductTypeResponse,
    PackStyleCreateRequest,
    PackStyleUpdateRequest,
    PackStyleResponse,
    PalletCreateRequest,
    PalletUpdateRequest,
    PalletResponse,
)

router = APIRouter(prefix="/masters", tags=["Master Data"])


# ============================================================
# PRODUCT TYPE MASTER — CRUD
# ============================================================

@router.get("/product-types", response_model=list[ProductTypeResponse])
async def list_product_types(
    include_inactive: bool = False,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
):
    """List product types. By default only active records are returned."""
    query = select(ProductTypeMasterModel).order_by(ProductTypeMasterModel.product_type_name)
    if not include_inactive:
        query = query.where(ProductTypeMasterModel.is_active == True)  # noqa: E712
    result = await session.execute(query)
    return [ProductTypeResponse.model_validate(r) for r in result.scalars().all()]


@router.post("/product-types", response_model=ProductTypeResponse, status_code=status.HTTP_201_CREATED)
async def create_product_type(
    request: ProductTypeCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
):
    """Create a new product type. Duplicate name is not allowed."""
    existing = await session.execute(
        select(ProductTypeMasterModel).where(
            ProductTypeMasterModel.product_type_name.ilike(request.product_type_name)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Product Type already exists.",
        )
    record = ProductTypeMasterModel(
        product_type_name=request.product_type_name,
        is_active=True,
        created_by=current_user.username,
        modified_by=current_user.username,
    )
    session.add(record)
    await session.flush()
    await session.refresh(record)
    return ProductTypeResponse.model_validate(record)


@router.put("/product-types/{record_id}", response_model=ProductTypeResponse)
async def update_product_type(
    record_id: UUID,
    request: ProductTypeUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
):
    """Update a product type."""
    result = await session.execute(
        select(ProductTypeMasterModel).where(ProductTypeMasterModel.id == str(record_id))
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product Type not found")

    if request.product_type_name is not None and request.product_type_name != record.product_type_name:
        dup = await session.execute(
            select(ProductTypeMasterModel).where(
                ProductTypeMasterModel.product_type_name.ilike(request.product_type_name),
                ProductTypeMasterModel.id != str(record_id),
            )
        )
        if dup.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Product Type already exists.",
            )
        record.product_type_name = request.product_type_name

    if request.is_active is not None:
        record.is_active = request.is_active

    record.modified_by = current_user.username
    await session.flush()
    await session.refresh(record)
    return ProductTypeResponse.model_validate(record)


@router.delete("/product-types/{record_id}", status_code=status.HTTP_200_OK)
async def delete_product_type(
    record_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
):
    """Soft-delete a product type (sets is_active = false)."""
    result = await session.execute(
        select(ProductTypeMasterModel).where(ProductTypeMasterModel.id == str(record_id))
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product Type not found")

    record.is_active = False
    record.modified_by = current_user.username
    await session.flush()
    return {"message": "Product Type deactivated successfully"}


# ============================================================
# PACK STYLE MASTER — CRUD
# ============================================================

@router.get("/pack-styles", response_model=list[PackStyleResponse])
async def list_pack_styles(
    include_inactive: bool = False,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
):
    """List pack styles. By default only active records are returned."""
    query = select(PackStyleMasterModel).order_by(PackStyleMasterModel.pack_style)
    if not include_inactive:
        query = query.where(PackStyleMasterModel.is_active == True)  # noqa: E712
    result = await session.execute(query)
    return [PackStyleResponse.model_validate(r) for r in result.scalars().all()]


@router.post("/pack-styles", response_model=PackStyleResponse, status_code=status.HTTP_201_CREATED)
async def create_pack_style(
    request: PackStyleCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
):
    """Create a new pack style. Duplicate name is not allowed."""
    existing = await session.execute(
        select(PackStyleMasterModel).where(
            PackStyleMasterModel.pack_style.ilike(request.pack_style)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pack Style already exists.",
        )
    record = PackStyleMasterModel(
        pack_style=request.pack_style,
        is_active=True,
        created_by=current_user.username,
        modified_by=current_user.username,
    )
    session.add(record)
    await session.flush()
    await session.refresh(record)
    return PackStyleResponse.model_validate(record)


@router.put("/pack-styles/{record_id}", response_model=PackStyleResponse)
async def update_pack_style(
    record_id: UUID,
    request: PackStyleUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
):
    """Update a pack style."""
    result = await session.execute(
        select(PackStyleMasterModel).where(PackStyleMasterModel.id == str(record_id))
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pack Style not found")

    if request.pack_style is not None and request.pack_style != record.pack_style:
        dup = await session.execute(
            select(PackStyleMasterModel).where(
                PackStyleMasterModel.pack_style.ilike(request.pack_style),
                PackStyleMasterModel.id != str(record_id),
            )
        )
        if dup.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Pack Style already exists.",
            )
        record.pack_style = request.pack_style

    if request.is_active is not None:
        record.is_active = request.is_active

    record.modified_by = current_user.username
    await session.flush()
    await session.refresh(record)
    return PackStyleResponse.model_validate(record)


@router.delete("/pack-styles/{record_id}", status_code=status.HTTP_200_OK)
async def delete_pack_style(
    record_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
):
    """Soft-delete a pack style (sets is_active = false)."""
    result = await session.execute(
        select(PackStyleMasterModel).where(PackStyleMasterModel.id == str(record_id))
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pack Style not found")

    record.is_active = False
    record.modified_by = current_user.username
    await session.flush()
    return {"message": "Pack Style deactivated successfully"}


# ============================================================
# TYPE OF PALLET MASTER — CRUD + Excel Import
# ============================================================

@router.get("/pallets", response_model=list[PalletResponse])
async def list_pallets(
    include_inactive: bool = False,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
):
    """List pallet types. By default only active records are returned."""
    query = select(TypeOfPalletMasterModel).order_by(TypeOfPalletMasterModel.name)
    if not include_inactive:
        query = query.where(TypeOfPalletMasterModel.is_active == True)  # noqa: E712
    result = await session.execute(query)
    return [PalletResponse.model_validate(r) for r in result.scalars().all()]


@router.post("/pallets", response_model=PalletResponse, status_code=status.HTTP_201_CREATED)
async def create_pallet(
    request: PalletCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
):
    """Create a new pallet type. Duplicate name is not allowed."""
    existing = await session.execute(
        select(TypeOfPalletMasterModel).where(
            TypeOfPalletMasterModel.name.ilike(request.name)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pallet name already exists.",
        )
    record = TypeOfPalletMasterModel(
        name=request.name,
        length=request.length,
        width=request.width,
        height=request.height,
        gross_weight_per_pack_type=request.gross_weight_per_pack_type,
        volumetric_weight=request.volumetric_weight,
        is_active=True,
        created_by=current_user.username,
        modified_by=current_user.username,
    )
    session.add(record)
    await session.flush()
    await session.refresh(record)
    return PalletResponse.model_validate(record)


@router.put("/pallets/{pallet_id}", response_model=PalletResponse)
async def update_pallet(
    pallet_id: UUID,
    request: PalletUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
):
    """Update a pallet type."""
    result = await session.execute(
        select(TypeOfPalletMasterModel).where(TypeOfPalletMasterModel.id == str(pallet_id))
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pallet not found")

    if request.name is not None and request.name != record.name:
        dup = await session.execute(
            select(TypeOfPalletMasterModel).where(
                TypeOfPalletMasterModel.name.ilike(request.name),
                TypeOfPalletMasterModel.id != str(pallet_id),
            )
        )
        if dup.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Pallet name already exists.",
            )
        record.name = request.name

    if request.length is not None:
        record.length = request.length
    if request.width is not None:
        record.width = request.width
    if request.height is not None:
        record.height = request.height
    if request.gross_weight_per_pack_type is not None:
        record.gross_weight_per_pack_type = request.gross_weight_per_pack_type
    if request.volumetric_weight is not None:
        record.volumetric_weight = request.volumetric_weight
    if request.is_active is not None:
        record.is_active = request.is_active

    record.modified_by = current_user.username
    await session.flush()
    await session.refresh(record)
    return PalletResponse.model_validate(record)


@router.delete("/pallets/{pallet_id}", status_code=status.HTTP_200_OK)
async def delete_pallet(
    pallet_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
):
    """Soft-delete a pallet type (sets is_active = false)."""
    result = await session.execute(
        select(TypeOfPalletMasterModel).where(TypeOfPalletMasterModel.id == str(pallet_id))
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pallet not found")

    record.is_active = False
    record.modified_by = current_user.username
    await session.flush()
    return {"message": "Pallet type deactivated successfully"}


@router.get("/pallets-template")
async def download_pallets_template(
    current_user: User = Depends(get_current_active_user),
):
    """Download Excel template for pallet import."""
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Pallets"
    ws.append(["", "Pallet Type", "Length", "Width", "Height", "Gross Weight", "Volumetric Weight"])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=pallets_template.xlsx"},
    )


@router.post("/pallets-import", status_code=status.HTTP_200_OK)
async def import_pallets_excel(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
):
    """Import pallets from Excel. Columns: B=Pallet Type(1), C=Length(2), D=Width(3), E=Height(4), F=Gross Weight(5), G=Volumetric Weight(6)."""
    import openpyxl

    contents = await file.read()
    wb = openpyxl.load_workbook(io.BytesIO(contents), read_only=True)
    ws = wb.active
    created = 0
    skipped = 0

    # Preload existing pallet names for fast duplicate checking
    existing_result = await session.execute(_text("SELECT name FROM type_of_pallet_master"))
    existing_names = set(r[0].lower() for r in existing_result.fetchall() if r[0])

    for idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if not row:
            continue

        name = str(row[1]).strip() if len(row) > 1 and row[1] else ""
        if not name:
            continue

        if name.lower() in existing_names:
            skipped += 1
            continue

        length = int(float(row[2])) if len(row) > 2 and row[2] else None
        width = int(float(row[3])) if len(row) > 3 and row[3] else None
        height = int(float(row[4])) if len(row) > 4 and row[4] else None
        gross_weight = int(float(row[5])) if len(row) > 5 and row[5] else None
        volumetric_weight = int(float(row[6])) if len(row) > 6 and row[6] else None

        existing_names.add(name.lower())
        session.add(TypeOfPalletMasterModel(
            name=name,
            length=length,
            width=width,
            height=height,
            gross_weight_per_pack_type=gross_weight,
            volumetric_weight=volumetric_weight,
            is_active=True,
            created_by=current_user.username,
            modified_by=current_user.username,
        ))
        created += 1

    await session.flush()
    wb.close()
    return {"created": created, "skipped": skipped}


# ============================================================
# BRAND MASTER — CRUD
# ============================================================

from src.infrastructure.database.models.masters.brand_model import BrandMasterModel
from src.api.v1.endpoints.masters.schemas import (
    BrandCreateRequest, BrandUpdateRequest, BrandResponse,
)


@router.get("/brands", response_model=list[BrandResponse])
async def list_brands(
    include_inactive: bool = False,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
):
    """List brands. By default only active records are returned."""
    query = select(BrandMasterModel).order_by(BrandMasterModel.brand_name)
    if not include_inactive:
        query = query.where(BrandMasterModel.is_active == True)  # noqa: E712
    result = await session.execute(query)
    return [BrandResponse.model_validate(r) for r in result.scalars().all()]


@router.post("/brands", response_model=BrandResponse, status_code=status.HTTP_201_CREATED)
async def create_brand(
    request: BrandCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
):
    """Create a new brand. Duplicate name is not allowed."""
    existing = await session.execute(
        select(BrandMasterModel).where(
            BrandMasterModel.brand_name.ilike(request.brand_name)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Brand already exists.",
        )
    record = BrandMasterModel(
        brand_name=request.brand_name,
        is_active=True,
        created_by=current_user.username,
        modified_by=current_user.username,
    )
    session.add(record)
    await session.flush()
    await session.refresh(record)
    return BrandResponse.model_validate(record)


@router.put("/brands/{record_id}", response_model=BrandResponse)
async def update_brand(
    record_id: UUID,
    request: BrandUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
):
    """Update a brand."""
    result = await session.execute(
        select(BrandMasterModel).where(BrandMasterModel.id == str(record_id))
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found")

    if request.brand_name is not None and request.brand_name != record.brand_name:
        dup = await session.execute(
            select(BrandMasterModel).where(
                BrandMasterModel.brand_name.ilike(request.brand_name),
                BrandMasterModel.id != str(record_id),
            )
        )
        if dup.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Brand already exists.",
            )
        record.brand_name = request.brand_name

    if request.is_active is not None:
        record.is_active = request.is_active

    record.modified_by = current_user.username
    await session.flush()
    await session.refresh(record)
    return BrandResponse.model_validate(record)


@router.delete("/brands/{record_id}", status_code=status.HTTP_200_OK)
async def delete_brand(
    record_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
):
    """Soft-delete a brand (sets is_active = false)."""
    result = await session.execute(
        select(BrandMasterModel).where(BrandMasterModel.id == str(record_id))
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found")

    record.is_active = False
    record.modified_by = current_user.username
    await session.flush()
    return {"message": "Brand deactivated successfully"}


# ============================================================
# DOSAGE MASTER — CRUD
# ============================================================

from src.infrastructure.database.models.masters.dosage_model import DosageMasterModel
from src.api.v1.endpoints.masters.schemas import (
    DosageCreateRequest, DosageUpdateRequest, DosageResponse,
)


@router.get("/dosages", response_model=list[DosageResponse])
async def list_dosages(
    include_inactive: bool = False,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
):
    """List dosages. By default only active records are returned."""
    query = select(DosageMasterModel).order_by(DosageMasterModel.dosage)
    if not include_inactive:
        query = query.where(DosageMasterModel.is_active == True)  # noqa: E712
    result = await session.execute(query)
    return [DosageResponse.model_validate(r) for r in result.scalars().all()]


@router.post("/dosages", response_model=DosageResponse, status_code=status.HTTP_201_CREATED)
async def create_dosage(
    request: DosageCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
):
    """Create a new dosage. Duplicate value is not allowed."""
    existing = await session.execute(
        select(DosageMasterModel).where(
            DosageMasterModel.dosage.ilike(request.dosage)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dosage already exists.",
        )
    record = DosageMasterModel(
        dosage=request.dosage,
        is_active=True,
        created_by=current_user.username,
        modified_by=current_user.username,
    )
    session.add(record)
    await session.flush()
    await session.refresh(record)
    return DosageResponse.model_validate(record)


@router.put("/dosages/{record_id}", response_model=DosageResponse)
async def update_dosage(
    record_id: UUID,
    request: DosageUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
):
    """Update a dosage."""
    result = await session.execute(
        select(DosageMasterModel).where(DosageMasterModel.id == str(record_id))
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dosage not found")

    if request.dosage is not None and request.dosage != record.dosage:
        dup = await session.execute(
            select(DosageMasterModel).where(
                DosageMasterModel.dosage.ilike(request.dosage),
                DosageMasterModel.id != str(record_id),
            )
        )
        if dup.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Dosage already exists.",
            )
        record.dosage = request.dosage

    if request.is_active is not None:
        record.is_active = request.is_active

    record.modified_by = current_user.username
    await session.flush()
    await session.refresh(record)
    return DosageResponse.model_validate(record)


@router.delete("/dosages/{record_id}", status_code=status.HTTP_200_OK)
async def delete_dosage(
    record_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
):
    """Soft-delete a dosage (sets is_active = false)."""
    result = await session.execute(
        select(DosageMasterModel).where(DosageMasterModel.id == str(record_id))
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dosage not found")

    record.is_active = False
    record.modified_by = current_user.username
    await session.flush()
    return {"message": "Dosage deactivated successfully"}


# ============================================================
# MODE OF SHIPMENT MASTER — CRUD
# ============================================================

from src.infrastructure.database.models.masters.mode_of_shipment_model import ModeOfShipmentMasterModel
from src.api.v1.endpoints.masters.schemas import (
    ModeOfShipmentCreateRequest, ModeOfShipmentUpdateRequest, ModeOfShipmentResponse,
)


@router.get("/modes-of-shipment", response_model=list[ModeOfShipmentResponse])
async def list_modes_of_shipment(
    include_inactive: bool = False,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
):
    """List modes of shipment. By default only active records are returned."""
    query = select(ModeOfShipmentMasterModel).order_by(ModeOfShipmentMasterModel.mode_name)
    if not include_inactive:
        query = query.where(ModeOfShipmentMasterModel.is_active == True)  # noqa: E712
    result = await session.execute(query)
    return [ModeOfShipmentResponse.model_validate(r) for r in result.scalars().all()]


@router.post("/modes-of-shipment", response_model=ModeOfShipmentResponse, status_code=status.HTTP_201_CREATED)
async def create_mode_of_shipment(
    request: ModeOfShipmentCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
):
    """Create a new mode of shipment. Duplicate name is not allowed."""
    existing = await session.execute(
        select(ModeOfShipmentMasterModel).where(
            ModeOfShipmentMasterModel.mode_name.ilike(request.mode_name)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mode of Shipment already exists.",
        )
    record = ModeOfShipmentMasterModel(
        mode_name=request.mode_name,
        is_active=True,
        created_by=current_user.username,
        modified_by=current_user.username,
    )
    session.add(record)
    await session.flush()
    await session.refresh(record)
    return ModeOfShipmentResponse.model_validate(record)


@router.put("/modes-of-shipment/{record_id}", response_model=ModeOfShipmentResponse)
async def update_mode_of_shipment(
    record_id: UUID,
    request: ModeOfShipmentUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
):
    """Update a mode of shipment."""
    result = await session.execute(
        select(ModeOfShipmentMasterModel).where(ModeOfShipmentMasterModel.id == str(record_id))
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mode of Shipment not found")

    if request.mode_name is not None and request.mode_name != record.mode_name:
        dup = await session.execute(
            select(ModeOfShipmentMasterModel).where(
                ModeOfShipmentMasterModel.mode_name.ilike(request.mode_name),
                ModeOfShipmentMasterModel.id != str(record_id),
            )
        )
        if dup.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Mode of Shipment already exists.",
            )
        record.mode_name = request.mode_name

    if request.is_active is not None:
        record.is_active = request.is_active

    record.modified_by = current_user.username
    await session.flush()
    await session.refresh(record)
    return ModeOfShipmentResponse.model_validate(record)


@router.delete("/modes-of-shipment/{record_id}", status_code=status.HTTP_200_OK)
async def delete_mode_of_shipment(
    record_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
):
    """Soft-delete a mode of shipment (sets is_active = false)."""
    result = await session.execute(
        select(ModeOfShipmentMasterModel).where(ModeOfShipmentMasterModel.id == str(record_id))
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mode of Shipment not found")

    record.is_active = False
    record.modified_by = current_user.username
    await session.flush()
    return {"message": "Mode of Shipment deactivated successfully"}


# ============================================================
# THERAPEUTIC CATEGORY MASTER — CRUD
# ============================================================

from src.infrastructure.database.models.masters.therapeutic_category_model import TherapeuticCategoryMasterModel
from src.api.v1.endpoints.masters.schemas import (
    TherapeuticCategoryCreateRequest, TherapeuticCategoryUpdateRequest, TherapeuticCategoryResponse,
)


@router.get("/therapeutic-categories", response_model=list[TherapeuticCategoryResponse])
async def list_therapeutic_categories(
    include_inactive: bool = False,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
):
    """List therapeutic categories. By default only active records are returned."""
    query = select(TherapeuticCategoryMasterModel).order_by(TherapeuticCategoryMasterModel.therapeutic_category_name)
    if not include_inactive:
        query = query.where(TherapeuticCategoryMasterModel.is_active == True)  # noqa: E712
    result = await session.execute(query)
    return [TherapeuticCategoryResponse.model_validate(r) for r in result.scalars().all()]


@router.post("/therapeutic-categories", response_model=TherapeuticCategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_therapeutic_category(
    request: TherapeuticCategoryCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
):
    """Create a new therapeutic category. Duplicate name is not allowed."""
    existing = await session.execute(
        select(TherapeuticCategoryMasterModel).where(
            TherapeuticCategoryMasterModel.therapeutic_category_name.ilike(request.therapeutic_category_name)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Therapeutic Category already exists.",
        )
    record = TherapeuticCategoryMasterModel(
        therapeutic_category_name=request.therapeutic_category_name,
        is_active=True,
        created_by=current_user.username,
        modified_by=current_user.username,
    )
    session.add(record)
    await session.flush()
    await session.refresh(record)
    return TherapeuticCategoryResponse.model_validate(record)


@router.put("/therapeutic-categories/{record_id}", response_model=TherapeuticCategoryResponse)
async def update_therapeutic_category(
    record_id: UUID,
    request: TherapeuticCategoryUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
):
    """Update a therapeutic category."""
    result = await session.execute(
        select(TherapeuticCategoryMasterModel).where(TherapeuticCategoryMasterModel.id == str(record_id))
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Therapeutic Category not found")

    if request.therapeutic_category_name is not None and request.therapeutic_category_name != record.therapeutic_category_name:
        dup = await session.execute(
            select(TherapeuticCategoryMasterModel).where(
                TherapeuticCategoryMasterModel.therapeutic_category_name.ilike(request.therapeutic_category_name),
                TherapeuticCategoryMasterModel.id != str(record_id),
            )
        )
        if dup.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Therapeutic Category already exists.",
            )
        record.therapeutic_category_name = request.therapeutic_category_name

    if request.is_active is not None:
        record.is_active = request.is_active

    record.modified_by = current_user.username
    await session.flush()
    await session.refresh(record)
    return TherapeuticCategoryResponse.model_validate(record)


@router.delete("/therapeutic-categories/{record_id}", status_code=status.HTTP_200_OK)
async def delete_therapeutic_category(
    record_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user),
):
    """Soft-delete a therapeutic category (sets is_active = false)."""
    result = await session.execute(
        select(TherapeuticCategoryMasterModel).where(TherapeuticCategoryMasterModel.id == str(record_id))
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Therapeutic Category not found")

    record.is_active = False
    record.modified_by = current_user.username
    await session.flush()
    return {"message": "Therapeutic Category deactivated successfully"}

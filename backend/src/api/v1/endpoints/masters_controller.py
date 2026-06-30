"""
Masters API endpoints.
Provides CRUD operations for master data: Region, etc.
Includes Excel import/template download support.
"""

import io
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_user
from src.domain.entities.user import User
from src.infrastructure.database.models.city_model import CityModel
from src.infrastructure.database.models.country_model import CountryModel
from src.infrastructure.database.models.region_model import RegionModel
from src.infrastructure.database.models.state_model import StateModel
from src.infrastructure.database.session import get_db_session

router = APIRouter(prefix="/masters", tags=["Masters"])


# ============================================================
# SCHEMAS
# ============================================================


class RegionCreateRequest(BaseModel):
    region_name: str
    region_id: Optional[str] = None


class RegionUpdateRequest(BaseModel):
    region_name: Optional[str] = None
    region_id: Optional[str] = None
    is_active: Optional[bool] = None


class RegionResponse(BaseModel):
    id: UUID
    region_id: Optional[str] = None
    region_name: str
    is_active: bool

    class Config:
        from_attributes = True


# ============================================================
# REGION MASTER — CRUD
# ============================================================


@router.get("/regions", response_model=list[RegionResponse])
async def list_regions(
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """List regions. By default only active regions are returned."""
    query = select(RegionModel).order_by(RegionModel.region_name)
    if not include_inactive:
        query = query.where(RegionModel.is_active == True)  # noqa: E712
    result = await db.execute(query)
    return [RegionResponse.model_validate(r) for r in result.scalars().all()]


@router.post("/regions", response_model=RegionResponse, status_code=status.HTTP_201_CREATED)
async def create_region(
    request: RegionCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Create a new region. Duplicate region_name is not allowed."""
    existing = await db.execute(
        select(RegionModel).where(RegionModel.region_name.ilike(request.region_name))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Region name already exists.",
        )

    region = RegionModel(
        region_name=request.region_name,
        region_id=request.region_id,
        is_active=True,
        created_by=current_user.username,
        modified_by=current_user.username,
    )
    db.add(region)
    await db.flush()
    return RegionResponse.model_validate(region)


@router.put("/regions/{region_id}", response_model=RegionResponse)
async def update_region(
    region_id: UUID,
    request: RegionUpdateRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Update a region."""
    result = await db.execute(select(RegionModel).where(RegionModel.id == region_id))
    region = result.scalar_one_or_none()
    if not region:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Region not found")

    if request.region_name is not None and request.region_name != region.region_name:
        dup = await db.execute(
            select(RegionModel).where(
                RegionModel.region_name.ilike(request.region_name),
                RegionModel.id != region_id,
            )
        )
        if dup.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Region name already exists.",
            )
        region.region_name = request.region_name

    if request.region_id is not None:
        region.region_id = request.region_id

    if request.is_active is not None:
        region.is_active = request.is_active

    region.modified_by = current_user.username
    await db.flush()
    return RegionResponse.model_validate(region)


@router.delete("/regions/{region_id}", status_code=status.HTTP_200_OK)
async def delete_region(
    region_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Soft-delete a region (sets is_active = false)."""
    result = await db.execute(select(RegionModel).where(RegionModel.id == region_id))
    region = result.scalar_one_or_none()
    if not region:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Region not found")

    region.is_active = False
    region.modified_by = current_user.username
    await db.flush()
    return {"message": "Region deactivated successfully"}


# ============================================================
# EXCEL IMPORT / TEMPLATE
# ============================================================


@router.get("/regions-template")
async def download_region_template(
    current_user: User = Depends(get_current_user),
):
    """Download an Excel template for bulk region import."""
    try:
        import openpyxl
    except ImportError:
        # Fallback: return a CSV template if openpyxl is not available
        csv_content = "region_id,region_name\n"
        return StreamingResponse(
            io.BytesIO(csv_content.encode()),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=regions_template.csv"},
        )

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Regions"
    ws.append(["region_id", "region_name"])
    # Add sample row
    ws.append(["REG001", "Sample Region"])

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=regions_template.xlsx"},
    )


@router.post("/regions-import")
async def import_regions(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """
    Import regions from an Excel file (.xlsx/.xls).
    Expected columns: region_id, region_name.
    Skips duplicates by region_name.
    """
    try:
        import openpyxl
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="openpyxl package is required for Excel import. Install it with: pip install openpyxl",
        )

    content = await file.read()
    try:
        wb = openpyxl.load_workbook(io.BytesIO(content))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Excel file. Please upload a valid .xlsx file.",
        )

    ws = wb.active
    rows = list(ws.iter_rows(min_row=2, values_only=True))  # Skip header

    created = 0
    skipped = 0

    for row in rows:
        if not row or len(row) < 2:
            skipped += 1
            continue

        region_id_val = str(row[0]).strip() if row[0] else None
        region_name_val = str(row[1]).strip() if row[1] else None

        if not region_name_val:
            skipped += 1
            continue

        # Check duplicate
        existing = await db.execute(
            select(RegionModel).where(RegionModel.region_name.ilike(region_name_val))
        )
        if existing.scalar_one_or_none():
            skipped += 1
            continue

        region = RegionModel(
            region_name=region_name_val,
            region_id=region_id_val,
            is_active=True,
            created_by=current_user.username,
            modified_by=current_user.username,
        )
        db.add(region)
        created += 1

    await db.flush()
    return {"created": created, "skipped": skipped}


# ============================================================
# COUNTRY MASTER — SCHEMAS
# ============================================================


class CountryCreateRequest(BaseModel):
    country_code: str
    country_name: str
    region_id: Optional[UUID] = None


class CountryUpdateRequest(BaseModel):
    country_code: Optional[str] = None
    country_name: Optional[str] = None
    region_id: Optional[UUID] = None
    is_active: Optional[bool] = None


class CountryResponse(BaseModel):
    id: UUID
    country_code: str
    country_name: str
    region_id: Optional[UUID] = None
    region_name: Optional[str] = None
    is_active: bool

    class Config:
        from_attributes = True


# ============================================================
# COUNTRY MASTER — CRUD
# ============================================================


@router.get("/countries", response_model=list[CountryResponse])
async def list_countries(
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """List countries with region info. By default only active."""
    query = select(CountryModel).order_by(CountryModel.country_name)
    if not include_inactive:
        query = query.where(CountryModel.is_active == True)  # noqa: E712
    result = await db.execute(query)
    countries = result.scalars().all()

    return [
        CountryResponse(
            id=c.id,
            country_code=c.country_code,
            country_name=c.country_name,
            region_id=c.region_id,
            region_name=c.region.region_name if c.region else None,
            is_active=c.is_active,
        )
        for c in countries
    ]


@router.post("/countries", response_model=CountryResponse, status_code=status.HTTP_201_CREATED)
async def create_country(
    request: CountryCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Create a new country. Duplicate country_name is not allowed."""
    existing = await db.execute(
        select(CountryModel).where(CountryModel.country_name.ilike(request.country_name))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Country name already exists.",
        )

    # Validate region if provided
    if request.region_id:
        region_result = await db.execute(
            select(RegionModel).where(
                RegionModel.id == request.region_id,
                RegionModel.is_active == True,  # noqa: E712
            )
        )
        if not region_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selected region does not exist or is inactive.",
            )

    country = CountryModel(
        country_code=request.country_code,
        country_name=request.country_name,
        region_id=request.region_id,
        is_active=True,
        created_by=current_user.username,
        modified_by=current_user.username,
    )
    db.add(country)
    await db.flush()

    # Reload to get the region relationship
    await db.refresh(country)

    return CountryResponse(
        id=country.id,
        country_code=country.country_code,
        country_name=country.country_name,
        region_id=country.region_id,
        region_name=country.region.region_name if country.region else None,
        is_active=country.is_active,
    )


@router.put("/countries/{country_id}", response_model=CountryResponse)
async def update_country(
    country_id: UUID,
    request: CountryUpdateRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Update a country."""
    result = await db.execute(select(CountryModel).where(CountryModel.id == country_id))
    country = result.scalar_one_or_none()
    if not country:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Country not found")

    if request.country_name is not None and request.country_name != country.country_name:
        dup = await db.execute(
            select(CountryModel).where(
                CountryModel.country_name.ilike(request.country_name),
                CountryModel.id != country_id,
            )
        )
        if dup.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Country name already exists.",
            )
        country.country_name = request.country_name

    if request.country_code is not None:
        country.country_code = request.country_code

    if request.region_id is not None:
        region_result = await db.execute(
            select(RegionModel).where(
                RegionModel.id == request.region_id,
                RegionModel.is_active == True,  # noqa: E712
            )
        )
        if not region_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selected region does not exist or is inactive.",
            )
        country.region_id = request.region_id

    if request.is_active is not None:
        country.is_active = request.is_active

    country.modified_by = current_user.username
    await db.flush()

    # Reload to get the region relationship
    await db.refresh(country)

    return CountryResponse(
        id=country.id,
        country_code=country.country_code,
        country_name=country.country_name,
        region_id=country.region_id,
        region_name=country.region.region_name if country.region else None,
        is_active=country.is_active,
    )


@router.delete("/countries/{country_id}", status_code=status.HTTP_200_OK)
async def delete_country(
    country_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Soft-delete a country (sets is_active = false)."""
    result = await db.execute(select(CountryModel).where(CountryModel.id == country_id))
    country = result.scalar_one_or_none()
    if not country:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Country not found")

    country.is_active = False
    country.modified_by = current_user.username
    await db.flush()
    return {"message": "Country deactivated successfully"}


# ============================================================
# COUNTRY — EXCEL IMPORT / TEMPLATE
# ============================================================


@router.get("/countries-template")
async def download_country_template(
    current_user: User = Depends(get_current_user),
):
    """Download an Excel template for bulk country import."""
    try:
        import openpyxl
    except ImportError:
        csv_content = "country_code,country_name,region_name\n"
        return StreamingResponse(
            io.BytesIO(csv_content.encode()),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=countries_template.csv"},
        )

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Countries"
    ws.append(["country_code", "country_name", "region_name"])
    ws.append(["US", "United States", "Asia Pacific"])

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=countries_template.xlsx"},
    )


@router.post("/countries-import")
async def import_countries(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """
    Import countries from an Excel file (.xlsx/.xls).
    Expected columns: country_code, country_name, region_name.
    Skips duplicates by country_name. Matches region by name.
    """
    try:
        import openpyxl
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="openpyxl package is required for Excel import.",
        )

    content = await file.read()
    try:
        wb = openpyxl.load_workbook(io.BytesIO(content))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Excel file. Please upload a valid .xlsx file.",
        )

    ws = wb.active
    rows = list(ws.iter_rows(min_row=2, values_only=True))

    created = 0
    skipped = 0

    for row in rows:
        if not row or len(row) < 2:
            skipped += 1
            continue

        code_val = str(row[0]).strip() if row[0] else None
        name_val = str(row[1]).strip() if row[1] else None
        region_name_val = str(row[2]).strip() if len(row) > 2 and row[2] else None

        if not code_val or not name_val:
            skipped += 1
            continue

        # Check duplicate
        existing = await db.execute(
            select(CountryModel).where(CountryModel.country_name.ilike(name_val))
        )
        if existing.scalar_one_or_none():
            skipped += 1
            continue

        # Resolve region by name
        region_id = None
        if region_name_val:
            region_result = await db.execute(
                select(RegionModel).where(
                    RegionModel.region_name.ilike(region_name_val),
                    RegionModel.is_active == True,  # noqa: E712
                )
            )
            region = region_result.scalar_one_or_none()
            if region:
                region_id = region.id

        country = CountryModel(
            country_code=code_val,
            country_name=name_val,
            region_id=region_id,
            is_active=True,
            created_by=current_user.username,
            modified_by=current_user.username,
        )
        db.add(country)
        created += 1

    await db.flush()
    return {"created": created, "skipped": skipped}


# ============================================================
# STATE MASTER — SCHEMAS
# ============================================================


class StateCreateRequest(BaseModel):
    country_id: UUID
    language_key: str
    state_name: str


class StateUpdateRequest(BaseModel):
    country_id: Optional[UUID] = None
    language_key: Optional[str] = None
    state_name: Optional[str] = None
    is_active: Optional[bool] = None


class StateResponse(BaseModel):
    id: UUID
    country_id: UUID
    country_name: Optional[str] = None
    language_key: str
    state_name: str
    is_active: bool

    class Config:
        from_attributes = True


# ============================================================
# STATE MASTER — CRUD
# ============================================================


@router.get("/states", response_model=list[StateResponse])
async def list_states(
    include_inactive: bool = False,
    country_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """List states with country info. By default only active."""
    query = select(StateModel).order_by(StateModel.state_name)
    if not include_inactive:
        query = query.where(StateModel.is_active == True)  # noqa: E712
    if country_id:
        query = query.where(StateModel.country_id == country_id)
    result = await db.execute(query)
    states = result.scalars().all()

    return [
        StateResponse(
            id=s.id,
            country_id=s.country_id,
            country_name=s.country.country_name if s.country else None,
            language_key=s.language_key,
            state_name=s.state_name,
            is_active=s.is_active,
        )
        for s in states
    ]


@router.post("/states", response_model=StateResponse, status_code=status.HTTP_201_CREATED)
async def create_state(
    request: StateCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Create a new state. Duplicate state_name is not allowed."""
    existing = await db.execute(
        select(StateModel).where(StateModel.state_name.ilike(request.state_name))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="State name already exists.",
        )

    # Validate country is active
    country_result = await db.execute(
        select(CountryModel).where(
            CountryModel.id == request.country_id,
            CountryModel.is_active == True,  # noqa: E712
        )
    )
    if not country_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Selected country does not exist or is inactive.",
        )

    state = StateModel(
        country_id=request.country_id,
        language_key=request.language_key,
        state_name=request.state_name,
        is_active=True,
        created_by=current_user.username,
        modified_by=current_user.username,
    )
    db.add(state)
    await db.flush()
    await db.refresh(state)

    return StateResponse(
        id=state.id,
        country_id=state.country_id,
        country_name=state.country.country_name if state.country else None,
        language_key=state.language_key,
        state_name=state.state_name,
        is_active=state.is_active,
    )


@router.put("/states/{state_id}", response_model=StateResponse)
async def update_state(
    state_id: UUID,
    request: StateUpdateRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Update a state."""
    result = await db.execute(select(StateModel).where(StateModel.id == state_id))
    state = result.scalar_one_or_none()
    if not state:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="State not found")

    if request.state_name is not None and request.state_name != state.state_name:
        dup = await db.execute(
            select(StateModel).where(
                StateModel.state_name.ilike(request.state_name),
                StateModel.id != state_id,
            )
        )
        if dup.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="State name already exists.",
            )
        state.state_name = request.state_name

    if request.country_id is not None:
        country_result = await db.execute(
            select(CountryModel).where(
                CountryModel.id == request.country_id,
                CountryModel.is_active == True,  # noqa: E712
            )
        )
        if not country_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selected country does not exist or is inactive.",
            )
        state.country_id = request.country_id

    if request.language_key is not None:
        state.language_key = request.language_key
    if request.is_active is not None:
        state.is_active = request.is_active

    state.modified_by = current_user.username
    await db.flush()
    await db.refresh(state)

    return StateResponse(
        id=state.id,
        country_id=state.country_id,
        country_name=state.country.country_name if state.country else None,
        language_key=state.language_key,
        state_name=state.state_name,
        is_active=state.is_active,
    )


@router.delete("/states/{state_id}", status_code=status.HTTP_200_OK)
async def delete_state(
    state_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Soft-delete a state (sets is_active = false)."""
    result = await db.execute(select(StateModel).where(StateModel.id == state_id))
    state = result.scalar_one_or_none()
    if not state:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="State not found")

    state.is_active = False
    state.modified_by = current_user.username
    await db.flush()
    return {"message": "State deactivated successfully"}


# ============================================================
# STATE — EXCEL IMPORT / TEMPLATE
# ============================================================


@router.get("/states-template")
async def download_state_template(
    current_user: User = Depends(get_current_user),
):
    """Download an Excel template for bulk state import."""
    try:
        import openpyxl
    except ImportError:
        csv_content = "language_key,country_name,state_name\n"
        return StreamingResponse(
            io.BytesIO(csv_content.encode()),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=states_template.csv"},
        )

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "States"
    ws.append(["language_key", "country_name", "state_name"])
    ws.append(["EN", "India", "Maharashtra"])

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=states_template.xlsx"},
    )


@router.post("/states-import")
async def import_states(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """
    Import states from an Excel file (.xlsx/.xls).
    Expected columns: language_key, country_name, state_name.
    Skips duplicates by state_name. Matches country by name.
    """
    try:
        import openpyxl
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="openpyxl package is required for Excel import.",
        )

    content = await file.read()
    try:
        wb = openpyxl.load_workbook(io.BytesIO(content))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Excel file. Please upload a valid .xlsx file.",
        )

    ws = wb.active
    rows = list(ws.iter_rows(min_row=2, values_only=True))

    created = 0
    skipped = 0

    for row in rows:
        if not row or len(row) < 3:
            skipped += 1
            continue

        lang_key = str(row[0]).strip() if row[0] else None
        country_name_val = str(row[1]).strip() if row[1] else None
        state_name_val = str(row[2]).strip() if row[2] else None

        if not lang_key or not country_name_val or not state_name_val:
            skipped += 1
            continue

        # Check duplicate
        existing = await db.execute(
            select(StateModel).where(StateModel.state_name.ilike(state_name_val))
        )
        if existing.scalar_one_or_none():
            skipped += 1
            continue

        # Resolve country by name
        country_result = await db.execute(
            select(CountryModel).where(
                CountryModel.country_name.ilike(country_name_val),
                CountryModel.is_active == True,  # noqa: E712
            )
        )
        country = country_result.scalar_one_or_none()
        if not country:
            skipped += 1
            continue

        state = StateModel(
            country_id=country.id,
            language_key=lang_key,
            state_name=state_name_val,
            is_active=True,
            created_by=current_user.username,
            modified_by=current_user.username,
        )
        db.add(state)
        created += 1

    await db.flush()
    return {"created": created, "skipped": skipped}


# ============================================================
# CITY MASTER — SCHEMAS
# ============================================================


class CityCreateRequest(BaseModel):
    state_id: UUID
    city_name: str


class CityUpdateRequest(BaseModel):
    state_id: Optional[UUID] = None
    city_name: Optional[str] = None
    is_active: Optional[bool] = None


class CityResponse(BaseModel):
    id: UUID
    city_name: str
    state_id: UUID
    state_name: Optional[str] = None
    is_active: bool

    class Config:
        from_attributes = True


# ============================================================
# CITY MASTER — CRUD
# ============================================================


@router.get("/cities", response_model=list[CityResponse])
async def list_cities(
    include_inactive: bool = False,
    state_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """List cities with state info. By default only active."""
    query = select(CityModel).order_by(CityModel.city_name)
    if not include_inactive:
        query = query.where(CityModel.is_active == True)  # noqa: E712
    if state_id:
        query = query.where(CityModel.state_id == state_id)
    result = await db.execute(query)
    cities = result.scalars().all()

    return [
        CityResponse(
            id=c.id,
            city_name=c.city_name,
            state_id=c.state_id,
            state_name=c.state.state_name if c.state else None,
            is_active=c.is_active,
        )
        for c in cities
    ]


@router.post("/cities", response_model=CityResponse, status_code=status.HTTP_201_CREATED)
async def create_city(
    request: CityCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Create a new city. Duplicate city_name within the same state is not allowed."""
    existing = await db.execute(
        select(CityModel).where(
            CityModel.city_name.ilike(request.city_name),
            CityModel.state_id == request.state_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="City name already exists in this state.",
        )

    # Validate state is active
    state_result = await db.execute(
        select(StateModel).where(
            StateModel.id == request.state_id,
            StateModel.is_active == True,  # noqa: E712
        )
    )
    if not state_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Selected state does not exist or is inactive.",
        )

    city = CityModel(
        city_name=request.city_name,
        state_id=request.state_id,
        is_active=True,
        created_by=current_user.username,
        modified_by=current_user.username,
    )
    db.add(city)
    await db.flush()
    await db.refresh(city)

    return CityResponse(
        id=city.id,
        city_name=city.city_name,
        state_id=city.state_id,
        state_name=city.state.state_name if city.state else None,
        is_active=city.is_active,
    )


@router.put("/cities/{city_id}", response_model=CityResponse)
async def update_city(
    city_id: UUID,
    request: CityUpdateRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Update a city."""
    result = await db.execute(select(CityModel).where(CityModel.id == city_id))
    city = result.scalar_one_or_none()
    if not city:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="City not found")

    target_state_id = request.state_id if request.state_id is not None else city.state_id
    target_city_name = request.city_name if request.city_name is not None else city.city_name

    if request.city_name is not None or request.state_id is not None:
        dup = await db.execute(
            select(CityModel).where(
                CityModel.city_name.ilike(target_city_name),
                CityModel.state_id == target_state_id,
                CityModel.id != city_id,
            )
        )
        if dup.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="City name already exists in this state.",
            )

    if request.state_id is not None:
        state_result = await db.execute(
            select(StateModel).where(
                StateModel.id == request.state_id,
                StateModel.is_active == True,  # noqa: E712
            )
        )
        if not state_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selected state does not exist or is inactive.",
            )
        city.state_id = request.state_id

    if request.city_name is not None:
        city.city_name = request.city_name
    if request.is_active is not None:
        city.is_active = request.is_active

    city.modified_by = current_user.username
    await db.flush()
    await db.refresh(city)

    return CityResponse(
        id=city.id,
        city_name=city.city_name,
        state_id=city.state_id,
        state_name=city.state.state_name if city.state else None,
        is_active=city.is_active,
    )


@router.delete("/cities/{city_id}", status_code=status.HTTP_200_OK)
async def delete_city(
    city_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Soft-delete a city (sets is_active = false)."""
    result = await db.execute(select(CityModel).where(CityModel.id == city_id))
    city = result.scalar_one_or_none()
    if not city:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="City not found")

    city.is_active = False
    city.modified_by = current_user.username
    await db.flush()
    return {"message": "City deactivated successfully"}


# ============================================================
# CITY — EXCEL IMPORT / TEMPLATE
# ============================================================


@router.get("/cities-template")
async def download_city_template(
    current_user: User = Depends(get_current_user),
):
    """Download an Excel template for bulk city import."""
    try:
        import openpyxl
    except ImportError:
        csv_content = "city_name,state_name\n"
        return StreamingResponse(
            io.BytesIO(csv_content.encode()),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=cities_template.csv"},
        )

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Cities"
    ws.append(["city_name", "state_name"])
    ws.append(["Mumbai", "Maharashtra"])

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=cities_template.xlsx"},
    )


@router.post("/cities-import")
async def import_cities(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """
    Import cities from an Excel file (.xlsx/.xls).
    Expected columns: city_name, state_name.
    Skips duplicates by city_name+state. Matches state by name.
    """
    try:
        import openpyxl
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="openpyxl package is required for Excel import.",
        )

    content = await file.read()
    try:
        wb = openpyxl.load_workbook(io.BytesIO(content))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Excel file. Please upload a valid .xlsx file.",
        )

    ws = wb.active
    rows = list(ws.iter_rows(min_row=2, values_only=True))

    created = 0
    skipped = 0

    for row in rows:
        if not row or len(row) < 2:
            skipped += 1
            continue

        city_name_val = str(row[0]).strip() if row[0] else None
        state_name_val = str(row[1]).strip() if row[1] else None

        if not city_name_val or not state_name_val:
            skipped += 1
            continue

        # Resolve state by name
        state_result = await db.execute(
            select(StateModel).where(
                StateModel.state_name.ilike(state_name_val),
                StateModel.is_active == True,  # noqa: E712
            )
        )
        state = state_result.scalar_one_or_none()
        if not state:
            skipped += 1
            continue

        # Check duplicate within state
        existing = await db.execute(
            select(CityModel).where(
                CityModel.city_name.ilike(city_name_val),
                CityModel.state_id == state.id,
            )
        )
        if existing.scalar_one_or_none():
            skipped += 1
            continue

        city = CityModel(
            city_name=city_name_val,
            state_id=state.id,
            is_active=True,
            created_by=current_user.username,
            modified_by=current_user.username,
        )
        db.add(city)
        created += 1

    await db.flush()
    return {"created": created, "skipped": skipped}

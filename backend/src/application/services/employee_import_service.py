"""
Employee Import Application Service.
Orchestrates fetching employees from Darwin AD and upserting into the database.
Controllers delegate here; this layer calls repositories and external clients.

Entity resolution (Req 3.2–3.4): When a Darwin employee record contains a
``group_company`` value, this service resolves it to an Entity (by name,
case-insensitive). If no matching Entity exists, one is created automatically.
The user's ``entity_id`` is then set to the resolved Entity's UUID.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.services.masters.entity_service import EntityCreateInput, EntityService
from src.domain.entities.user import User
from src.infrastructure.database.models.masters.entity_model import EntityModel
from src.infrastructure.database.models.user_details_model import UserDetailsModel
from src.infrastructure.database.models.user_model import UserModel
from src.infrastructure.database.repositories.masters.entity_repository_impl import (
    EntityRepositoryImpl,
)
from src.infrastructure.external.employee_ad.employee_ad_client import (
    EmployeeADClient,
    EmployeeADError,
)
from src.infrastructure.security.password_encoder import hash_password

logger = logging.getLogger(__name__)


@dataclass
class ImportResult:
    """Result for a single employee import."""

    employee_id: str
    status: str  # "created", "updated", "failed"
    message: str = ""


@dataclass
class ImportSummary:
    """Aggregated result for the import operation."""

    total: int = 0
    created: int = 0
    updated: int = 0
    failed: int = 0
    results: list[ImportResult] = field(default_factory=list)


class EmployeeImportService:
    """
    Application service for importing employees from Darwin AD.

    Responsibilities:
    - Fetch employee data from Darwin AD external service
    - Upsert users and user_details records
    - Track import results per employee
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._ad_client = EmployeeADClient()

    async def import_employees(
        self,
        employee_ids: list[str],
        actor: User,
    ) -> ImportSummary:
        """
        Fetch employees from Darwin AD and upsert into users + user_details.

        - New users: created with username=employee_id, password=employee_id
        - Existing users: password unchanged, user_details updated with latest Darwin data

        Raises:
            ValueError: If Darwin API call fails.
        """
        # Fetch from Darwin AD
        try:
            darwin_response = await self._ad_client.get_selected_employees(employee_ids)
        except EmployeeADError as exc:
            raise ValueError(f"Darwin API error: {exc.detail}")

        logger.info(
            "Darwin raw response keys: %s",
            darwin_response.keys() if isinstance(darwin_response, dict) else type(darwin_response),
        )

        employee_data_list = self._extract_employee_list(darwin_response)

        summary = ImportSummary()
        for emp_data in employee_data_list:
            result = await self._process_single_employee(emp_data, actor)
            summary.results.append(result)
            if result.status == "created":
                summary.created += 1
            elif result.status == "updated":
                summary.updated += 1
            else:
                summary.failed += 1

        summary.total = len(summary.results)
        return summary

    # ─── Private Helpers ───

    async def _process_single_employee(self, emp_data: dict, actor: User) -> ImportResult:
        """Process a single employee record: upsert user + user_details.

        Also resolves the Entity from ``group_company`` (Req 3.2–3.4):
        create-if-missing or link-if-exists, and sets ``entity_id`` on the user.
        """
        logger.info(
            "Employee data keys: %s",
            emp_data.keys() if isinstance(emp_data, dict) else type(emp_data),
        )

        emp_id = str(
            emp_data.get("employee_id", emp_data.get("EmployeeId", emp_data.get("employeeId", "")))
        ).strip()

        if not emp_id:
            return ImportResult(
                employee_id="unknown",
                status="failed",
                message="No EmployeeId in Darwin response",
            )

        try:
            # Resolve Entity from group_company
            entity_id = await self._resolve_entity_from_group_company(emp_data, actor)

            # Check if user exists
            stmt = select(UserModel).where(UserModel.username == emp_id)
            result = await self._session.execute(stmt)
            user_model = result.scalar_one_or_none()

            if user_model is None:
                # Create new user
                user_model = UserModel(
                    id=uuid4(),
                    username=emp_id,
                    password_hash=hash_password(emp_id),
                    is_active=True,
                    is_blocked=False,
                    is_validate_ad=True,
                    created_by=actor.username,
                    modified_by=actor.username,
                )
                self._session.add(user_model)
                await self._session.flush()
                status_str = "created"
            else:
                status_str = "updated"

            # Upsert user_details (entity_id stored here per updated design)
            await self._upsert_user_details(emp_data, user_model.id, actor.username, entity_id)

            return ImportResult(employee_id=emp_id, status=status_str)

        except Exception as exc:
            return ImportResult(
                employee_id=emp_id,
                status="failed",
                message=str(exc)[:200],
            )

    async def _resolve_entity_from_group_company(
        self, emp_data: dict, actor: User
    ) -> "UUID | None":
        """Resolve or create an Entity from the Darwin ``group_company`` field.

        - If ``group_company`` is empty/missing → returns None (no entity link).
        - If an Entity with that name exists → returns its id.
        - If no Entity exists → creates one and returns its id.
        """
        from uuid import UUID as _UUID  # noqa: F811

        group_company = str(emp_data.get("group_company", "")).strip()
        if not group_company:
            return None

        entity_repo = EntityRepositoryImpl(self._session)

        # Try to find existing entity by name (case-insensitive)
        existing = await entity_repo.get_by_name(group_company)
        if existing is not None:
            return existing.id

        # Create new entity
        entity_service = EntityService(session=self._session, entity_repo=entity_repo)
        created = await entity_service.create_entity(
            EntityCreateInput(
                entity_name=group_company,
                company_code=None,
            ),
            actor,
        )
        return created.id

    async def _upsert_user_details(
        self, emp_data: dict, user_id, actor_username: str, entity_id=None
    ) -> None:
        """Create or update user_details record from Darwin data."""
        details_stmt = select(UserDetailsModel).where(
            UserDetailsModel.user_id == user_id
        )
        details_result = await self._session.execute(details_stmt)
        details_model = details_result.scalar_one_or_none()

        details_fields = self._extract_details_fields(emp_data, user_id, actor_username)
        # Store entity_id in user_details (not users table)
        if entity_id is not None:
            details_fields["entity_id"] = entity_id

        if details_model is None:
            details_model = UserDetailsModel(**details_fields)
            self._session.add(details_model)
        else:
            for key, value in details_fields.items():
                # Never overwrite the primary key (id), user_id, or audit creation fields
                if key not in ("id", "user_id", "created_by", "created_date"):
                    setattr(details_model, key, value)
            if entity_id is not None:
                details_model.entity_id = entity_id
            details_model.modified_by = actor_username

        await self._session.flush()

    @staticmethod
    def _extract_employee_list(darwin_response) -> list[dict]:
        """Extract employee data list from Darwin response (handles multiple response formats)."""
        if isinstance(darwin_response, list):
            return darwin_response

        employee_data_list = darwin_response.get("employeeData", [])
        if employee_data_list:
            return employee_data_list

        # Try other common keys
        for key in darwin_response:
            val = darwin_response[key]
            if isinstance(val, list) and len(val) > 0:
                return val

        return []

    @staticmethod
    def _extract_details_fields(emp_data: dict, user_id, created_by: str) -> dict:
        """Extract and normalize Darwin employee fields into user_details columns."""

        def get(key: str) -> str:
            val = emp_data.get(key, "")
            return str(val).strip() if val is not None else ""

        first = get("first_name")
        middle = get("middle_name")
        last = get("last_name")
        full_name = " ".join(part for part in [first, middle, last] if part)

        return {
            "id": uuid4(),
            "user_id": user_id,
            "employee_id": get("employee_id"),
            "employee_name": full_name,
            "first_name": first,
            "middle_name": middle,
            "last_name": last,
            "email": get("company_email_id"),
            "designation_title": get("designation_title"),
            "department": get("department"),
            "business_unit": get("business_unit"),
            "group_company": get("group_company"),
            "location": get("office_location"),
            "region": get("office_state"),
            "zone": get("office_city"),
            "grade": get("job_level"),
            "office_mobile_no": get("office_mobile_no"),
            "personal_mobile_no": get("personal_mobile_no"),
            "date_of_joining": get("date_of_joining") or get("date_of_birth"),
            "reporting_manager": get("direct_manager_name"),
            "direct_manager_employee_id": get("direct_manager_employee_id"),
            "direct_manager_name": get("direct_manager_name"),
            "direct_manager_email": get("direct_manager_email"),
            "sap_user_id": get("cost_center_id"),
            "division_id": get("division"),
            "territory_id": get("territory_code_(sales_hq_code)"),
            "created_by": created_by,
            "modified_by": created_by,
        }

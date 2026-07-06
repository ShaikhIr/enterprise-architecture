"""
User Application Service.
Orchestrates user business logic — CRUD, role assignment, details, history,
the Create/Edit User pages (Requirements 4 & 5), and HR import (Requirement 3).
Controllers delegate here; this layer calls repositories.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.v1.schemas.user_request import (
    CreateUserRequest,
    EditUserRequest,
    HrImportRow,
)
from src.api.v1.schemas.user_response import (
    ImportRowError,
    ImportSummary,
    UserDetailResponse,
    UserListResponse,
    UserResponse,
)
from src.application.exceptions.application_exceptions import (
    MasterConflictError,
    MasterNotFoundError,
    MasterValidationError,
)
from src.application.services.masters.entity_service import (
    EntityCreateInput,
    EntityService,
)
from src.domain.entities.masters.entity import EntityEntity
from src.domain.entities.user import User
from src.domain.repositories.masters.entity_repository import IEntityRepository
from src.domain.repositories.user_repository import IUserRepository
from src.infrastructure.database.models.audit_log_model import AuditLogModel
from src.infrastructure.database.models.role_model import RoleAssignmentModel, RoleModel
from src.infrastructure.database.models.user_details_model import UserDetailsModel
from src.infrastructure.database.models.user_model import UserModel
from src.infrastructure.database.repositories.masters.entity_repository_impl import (
    EntityRepositoryImpl,
)
from src.infrastructure.security.password_encoder import hash_password



class UserService:
    """
    Application service for user management.

    Responsibilities:
    - Orchestrate user CRUD operations (incl. Create/Edit User pages)
    - Manage role assignments and the optional Entity link
    - Import users from the HR system with entity resolution
    - Aggregate data from multiple sources (users, user_details, audit_logs)
    """

    def __init__(
        self,
        session: AsyncSession,
        user_repo: IUserRepository,
        entity_repo: IEntityRepository | None = None,
    ) -> None:
        self._session = session
        self._user_repo = user_repo
        # Entity repository is needed for the Entity reference validation and HR
        # import resolution. When the caller does not inject one, build the
        # default SQLAlchemy adapter from the shared session.
        self._entity_repo: IEntityRepository = entity_repo or EntityRepositoryImpl(session)

    # ─── List Users ───

    async def list_users(self, skip: int = 0, limit: int = 100) -> UserListResponse:
        """Get users with employee details and last login timestamp."""
        stmt = (
            select(UserModel, UserDetailsModel)
            .outerjoin(UserDetailsModel, UserDetailsModel.user_id == UserModel.id)
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        rows = result.all()

        user_ids = [str(row[0].id) for row in rows]
        last_login_map = await self._get_last_logins(user_ids)

        users = []
        for user_model, details_model in rows:
            users.append(UserResponse(
                id=user_model.id,
                username=user_model.username,
                is_active=user_model.is_active,
                is_blocked=user_model.is_blocked,
                is_validate_ad=user_model.is_validate_ad,
                employee_id=details_model.employee_id if details_model else None,
                employee_name=details_model.employee_name if details_model else None,
                email=details_model.email if details_model else None,
                last_login=last_login_map.get(str(user_model.id)),
                created_by=user_model.created_by,
                created_date=user_model.created_date,
                modified_by=user_model.modified_by,
                modified_date=user_model.modified_date,
            ))

        return UserListResponse(users=users, total=len(users), skip=skip, limit=limit)

    # ─── Create User (Requirement 4) ───

    async def create_user(self, request: CreateUserRequest, actor: User) -> UserResponse:
        """Create a new user with optional entity link and role assignments.

        Enforces (in order, before any persistence so a rejected request stores
        nothing):
        - Employee ID and User Name required (Req 4.1)
        - Employee ID uniqueness (Req 4.2) and User Name uniqueness (Req 4.3)
        - Password >= 8 chars unless Validate-with-AD (Req 4.4, 4.7)
        - Entity reference must be an existing active Entity (Req 4.5)
        - All supplied Roles must exist (Req 4.6)
        Then stores the user + details and assigns roles (Req 4.8, 4.9, 4.10).
        """
        employee_id = (request.employee_id or "").strip()
        username = (request.username or "").strip()

        if not employee_id:
            raise MasterValidationError("employee_id", "Employee ID is required")
        if not username:
            raise MasterValidationError("username", "User Name is required")

        if await self._employee_id_exists(employee_id):
            raise MasterConflictError(
                f"A user with Employee ID '{employee_id}' already exists"
            )
        if await self._user_repo.exists_by_username(username):
            raise MasterConflictError(
                f"A user with User Name '{username}' already exists"
            )

        password_hash = self._resolve_create_password(request)

        await self._validate_active_entity(request.entity_id)
        await self._validate_roles_exist(request.role_ids)

        user = User(
            id=uuid4(),
            username=username,
            password_hash=password_hash,
            is_validate_ad=request.is_validate_ad,
            created_by=actor.username,
            modified_by=actor.username,
        )
        created = await self._user_repo.create(user)

        self._add_user_details(
            user_id=created.id,
            employee_id=employee_id,
            email=request.email,
            first_name=request.first_name,
            last_name=request.last_name,
            actor_username=actor.username,
        )

        # Store entity_id in user_details
        if request.entity_id is not None:
            await self._update_entity_in_details(created.id, request.entity_id, actor.username)

        await self._assign_roles(created.id, request.role_ids, actor.username)

        return self._to_response(created)

    # ─── Get User by ID ───

    async def get_user(self, user_id: UUID) -> User:
        """Get a user by ID. Raises ValueError if not found."""
        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            raise ValueError("User not found")
        return user

    # ─── Edit User (Requirement 5) ───

    async def update_user(
        self, user_id: UUID, request: EditUserRequest, actor: User
    ) -> UserResponse:
        """Edit an existing user.

        Preserves Employee ID and User Name (Req 5.1); not-found on unknown ID
        (Req 5.2); validates Entity is active (Req 5.3); updates Email/First/Last
        and Entity (Req 5.4); replaces roles when supplied (Req 5.5); applies
        is_active (Req 5.6) and the AD toggle (Req 5.8); and applies the
        change-password rules (Req 5.9–5.11).
        """
        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            raise MasterNotFoundError("User", user_id)

        supplied = request.model_fields_set

        if "entity_id" in supplied:
            await self._validate_active_entity(request.entity_id)
            # Write entity_id to user_details (not users table per updated design)
            await self._update_entity_in_details(user_id, request.entity_id, actor.username)

        # Effective AD flag after this edit governs password handling.
        effective_ad = (
            request.is_validate_ad if request.is_validate_ad is not None else user.is_validate_ad
        )
        if request.is_validate_ad is not None:
            user.is_validate_ad = request.is_validate_ad

        # Change-password rules (Req 5.9–5.11). An empty/omitted value leaves the
        # password unchanged; a non-empty value only takes effect when AD is off.
        if request.change_password and not effective_ad:
            user.password_hash = hash_password(request.change_password)

        if request.is_active is not None:
            user.is_active = request.is_active

        if request.is_blocked is not None:
            user.is_blocked = request.is_blocked

        user.mark_modified(actor.username)
        updated = await self._user_repo.update(user)

        # Update mutable employee detail fields (Req 5.4).
        await self._update_user_details(
            user_id=user_id,
            supplied=supplied,
            email=request.email,
            first_name=request.first_name,
            last_name=request.last_name,
            actor_username=actor.username,
        )

        # Replace roles only when a role set was explicitly supplied (Req 5.5).
        if request.role_ids is not None:
            await self._validate_roles_exist(request.role_ids)
            await self._replace_roles(user_id, request.role_ids, actor.username)

        return self._to_response(updated)

    # ─── HR Import (Requirement 3) ───

    async def import_users(self, rows: list[HrImportRow], actor: User) -> ImportSummary:
        """Import/upsert users from the HR system.

        For each row: resolve the Entity by Company Code when non-empty else by
        Entity Name (Req 3.2), creating it when absent (Req 3.3) or linking the
        existing one (Req 3.4); upsert the user keyed by Employee ID (Req 3.6).
        A row supplying neither Company Code nor Entity Name is rejected with a
        row-level error and the batch continues (Req 3.5); any other row failure
        is likewise isolated so the remaining rows still process.
        """
        summary = ImportSummary(received=len(rows))

        for index, row in enumerate(rows, start=1):
            try:
                outcome = await self._import_single_row(row, actor)
                if outcome == "created":
                    summary.created += 1
                else:
                    summary.updated += 1
            except (MasterValidationError, MasterConflictError) as exc:
                summary.failed += 1
                summary.errors.append(
                    ImportRowError(
                        row_number=index,
                        employee_id=(row.employee_id or None),
                        reason=str(exc),
                    )
                )

        return summary

    async def _import_single_row(self, row: HrImportRow, actor: User) -> str:
        """Process a single HR import row.

        Returns ``"created"`` or ``"updated"`` on success and raises
        ``MasterValidationError``/``MasterConflictError`` for a row that cannot
        be imported (e.g. unresolvable entity), so the caller can isolate it.
        """
        employee_id = (row.employee_id or "").strip()
        if not employee_id:
            raise MasterValidationError("employee_id", "Employee ID is required")

        company_code = (row.company_code or "").strip()
        entity_name = (row.entity_name or "").strip()
        if not company_code and not entity_name:
            raise MasterValidationError(
                "entity",
                "Row supplies neither a Company Code nor an Entity Name",
            )

        entity = await self._resolve_or_create_entity(company_code, entity_name, actor)

        existing_user_id = await self._get_user_id_by_employee_id(employee_id)

        if existing_user_id is None:
            await self._create_imported_user(row, employee_id, entity, actor)
            return "created"

        await self._update_imported_user(existing_user_id, row, entity, actor)
        return "updated"

    async def _resolve_or_create_entity(
        self, company_code: str, entity_name: str, actor: User
    ) -> EntityEntity:
        """Resolve the Entity by Company Code else Entity Name, creating it when
        absent (Req 3.2, 3.3, 3.4)."""
        entity: EntityEntity | None = None
        if company_code:
            entity = await self._entity_repo.get_by_company_code(company_code)
        elif entity_name:
            entity = await self._entity_repo.get_by_name(entity_name)

        if entity is not None:
            return entity

        # Create the missing entity, reusing EntityService validation/uniqueness.
        entity_service = EntityService(self._session, self._entity_repo)
        return await entity_service.create_entity(
            EntityCreateInput(
                entity_name=entity_name or company_code,
                company_code=company_code or None,
            ),
            actor,
        )

    async def _create_imported_user(
        self, row: HrImportRow, employee_id: str, entity: EntityEntity, actor: User
    ) -> None:
        username = (row.username or employee_id).strip() or employee_id
        if await self._user_repo.exists_by_username(username):
            raise MasterConflictError(
                f"A user with User Name '{username}' already exists"
            )

        user = User(
            id=uuid4(),
            username=username,
            password_hash=self._unusable_password_hash(),
            is_validate_ad=row.is_validate_ad,
            created_by=actor.username,
            modified_by=actor.username,
        )
        created = await self._user_repo.create(user)
        self._add_user_details(
            user_id=created.id,
            employee_id=employee_id,
            email=row.email,
            first_name=row.first_name,
            last_name=row.last_name,
            actor_username=actor.username,
        )
        # Store entity_id in user_details
        await self._update_entity_in_details(created.id, entity.id, actor.username)

    async def _update_imported_user(
        self, user_id: UUID, row: HrImportRow, entity: EntityEntity, actor: User
    ) -> None:
        user = await self._user_repo.get_by_id(user_id)
        if user is None:  # pragma: no cover - resolved id should exist
            raise MasterNotFoundError("User", user_id)
        user.is_validate_ad = row.is_validate_ad
        user.mark_modified(actor.username)
        await self._user_repo.update(user)

        await self._upsert_user_details(
            user_id=user_id,
            employee_id=row.employee_id.strip(),
            email=row.email,
            first_name=row.first_name,
            last_name=row.last_name,
            actor_username=actor.username,
        )
        # Store entity_id in user_details
        await self._update_entity_in_details(user_id, entity.id, actor.username)

    # ─── Get Full Details ───

    async def get_user_details(self, user_id: UUID) -> UserDetailResponse:
        """Get full user profile including all employee AD fields."""
        stmt = (
            select(UserModel, UserDetailsModel)
            .outerjoin(UserDetailsModel, UserDetailsModel.user_id == UserModel.id)
            .where(UserModel.id == user_id)
        )
        result = await self._session.execute(stmt)
        row = result.one_or_none()

        if not row:
            raise ValueError("User not found")

        user_model, details = row

        return UserDetailResponse(
            id=user_model.id,
            username=user_model.username,
            is_active=user_model.is_active,
            is_blocked=user_model.is_blocked,
            is_validate_ad=user_model.is_validate_ad,
            entity_id=details.entity_id if details else None,
            employee_id=details.employee_id if details else None,
            employee_name=details.employee_name if details else None,
            first_name=details.first_name if details else None,
            middle_name=details.middle_name if details else None,
            last_name=details.last_name if details else None,
            email=details.email if details else None,
            designation_title=details.designation_title if details else None,
            department=details.department if details else None,
            business_unit=details.business_unit if details else None,
            group_company=details.group_company if details else None,
            location=details.location if details else None,
            region=details.region if details else None,
            zone=details.zone if details else None,
            grade=details.grade if details else None,
            office_mobile_no=details.office_mobile_no if details else None,
            personal_mobile_no=details.personal_mobile_no if details else None,
            date_of_joining=details.date_of_joining if details else None,
            reporting_manager=details.reporting_manager if details else None,
            direct_manager_employee_id=details.direct_manager_employee_id if details else None,
            direct_manager_name=details.direct_manager_name if details else None,
            direct_manager_email=details.direct_manager_email if details else None,
            sap_user_id=details.sap_user_id if details else None,
            division_id=details.division_id if details else None,
            territory_id=details.territory_id if details else None,
            created_by=user_model.created_by,
            created_date=user_model.created_date,
            modified_by=user_model.modified_by,
            modified_date=user_model.modified_date,
        )

    # ─── Get User Roles ───

    async def get_user_roles(self, user_id: UUID) -> dict:
        """Get all roles and their permissions assigned to a user."""
        stmt = (
            select(RoleAssignmentModel)
            .where(
                RoleAssignmentModel.user_id == str(user_id),
                RoleAssignmentModel.is_active == True,  # noqa: E712
            )
        )
        result = await self._session.execute(stmt)
        assignments = result.scalars().all()

        if not assignments:
            return {"user_id": str(user_id), "roles": []}

        role_ids = [a.role_id for a in assignments]

        role_stmt = (
            select(RoleModel)
            .options(selectinload(RoleModel.permissions))
            .where(RoleModel.id.in_(role_ids), RoleModel.is_active == True)  # noqa: E712
        )
        role_result = await self._session.execute(role_stmt)
        roles = role_result.scalars().all()

        return {
            "user_id": str(user_id),
            "roles": [
                {
                    "id": str(role.id),
                    "code": role.code,
                    "name": role.name,
                    "permissions": [
                        {
                            "code": p.code,
                            "name": p.name,
                            "scope": p.scope,
                            "resource": p.resource,
                            "action": p.action,
                        }
                        for p in role.permissions if p.is_active
                    ],
                }
                for role in roles
            ],
        }

    # ─── Get Login History ───

    async def get_login_history(self, user_id: UUID, limit: int = 20) -> list[dict]:
        """Get login/logout audit trail for a user."""
        stmt = (
            select(AuditLogModel)
            .where(
                AuditLogModel.resource_type == "Authentication",
                AuditLogModel.actor_id == str(user_id),
            )
            .order_by(AuditLogModel.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        entries = result.scalars().all()

        if not entries:
            user_model = await self._session.get(UserModel, str(user_id))
            if user_model:
                stmt2 = (
                    select(AuditLogModel)
                    .where(
                        AuditLogModel.resource_type == "Authentication",
                        AuditLogModel.actor_username == user_model.username,
                    )
                    .order_by(AuditLogModel.created_at.desc())
                    .limit(limit)
                )
                result = await self._session.execute(stmt2)
                entries = result.scalars().all()

        return [
            {
                "action": e.action,
                "ip_address": e.ip_address,
                "user_agent": e.user_agent,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in entries
        ]

    # ─── Private Helpers ───

    async def _get_last_logins(self, user_ids: list[str]) -> dict[str, str]:
        """Batch fetch last login timestamps from audit_logs."""
        if not user_ids:
            return {}

        stmt = (
            select(
                AuditLogModel.actor_id,
                func.max(AuditLogModel.created_at).label("last_login"),
            )
            .where(
                AuditLogModel.action == "LOGIN_SUCCESS",
                AuditLogModel.actor_id.in_(user_ids),
            )
            .group_by(AuditLogModel.actor_id)
        )
        result = await self._session.execute(stmt)
        return {str(row[0]): row[1] for row in result.all()}

    async def _employee_id_exists(self, employee_id: str) -> bool:
        """True when a user_details row already uses this Employee ID."""
        stmt = select(UserDetailsModel.id).where(
            UserDetailsModel.employee_id == employee_id
        )
        result = await self._session.execute(stmt)
        return result.first() is not None

    async def _get_user_id_by_employee_id(self, employee_id: str) -> UUID | None:
        """Resolve the owning user id for an Employee ID, or None."""
        stmt = select(UserDetailsModel.user_id).where(
            UserDetailsModel.employee_id == employee_id
        )
        result = await self._session.execute(stmt)
        user_id = result.scalar_one_or_none()
        if user_id is None:
            return None
        return user_id if isinstance(user_id, UUID) else UUID(str(user_id))

    async def _validate_active_entity(self, entity_id: UUID | None) -> None:
        """Reject when a supplied Entity reference is missing or inactive
        (Req 4.5, 5.3)."""
        if entity_id is None:
            return
        entity = await self._entity_repo.get_by_id(entity_id)
        if entity is None or not entity.is_active:
            raise MasterValidationError(
                "entity_id",
                "Entity reference must be an existing active Entity",
            )

    async def _validate_roles_exist(self, role_ids: list[UUID]) -> None:
        """Reject when any supplied Role does not exist (Req 4.6)."""
        if not role_ids:
            return
        unique_ids = {str(r) for r in role_ids}
        stmt = select(RoleModel.id).where(RoleModel.id.in_(list(unique_ids)))
        result = await self._session.execute(stmt)
        found = {str(r) for r in result.scalars().all()}
        missing = unique_ids - found
        if missing:
            raise MasterValidationError(
                "role_ids",
                f"Unknown role(s): {', '.join(sorted(missing))}",
            )

    def _resolve_create_password(self, request: CreateUserRequest) -> str:
        """Validate/resolve the password hash for a new user (Req 4.4, 4.7)."""
        if request.is_validate_ad:
            return self._unusable_password_hash()
        if not request.password:
            raise MasterValidationError(
                "password",
                "Password is required when Validate-with-AD is disabled",
            )
        return hash_password(request.password)

    @staticmethod
    def _unusable_password_hash() -> str:
        """A valid bcrypt hash of a random secret — never matches any password.

        Used for AD-authenticated users that have no local password (Req 4.7).
        """
        return hash_password(uuid4().hex)

    def _add_user_details(
        self,
        user_id: UUID,
        employee_id: str,
        email: str | None,
        first_name: str | None,
        last_name: str | None,
        actor_username: str,
    ) -> None:
        """Insert a user_details row carrying the supplied employee fields."""
        first = (first_name or "").strip()
        last = (last_name or "").strip()
        details = UserDetailsModel(
            id=uuid4(),
            user_id=user_id,
            employee_id=employee_id,
            employee_name=f"{first} {last}".strip(),
            first_name=first,
            last_name=last,
            email=(email or "").strip(),
            created_by=actor_username,
            modified_by=actor_username,
        )
        self._session.add(details)

    async def _update_user_details(
        self,
        user_id: UUID,
        supplied: set[str],
        email: str | None,
        first_name: str | None,
        last_name: str | None,
        actor_username: str,
    ) -> None:
        """Apply supplied mutable employee fields to the user_details row."""
        if not ({"email", "first_name", "last_name"} & supplied):
            return

        details = await self._get_user_details_model(user_id)
        if details is None:
            self._add_user_details(
                user_id=user_id,
                employee_id="",
                email=email,
                first_name=first_name,
                last_name=last_name,
                actor_username=actor_username,
            )
            return

        if "email" in supplied:
            details.email = (email or "").strip()
        if "first_name" in supplied:
            details.first_name = (first_name or "").strip()
        if "last_name" in supplied:
            details.last_name = (last_name or "").strip()
        details.employee_name = f"{details.first_name} {details.last_name}".strip()
        details.modified_by = actor_username

    async def _update_entity_in_details(
        self,
        user_id: UUID,
        entity_id: "UUID | None",
        actor_username: str,
    ) -> None:
        """Write entity_id to the user_details row (not the users table)."""
        details = await self._get_user_details_model(user_id)
        if details is None:
            # No user_details row yet — create a minimal one with entity_id
            details = UserDetailsModel(
                id=uuid4(),
                user_id=user_id,
                entity_id=entity_id,
                employee_id="",
                employee_name="",
                created_by=actor_username,
                modified_by=actor_username,
            )
            self._session.add(details)
        else:
            details.entity_id = entity_id
            details.modified_by = actor_username

    async def _upsert_user_details(
        self,
        user_id: UUID,
        employee_id: str,
        email: str | None,
        first_name: str | None,
        last_name: str | None,
        actor_username: str,
    ) -> None:
        """Create or refresh a user_details row during HR import."""
        details = await self._get_user_details_model(user_id)
        if details is None:
            self._add_user_details(
                user_id=user_id,
                employee_id=employee_id,
                email=email,
                first_name=first_name,
                last_name=last_name,
                actor_username=actor_username,
            )
            return

        if email is not None:
            details.email = email.strip()
        if first_name is not None:
            details.first_name = first_name.strip()
        if last_name is not None:
            details.last_name = last_name.strip()
        details.employee_name = f"{details.first_name} {details.last_name}".strip()
        details.modified_by = actor_username

    async def _get_user_details_model(self, user_id: UUID) -> UserDetailsModel | None:
        stmt = select(UserDetailsModel).where(UserDetailsModel.user_id == user_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def _assign_roles(
        self, user_id: UUID, role_ids: list[UUID], actor_username: str
    ) -> None:
        """Create active role assignments for each supplied role (Req 4.9, 4.10)."""
        for role_id in role_ids:
            assignment = RoleAssignmentModel(
                id=uuid4(),
                user_id=str(user_id),
                role_id=str(role_id),
                tenant_id=None,
                is_active=True,
                created_by=actor_username,
                modified_by=actor_username,
            )
            self._session.add(assignment)

    async def _replace_roles(
        self, user_id: UUID, role_ids: list[UUID], actor_username: str
    ) -> None:
        """Replace all existing role assignments with the supplied set (Req 5.5)."""
        existing_stmt = select(RoleAssignmentModel).where(
            RoleAssignmentModel.user_id == str(user_id),
            RoleAssignmentModel.is_active == True,  # noqa: E712
        )
        existing_result = await self._session.execute(existing_stmt)
        for assignment in existing_result.scalars().all():
            assignment.is_active = False
            assignment.modified_by = actor_username

        await self._assign_roles(user_id, role_ids, actor_username)

    @staticmethod
    def _to_response(user: User) -> UserResponse:
        """Map domain entity to response DTO."""
        return UserResponse(
            id=user.id,
            username=user.username,
            is_active=user.is_active,
            is_blocked=user.is_blocked,
            is_validate_ad=user.is_validate_ad,
            created_by=user.created_by,
            created_date=user.created_date,
            modified_by=user.modified_by,
            modified_date=user.modified_date,
        )

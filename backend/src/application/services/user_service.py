"""
User Application Service.
Orchestrates user business logic — CRUD, role assignment, details, history.

Depends only on domain ports: no SQLAlchemy session and no ORM models, so the
application layer stays free of infrastructure.
"""

from typing import Any

from src.api.v1.schemas.user_request import CreateUserRequest, UpdateUserRequest
from src.api.v1.schemas.user_response import UserDetailResponse, UserListResponse, UserResponse
from src.domain.entities.audit_log import AuditAction
from src.domain.entities.role import RoleAssignment
from src.domain.entities.user import User
from src.domain.entities.user_details import UserDetails
from src.domain.repositories.audit_log_repository import IAuditLogRepository
from src.domain.repositories.role_assignment_repository import IRoleAssignmentRepository
from src.domain.repositories.role_repository import IRoleRepository
from src.domain.repositories.user_details_repository import IUserDetailsRepository
from src.domain.repositories.user_repository import IUserRepository
from src.domain.services.password_hasher import IPasswordHasher

AUTHENTICATION_RESOURCE = "Authentication"


class UserService:
    """
    Application service for user management.

    Responsibilities:
    - Orchestrate user CRUD operations
    - Manage role assignments
    - Aggregate data from multiple sources (users, user details, audit trail)
    """

    def __init__(
        self,
        user_repo: IUserRepository,
        user_details_repo: IUserDetailsRepository,
        role_repo: IRoleRepository,
        assignment_repo: IRoleAssignmentRepository,
        audit_repo: IAuditLogRepository,
        password_hasher: IPasswordHasher,
    ) -> None:
        self._users = user_repo
        self._details = user_details_repo
        self._roles = role_repo
        self._assignments = assignment_repo
        self._audit = audit_repo
        self._hasher = password_hasher

    # ─── List Users ───

    async def list_users(self, skip: int = 0, limit: int = 100) -> UserListResponse:
        """Get a page of users decorated with employee details and last login."""
        users = await self._users.list_all(skip=skip, limit=limit)
        user_ids = [u.id for u in users]

        details = await self._details.get_many_by_user_ids(user_ids)
        last_logins = await self._audit.latest_timestamp_by_actor(
            str(AuditAction.LOGIN_SUCCESS), user_ids
        )

        return UserListResponse(
            users=[
                self._to_response(
                    user,
                    details=details.get(user.id),
                    last_login=last_logins.get(user.id),
                )
                for user in users
            ],
            total=len(users),
            skip=skip,
            limit=limit,
        )

    # ─── Create User ───

    async def create_user(self, request: CreateUserRequest, actor: User) -> UserResponse:
        """Create a new user and optionally assign a role."""
        if await self._users.exists_by_username(request.username):
            raise ValueError(f"Username '{request.username}' already exists")

        user = User(
            username=request.username,
            password_hash=self._hasher.hash(request.password),
            is_validate_ad=request.is_validate_ad,
            created_by=actor.username,
            modified_by=actor.username,
        )

        created = await self._users.create(user)

        if request.role_id:
            await self._assign_role(created.id, request.role_id, actor.username)

        return self._to_response(created)

    # ─── Get User by ID ───

    async def get_user(self, user_id: int) -> User:
        """Get a user by ID. Raises ValueError if not found."""
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise ValueError("User not found")
        return user

    # ─── Update User ───

    async def update_user(
        self, user_id: int, request: UpdateUserRequest, actor: User
    ) -> UserResponse:
        """Update user properties and optionally reassign role."""
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise ValueError("User not found")

        if request.is_active is not None:
            user.is_active = request.is_active
        if request.is_blocked is not None:
            user.is_blocked = request.is_blocked
        if request.is_validate_ad is not None:
            user.is_validate_ad = request.is_validate_ad

        user.mark_modified(actor.username)
        updated = await self._users.update(user)

        # Replace any existing assignment when a role is supplied.
        if request.role_id is not None:
            await self._assignments.deactivate_all_for_user(user_id, actor.username)
            await self._assign_role(user_id, request.role_id, actor.username)

        return self._to_response(updated)

    # ─── Get Full Details ───

    async def get_user_details(self, user_id: int) -> UserDetailResponse:
        """Get full user profile including all employee AD fields."""
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise ValueError("User not found")

        details = await self._details.get_by_user_id(user_id)

        return UserDetailResponse(
            id=user.id,
            username=user.username,
            is_active=user.is_active,
            is_blocked=user.is_blocked,
            is_validate_ad=user.is_validate_ad,
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
            direct_manager_employee_id=(
                details.direct_manager_employee_id if details else None
            ),
            direct_manager_name=details.direct_manager_name if details else None,
            direct_manager_email=details.direct_manager_email if details else None,
            sap_user_id=details.sap_user_id if details else None,
            division_id=details.division_id if details else None,
            territory_id=details.territory_id if details else None,
            created_by=user.created_by,
            created_date=user.created_date,
            modified_by=user.modified_by,
            modified_date=user.modified_date,
        )

    # ─── Get User Roles ───

    async def get_user_roles(self, user_id: int) -> dict[str, Any]:
        """Get all active roles and their permissions assigned to a user."""
        assignments = await self._assignments.list_active_for_user(user_id)
        if not assignments:
            return {"user_id": user_id, "roles": []}

        roles = await self._roles.list_by_ids([a.role_id for a in assignments])

        return {
            "user_id": user_id,
            "roles": [
                {
                    "id": role.id,
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
                        for p in role.permissions
                        if p.is_active
                    ],
                }
                for role in roles
                if role.is_active
            ],
        }

    # ─── Get Login History ───

    async def get_login_history(
        self, user_id: int, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Get the login/logout audit trail for a user."""
        entries = await self._audit.query(
            resource_type=AUTHENTICATION_RESOURCE, actor_id=user_id, limit=limit
        )

        # Older entries recorded failed logins against the username only, with
        # no actor_id, so fall back to matching on the username.
        if not entries:
            user = await self._users.get_by_id(user_id)
            if user:
                entries = await self._audit.query(
                    resource_type=AUTHENTICATION_RESOURCE,
                    actor_username=user.username,
                    limit=limit,
                )

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

    async def _assign_role(
        self, user_id: int, role_id: int, actor_username: str
    ) -> None:
        """Assign a single role to a user."""
        await self._assignments.create(
            RoleAssignment(
                user_id=user_id,
                role_id=role_id,
                tenant_id=None,
                is_active=True,
                created_by=actor_username,
                modified_by=actor_username,
            )
        )

    @staticmethod
    def _to_response(
        user: User,
        *,
        details: UserDetails | None = None,
        last_login: Any = None,
    ) -> UserResponse:
        """Map domain entity to response DTO."""
        return UserResponse(
            id=user.id,
            username=user.username,
            is_active=user.is_active,
            is_blocked=user.is_blocked,
            is_validate_ad=user.is_validate_ad,
            employee_id=details.employee_id if details else None,
            employee_name=details.employee_name if details else None,
            email=details.email if details else None,
            last_login=last_login,
            created_by=user.created_by,
            created_date=user.created_date,
            modified_by=user.modified_by,
            modified_date=user.modified_date,
        )

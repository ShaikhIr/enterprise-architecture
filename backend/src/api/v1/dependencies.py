"""
FastAPI dependency injection for API v1.
Provides current user resolution from JWT tokens and service factories.
"""

from typing import TYPE_CHECKING

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.employee_import_writer import IEmployeeImportWriter
from src.domain.entities.user import User
from src.domain.repositories.approval_matrix_repository import IApprovalMatrixRepository
from src.domain.repositories.audit_log_repository import IAuditLogRepository
from src.domain.repositories.category_of_law_repository import ICategoryOfLawRepository
from src.domain.repositories.country_repository import ICountryRepository
from src.domain.repositories.legislation_repository import ILegislationRepository
from src.domain.repositories.permission_repository import IPermissionRepository
from src.domain.repositories.role_assignment_repository import IRoleAssignmentRepository
from src.domain.repositories.role_repository import IRoleRepository
from src.domain.repositories.rule_repository import IRuleRepository
from src.domain.repositories.state_repository import IStateRepository
from src.domain.repositories.task_type_repository import ITaskTypeRepository
from src.domain.repositories.user_details_repository import IUserDetailsRepository
from src.domain.repositories.user_repository import IUserRepository
from src.domain.repositories.workflow_definition_repository import (
    IWorkflowDefinitionRepository,
)
from src.domain.repositories.workflow_instance_repository import (
    IWorkflowInstanceRepository,
)
from src.domain.services.password_hasher import IPasswordHasher
from src.domain.services.permission_resolver import IPermissionResolver
from src.infrastructure.database.audit_context import set_audit_actor
from src.infrastructure.database.repositories.approval_matrix_repository_impl import (
    ApprovalMatrixRepositoryImpl,
)
from src.infrastructure.database.repositories.audit_log_repository_impl import (
    AuditLogRepositoryImpl,
)
from src.infrastructure.database.repositories.category_of_law_repository_impl import (
    CategoryOfLawRepositoryImpl,
)
from src.infrastructure.database.repositories.country_repository_impl import (
    CountryRepositoryImpl,
)
from src.infrastructure.database.repositories.legislation_repository_impl import (
    LegislationRepositoryImpl,
)
from src.infrastructure.database.repositories.permission_repository_impl import (
    PermissionRepositoryImpl,
)
from src.infrastructure.database.repositories.role_assignment_repository_impl import (
    RoleAssignmentRepositoryImpl,
)
from src.infrastructure.database.repositories.role_repository_impl import (
    RoleRepositoryImpl,
)
from src.infrastructure.database.repositories.rule_repository_impl import (
    RuleRepositoryImpl,
)
from src.infrastructure.database.repositories.state_repository_impl import (
    StateRepositoryImpl,
)
from src.infrastructure.database.repositories.task_type_repository_impl import (
    TaskTypeRepositoryImpl,
)
from src.infrastructure.database.repositories.user_details_repository_impl import (
    UserDetailsRepositoryImpl,
)
from src.infrastructure.database.repositories.user_repository_impl import (
    UserRepositoryImpl,
)
from src.infrastructure.database.repositories.workflow_definition_repository_impl import (
    WorkflowDefinitionRepositoryImpl,
)
from src.infrastructure.database.repositories.workflow_instance_repository_impl import (
    WorkflowInstanceRepositoryImpl,
)
from src.infrastructure.database.session import get_db_session
from src.infrastructure.security.auth_manager import AuthManager
from src.infrastructure.security.jwt_provider import JWTProvider
from src.infrastructure.security.password_hasher_impl import BcryptPasswordHasher

if TYPE_CHECKING:
    # Only for the return-type annotation on get_audit_service, which imports AuditService
    # lazily inside the function body — matching get_permission_resolver's existing pattern
    # for PermissionManager below, rather than adding it to this file's module-level imports.
    from src.infrastructure.security.audit_service import AuditService

# Bearer token extraction scheme (enables Swagger "Authorize" button)
#
# auto_error=False so that a missing Authorization header reaches get_current_user and is
# answered with 401. Left to itself, HTTPBearer answers 403, which reads as "authenticated
# but not allowed" and is not something a client should retry. The SPA holds its access
# token in memory only, so the first requests after a page reload legitimately arrive
# without one; they need the 401 that tells the client to refresh and try again.
bearer_scheme = HTTPBearer(auto_error=False)


def get_jwt_provider() -> JWTProvider:
    """Provide JWT provider instance."""
    return JWTProvider()


def get_user_repository(
    session: AsyncSession = Depends(get_db_session),
) -> IUserRepository:
    """Provide user repository with injected session."""
    return UserRepositoryImpl(session)


def get_country_repository(
    session: AsyncSession = Depends(get_db_session),
) -> ICountryRepository:
    """Provide country repository with injected session."""
    return CountryRepositoryImpl(session)


def get_state_repository(
    session: AsyncSession = Depends(get_db_session),
) -> IStateRepository:
    """Provide state repository with injected session."""
    return StateRepositoryImpl(session)


def get_category_of_law_repository(
    session: AsyncSession = Depends(get_db_session),
) -> ICategoryOfLawRepository:
    """Provide category of law repository with injected session."""
    return CategoryOfLawRepositoryImpl(session)


def get_legislation_repository(
    session: AsyncSession = Depends(get_db_session),
) -> ILegislationRepository:
    """Provide legislation repository with injected session."""
    return LegislationRepositoryImpl(session)


def get_rule_repository(
    session: AsyncSession = Depends(get_db_session),
) -> IRuleRepository:
    """Provide rule repository with injected session."""
    return RuleRepositoryImpl(session)


def get_task_type_repository(
    session: AsyncSession = Depends(get_db_session),
) -> ITaskTypeRepository:
    """Provide task type repository with injected session."""
    return TaskTypeRepositoryImpl(session)


def get_workflow_definition_repository(
    session: AsyncSession = Depends(get_db_session),
) -> IWorkflowDefinitionRepository:
    """Provide workflow definition repository with injected session."""
    return WorkflowDefinitionRepositoryImpl(session)


def get_workflow_instance_repository(
    session: AsyncSession = Depends(get_db_session),
) -> IWorkflowInstanceRepository:
    """Provide workflow instance repository with injected session."""
    return WorkflowInstanceRepositoryImpl(session)


def get_approval_matrix_repository(
    session: AsyncSession = Depends(get_db_session),
) -> IApprovalMatrixRepository:
    """Provide approval matrix repository with injected session."""
    return ApprovalMatrixRepositoryImpl(session)


def get_permission_repository(
    session: AsyncSession = Depends(get_db_session),
) -> IPermissionRepository:
    """Provide permission repository with injected session."""
    return PermissionRepositoryImpl(session)


def get_role_repository(
    session: AsyncSession = Depends(get_db_session),
) -> IRoleRepository:
    """Provide role repository with injected session."""
    return RoleRepositoryImpl(session)


def get_role_assignment_repository(
    session: AsyncSession = Depends(get_db_session),
) -> IRoleAssignmentRepository:
    """Provide role assignment repository with injected session."""
    return RoleAssignmentRepositoryImpl(session)


def get_audit_log_repository(
    session: AsyncSession = Depends(get_db_session),
) -> IAuditLogRepository:
    """Provide audit log repository with injected session."""
    return AuditLogRepositoryImpl(session)


def get_permission_resolver(
    session: AsyncSession = Depends(get_db_session),
) -> IPermissionResolver:
    """Provide the effective-permission read model with injected session."""
    from src.infrastructure.security.permission_manager import PermissionManager

    return PermissionManager(session)


def get_user_details_repository(
    session: AsyncSession = Depends(get_db_session),
) -> IUserDetailsRepository:
    """Provide user details repository with injected session."""
    return UserDetailsRepositoryImpl(session)


def get_audit_service(session: AsyncSession = Depends(get_db_session)) -> "AuditService":
    """
    Provide the audit-writing service with injected session.

    Same shape as `get_permission_resolver`: an infrastructure adapter that needs the
    request's session is built once here, so controllers depend on the factory instead
    of importing `AuditService` and constructing it inline.
    """
    from src.infrastructure.security.audit_service import AuditService

    return AuditService(session)


def get_employee_import_writer(
    session: AsyncSession = Depends(get_db_session),
    user_repo: IUserRepository = Depends(get_user_repository),
    user_details_repo: IUserDetailsRepository = Depends(get_user_details_repository),
) -> IEmployeeImportWriter:
    """
    Provide the employee-import writer, attached to the request's own session.

    `UnitOfWork.from_session(session)` rather than `UnitOfWork()`: the request-scoped
    session from `get_db_session` still owns the commit at the end of the request; this
    writer only needs `savepoint()` from the unit of work, not a second transaction.
    """
    from src.infrastructure.database.repositories.employee_import_writer_impl import (
        EmployeeImportWriterImpl,
    )
    from src.infrastructure.database.unit_of_work import UnitOfWork

    uow = UnitOfWork.from_session(session)
    return EmployeeImportWriterImpl(uow, user_repo, user_details_repo)


def get_password_hasher() -> IPasswordHasher:
    """Provide the password hashing service."""
    return BcryptPasswordHasher()


def get_auth_manager(
    user_repo: IUserRepository = Depends(get_user_repository),
    jwt_provider: JWTProvider = Depends(get_jwt_provider),
) -> AuthManager:
    """Provide authentication manager with dependencies."""
    return AuthManager(user_repository=user_repo, jwt_provider=jwt_provider)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    jwt_provider: JWTProvider = Depends(get_jwt_provider),
    user_repo: IUserRepository = Depends(get_user_repository),
) -> User:
    """
    Resolve the current authenticated user from the JWT access token.

    Raises:
        HTTPException 401: If token is missing, invalid, or expired.
        HTTPException 401: If user does not exist.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt_provider.verify_token(credentials.credentials, expected_type="access")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    user = await user_repo.get_by_username(payload.sub)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Attach the identity to the audit context so the SQLAlchemy audit listener
    # can attribute every write in this request without threading the user
    # through the service and repository signatures.
    #
    # This has to happen here rather than in AuditContextMiddleware: middleware
    # runs before dependencies, so it has no authenticated user to record. This
    # dependency shares a task context with the route handler and its database
    # session, so the value is visible at flush time.
    #
    # tenant_id is not set — users are not yet scoped to a tenant. Add it here
    # once UserModel carries one.
    set_audit_actor(actor_id=user.id, actor_username=user.username)

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Ensure the current user is active and not blocked.

    Raises:
        HTTPException 403: If user is inactive or blocked.
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )
    if current_user.is_blocked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is blocked",
        )
    return current_user

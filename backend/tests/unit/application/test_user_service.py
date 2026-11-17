"""
User service tests.

`UserService` hashes passwords, enforces username uniqueness, applies partial updates
and replaces a user's role, and assembles read models from four ports (users, employee
details, role assignments, audit trail). The repositories only run queries, so these
tests pin the rules down against in-memory fakes.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from rbac_fakes import (
    FakeAuditLogRepository,
    FakePasswordHasher,
    FakePermissionRepository,
    FakeRoleAssignmentStore,
    FakeRoleRepository,
)
from user_fakes import FakeUserDetailsRepository, FakeUserRepository

from src.api.v1.schemas.user_request import CreateUserRequest, UpdateUserRequest
from src.application.services.user_service import UserService
from src.domain.entities.audit_log import AuditAction, AuditLog
from src.domain.entities.role import Permission, Role, RoleAssignment
from src.domain.entities.user import User
from src.domain.entities.user_details import UserDetails


@pytest.fixture
def users() -> FakeUserRepository:
    return FakeUserRepository()


@pytest.fixture
def details() -> FakeUserDetailsRepository:
    return FakeUserDetailsRepository()


@pytest.fixture
def permissions() -> FakePermissionRepository:
    return FakePermissionRepository()


@pytest.fixture
def roles(permissions: FakePermissionRepository) -> FakeRoleRepository:
    return FakeRoleRepository(permissions)


@pytest.fixture
def assignments() -> FakeRoleAssignmentStore:
    return FakeRoleAssignmentStore()


@pytest.fixture
def audit() -> FakeAuditLogRepository:
    return FakeAuditLogRepository()


@pytest.fixture
def service(
    users: FakeUserRepository,
    details: FakeUserDetailsRepository,
    roles: FakeRoleRepository,
    assignments: FakeRoleAssignmentStore,
    audit: FakeAuditLogRepository,
) -> UserService:
    return UserService(users, details, roles, assignments, audit, FakePasswordHasher())


@pytest.fixture
def actor() -> User:
    return User(id=1, username="alice")


def make_user(username: str = "bob", **overrides: Any) -> User:
    return User(username=username, password_hash="hashed::pw", **overrides)


def make_role(code: str = "EDITOR", **overrides: Any) -> Role:
    return Role(code=code, name=code.title(), **overrides)


def create_request(**overrides: Any) -> CreateUserRequest:
    values: dict[str, Any] = {"username": "newuser", "password": "s3cretpass"}
    values.update(overrides)
    return CreateUserRequest(**values)


class TestListUsers:
    async def test_returns_every_user_with_paging_echo(
        self, service: UserService, users: FakeUserRepository
    ) -> None:
        users.add(make_user("u1"))
        users.add(make_user("u2"))

        result = await service.list_users()

        assert [u.username for u in result.users] == ["u1", "u2"]
        assert (result.skip, result.limit) == (0, 100)

    async def test_skip_and_limit_page_the_users(
        self, service: UserService, users: FakeUserRepository
    ) -> None:
        for name in ("u1", "u2", "u3"):
            users.add(make_user(name))

        result = await service.list_users(skip=1, limit=1)

        assert [u.username for u in result.users] == ["u2"]
        assert (result.skip, result.limit) == (1, 1)

    async def test_users_are_decorated_with_employee_details(
        self,
        service: UserService,
        users: FakeUserRepository,
        details: FakeUserDetailsRepository,
    ) -> None:
        with_details = users.add(make_user("u1"))
        users.add(make_user("u2"))
        details.add(
            UserDetails(
                user_id=with_details.id,
                employee_id="E100",
                employee_name="Una One",
                email="una@example.com",
            )
        )

        result = await service.list_users()

        first, second = result.users
        assert (first.employee_id, first.employee_name, first.email) == (
            "E100",
            "Una One",
            "una@example.com",
        )
        assert (second.employee_id, second.employee_name, second.email) == (None, None, None)

    async def test_users_are_decorated_with_their_latest_login(
        self,
        service: UserService,
        users: FakeUserRepository,
        audit: FakeAuditLogRepository,
    ) -> None:
        logged_in = users.add(make_user("u1"))
        never = users.add(make_user("u2"))
        older = datetime.now(UTC) - timedelta(days=2)
        newer = datetime.now(UTC) - timedelta(hours=1)
        for stamp in (older, newer):
            audit.seed(
                AuditLog(
                    actor_id=logged_in.id,
                    action=str(AuditAction.LOGIN_SUCCESS),
                    created_at=stamp,
                )
            )
        # A failed login must not count as the last login.
        audit.seed(
            AuditLog(
                actor_id=never.id,
                action=str(AuditAction.LOGIN_FAILED),
                created_at=datetime.now(UTC),
            )
        )

        result = await service.list_users()

        first, second = result.users
        assert first.last_login == newer
        assert second.last_login is None

    async def test_empty_directory_returns_an_empty_page(self, service: UserService) -> None:
        result = await service.list_users()

        assert result.users == []
        assert result.total == 0

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Suspected bug: UserService.list_users sets total=len(users), the size of "
            "the current page, not the number of matching users, so total is wrong "
            "whenever the directory is larger than the page."
        ),
    )
    async def test_total_counts_all_users_not_just_the_page(
        self, service: UserService, users: FakeUserRepository
    ) -> None:
        for name in ("u1", "u2", "u3"):
            users.add(make_user(name))

        result = await service.list_users(skip=0, limit=2)

        assert len(result.users) == 2
        assert result.total == 3


class TestCreateUser:
    async def test_creates_the_user_with_a_hashed_password(
        self, service: UserService, users: FakeUserRepository, actor: User
    ) -> None:
        response = await service.create_user(create_request(), actor)

        stored = await users.get_by_id(response.id)
        assert stored is not None
        assert stored.password_hash == "hashed::s3cretpass"
        assert stored.password_hash != "s3cretpass"

    async def test_response_reflects_the_new_user_and_actor(
        self, service: UserService, actor: User
    ) -> None:
        response = await service.create_user(
            create_request(username="carol", is_validate_ad=False), actor
        )

        assert response.id != 0
        assert response.username == "carol"
        assert response.is_active is True
        assert response.is_blocked is False
        assert response.is_validate_ad is False
        assert response.created_by == "alice"
        assert response.modified_by == "alice"

    async def test_is_validate_ad_defaults_to_true(
        self, service: UserService, actor: User
    ) -> None:
        response = await service.create_user(create_request(), actor)

        assert response.is_validate_ad is True

    async def test_duplicate_username_is_rejected(
        self, service: UserService, users: FakeUserRepository, actor: User
    ) -> None:
        users.add(make_user("newuser"))

        with pytest.raises(ValueError, match="Username 'newuser' already exists"):
            await service.create_user(create_request(), actor)

        assert len(users.rows) == 1

    async def test_duplicate_username_assigns_no_role(
        self,
        service: UserService,
        users: FakeUserRepository,
        roles: FakeRoleRepository,
        assignments: FakeRoleAssignmentStore,
        actor: User,
    ) -> None:
        users.add(make_user("newuser"))
        role = roles.add(make_role())

        with pytest.raises(ValueError):
            await service.create_user(create_request(role_id=role.id), actor)

        assert assignments.rows == {}

    async def test_no_role_id_creates_no_assignment(
        self, service: UserService, assignments: FakeRoleAssignmentStore, actor: User
    ) -> None:
        await service.create_user(create_request(), actor)

        assert assignments.rows == {}

    async def test_role_id_creates_an_active_assignment_for_the_new_user(
        self,
        service: UserService,
        roles: FakeRoleRepository,
        assignments: FakeRoleAssignmentStore,
        actor: User,
    ) -> None:
        role = roles.add(make_role())

        response = await service.create_user(create_request(role_id=role.id), actor)

        (assignment,) = assignments.rows.values()
        assert assignment.user_id == response.id
        assert assignment.role_id == role.id
        assert assignment.tenant_id is None
        assert assignment.is_active is True
        assert assignment.created_by == "alice"

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Suspected bug: create_user never checks that role_id exists (RbacService."
            "assign_role does), so an unknown role id is persisted as a dangling "
            "assignment and fails later as a database error instead of a clean ValueError."
        ),
    )
    async def test_unknown_role_is_rejected(
        self,
        service: UserService,
        assignments: FakeRoleAssignmentStore,
        actor: User,
    ) -> None:
        with pytest.raises(ValueError, match="Role not found"):
            await service.create_user(create_request(role_id=9999), actor)

        assert assignments.rows == {}


class TestGetUser:
    async def test_returns_the_user(
        self, service: UserService, users: FakeUserRepository
    ) -> None:
        user = users.add(make_user("bob"))

        found = await service.get_user(user.id)

        assert found.username == "bob"

    async def test_unknown_user_is_rejected(self, service: UserService) -> None:
        with pytest.raises(ValueError, match="User not found"):
            await service.get_user(999_999)


class TestUpdateUser:
    async def test_unknown_user_is_rejected(self, service: UserService, actor: User) -> None:
        with pytest.raises(ValueError, match="User not found"):
            await service.update_user(999_999, UpdateUserRequest(is_active=False), actor)

    async def test_unknown_user_touches_no_assignments(
        self,
        service: UserService,
        assignments: FakeRoleAssignmentStore,
        actor: User,
    ) -> None:
        stranger = assignments.add(RoleAssignment(user_id=999_999, role_id=5))

        with pytest.raises(ValueError):
            await service.update_user(999_999, UpdateUserRequest(role_id=6), actor)

        assert assignments.rows[stranger.id].is_active is True
        assert len(assignments.rows) == 1

    async def test_is_active_alone_changes_only_is_active(
        self, service: UserService, users: FakeUserRepository, actor: User
    ) -> None:
        user = users.add(make_user("bob", is_blocked=True, is_validate_ad=False))

        response = await service.update_user(
            user.id, UpdateUserRequest(is_active=False), actor
        )

        assert response.is_active is False
        assert response.is_blocked is True
        assert response.is_validate_ad is False

    async def test_is_blocked_alone_changes_only_is_blocked(
        self, service: UserService, users: FakeUserRepository, actor: User
    ) -> None:
        user = users.add(make_user("bob", is_validate_ad=False))

        response = await service.update_user(
            user.id, UpdateUserRequest(is_blocked=True), actor
        )

        assert response.is_blocked is True
        assert response.is_active is True
        assert response.is_validate_ad is False

    async def test_is_validate_ad_alone_changes_only_is_validate_ad(
        self, service: UserService, users: FakeUserRepository, actor: User
    ) -> None:
        user = users.add(make_user("bob", is_active=False, is_validate_ad=True))

        response = await service.update_user(
            user.id, UpdateUserRequest(is_validate_ad=False), actor
        )

        assert response.is_validate_ad is False
        assert response.is_active is False
        assert response.is_blocked is False

    async def test_false_is_applied_and_not_mistaken_for_omitted(
        self, service: UserService, users: FakeUserRepository, actor: User
    ) -> None:
        user = users.add(make_user("bob", is_blocked=True))

        response = await service.update_user(
            user.id, UpdateUserRequest(is_blocked=False), actor
        )

        assert response.is_blocked is False

    async def test_changes_are_persisted_and_stamp_the_actor(
        self, service: UserService, users: FakeUserRepository, actor: User
    ) -> None:
        user = users.add(make_user("bob"))

        await service.update_user(user.id, UpdateUserRequest(is_active=False), actor)

        stored = await users.get_by_id(user.id)
        assert stored is not None
        assert stored.is_active is False
        assert stored.modified_by == "alice"

    async def test_empty_request_changes_no_flags(
        self,
        service: UserService,
        users: FakeUserRepository,
        assignments: FakeRoleAssignmentStore,
        actor: User,
    ) -> None:
        user = users.add(make_user("bob"))
        existing = assignments.add(RoleAssignment(user_id=user.id, role_id=5))

        response = await service.update_user(user.id, UpdateUserRequest(), actor)

        assert (response.is_active, response.is_blocked, response.is_validate_ad) == (
            True,
            False,
            True,
        )
        assert assignments.rows[existing.id].is_active is True
        assert len(assignments.rows) == 1

    async def test_role_id_replaces_the_existing_assignment(
        self,
        service: UserService,
        users: FakeUserRepository,
        roles: FakeRoleRepository,
        assignments: FakeRoleAssignmentStore,
        actor: User,
    ) -> None:
        user = users.add(make_user("bob"))
        old_role = roles.add(make_role("OLD"))
        new_role = roles.add(make_role("NEW"))
        old = assignments.add(RoleAssignment(user_id=user.id, role_id=old_role.id))

        await service.update_user(user.id, UpdateUserRequest(role_id=new_role.id), actor)

        assert assignments.rows[old.id].is_active is False
        assert assignments.rows[old.id].modified_by == "alice"
        active = await assignments.list_active_for_user(user.id)
        assert [a.role_id for a in active] == [new_role.id]
        assert active[0].created_by == "alice"

    async def test_role_id_deactivates_every_prior_assignment(
        self,
        service: UserService,
        users: FakeUserRepository,
        assignments: FakeRoleAssignmentStore,
        actor: User,
    ) -> None:
        user = users.add(make_user("bob"))
        assignments.add(RoleAssignment(user_id=user.id, role_id=1))
        assignments.add(RoleAssignment(user_id=user.id, role_id=2))

        await service.update_user(user.id, UpdateUserRequest(role_id=3), actor)

        active = await assignments.list_active_for_user(user.id)
        assert [a.role_id for a in active] == [3]

    async def test_role_replacement_leaves_other_users_alone(
        self,
        service: UserService,
        users: FakeUserRepository,
        assignments: FakeRoleAssignmentStore,
        actor: User,
    ) -> None:
        user = users.add(make_user("bob"))
        other = users.add(make_user("carol"))
        theirs = assignments.add(RoleAssignment(user_id=other.id, role_id=1))

        await service.update_user(user.id, UpdateUserRequest(role_id=3), actor)

        assert assignments.rows[theirs.id].is_active is True

    async def test_reassigning_the_same_role_leaves_exactly_one_active_assignment(
        self,
        service: UserService,
        users: FakeUserRepository,
        assignments: FakeRoleAssignmentStore,
        actor: User,
    ) -> None:
        user = users.add(make_user("bob"))
        assignments.add(RoleAssignment(user_id=user.id, role_id=3))

        await service.update_user(user.id, UpdateUserRequest(role_id=3), actor)

        active = await assignments.list_active_for_user(user.id)
        assert [a.role_id for a in active] == [3]

    async def test_role_and_flags_can_change_together(
        self,
        service: UserService,
        users: FakeUserRepository,
        assignments: FakeRoleAssignmentStore,
        actor: User,
    ) -> None:
        user = users.add(make_user("bob"))

        response = await service.update_user(
            user.id, UpdateUserRequest(is_blocked=True, role_id=3), actor
        )

        assert response.is_blocked is True
        active = await assignments.list_active_for_user(user.id)
        assert [a.role_id for a in active] == [3]

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Suspected bug: update_user never checks that role_id exists. It first "
            "deactivates all of the user's assignments and then assigns the unknown "
            "role, so a bad id strips the user's access instead of failing cleanly."
        ),
    )
    async def test_unknown_role_is_rejected_and_existing_access_is_kept(
        self,
        service: UserService,
        users: FakeUserRepository,
        roles: FakeRoleRepository,
        assignments: FakeRoleAssignmentStore,
        actor: User,
    ) -> None:
        user = users.add(make_user("bob"))
        role = roles.add(make_role())
        assignments.add(RoleAssignment(user_id=user.id, role_id=role.id))

        with pytest.raises(ValueError, match="Role not found"):
            await service.update_user(user.id, UpdateUserRequest(role_id=9999), actor)

        active = await assignments.list_active_for_user(user.id)
        assert [a.role_id for a in active] == [role.id]


class TestGetUserDetails:
    async def test_unknown_user_is_rejected(self, service: UserService) -> None:
        with pytest.raises(ValueError, match="User not found"):
            await service.get_user_details(999_999)

    async def test_user_without_employee_details_has_none_for_every_detail_field(
        self, service: UserService, users: FakeUserRepository
    ) -> None:
        user = users.add(make_user("bob", is_blocked=True))

        result = await service.get_user_details(user.id)

        assert (result.id, result.username, result.is_blocked) == (user.id, "bob", True)
        assert result.employee_id is None
        assert result.first_name is None
        assert result.email is None
        assert result.territory_id is None

    async def test_employee_details_are_merged_into_the_profile(
        self,
        service: UserService,
        users: FakeUserRepository,
        details: FakeUserDetailsRepository,
    ) -> None:
        user = users.add(make_user("bob"))
        details.add(
            UserDetails(
                user_id=user.id,
                employee_id="E100",
                employee_name="Bob Builder",
                first_name="Bob",
                middle_name="The",
                last_name="Builder",
                email="bob@example.com",
                designation_title="Engineer",
                department="Ops",
                business_unit="BU1",
                group_company="GC",
                location="Pune",
                region="West",
                zone="Z1",
                grade="G5",
                office_mobile_no="111",
                personal_mobile_no="222",
                date_of_joining="2020-01-01",
                reporting_manager="Mia",
                direct_manager_employee_id="E1",
                direct_manager_name="Mia Manager",
                direct_manager_email="mia@example.com",
                sap_user_id="SAP1",
                division_id="D1",
                territory_id="T1",
            )
        )

        result = await service.get_user_details(user.id)

        assert result.employee_id == "E100"
        assert result.employee_name == "Bob Builder"
        assert (result.first_name, result.middle_name, result.last_name) == (
            "Bob",
            "The",
            "Builder",
        )
        assert result.email == "bob@example.com"
        assert result.designation_title == "Engineer"
        assert result.department == "Ops"
        assert result.business_unit == "BU1"
        assert result.group_company == "GC"
        assert (result.location, result.region, result.zone, result.grade) == (
            "Pune",
            "West",
            "Z1",
            "G5",
        )
        assert (result.office_mobile_no, result.personal_mobile_no) == ("111", "222")
        assert result.date_of_joining == "2020-01-01"
        assert result.reporting_manager == "Mia"
        assert result.direct_manager_employee_id == "E1"
        assert result.direct_manager_name == "Mia Manager"
        assert result.direct_manager_email == "mia@example.com"
        assert (result.sap_user_id, result.division_id, result.territory_id) == (
            "SAP1",
            "D1",
            "T1",
        )

    async def test_audit_fields_come_from_the_user(
        self, service: UserService, users: FakeUserRepository
    ) -> None:
        user = users.add(make_user("bob", created_by="seeder", modified_by="editor"))

        result = await service.get_user_details(user.id)

        assert (result.created_by, result.modified_by) == ("seeder", "editor")

    async def test_details_of_another_user_are_not_merged(
        self,
        service: UserService,
        users: FakeUserRepository,
        details: FakeUserDetailsRepository,
    ) -> None:
        user = users.add(make_user("bob"))
        other = users.add(make_user("carol"))
        details.add(UserDetails(user_id=other.id, employee_id="E999"))

        result = await service.get_user_details(user.id)

        assert result.employee_id is None


class TestGetUserRoles:
    async def test_user_without_assignments_has_no_roles(self, service: UserService) -> None:
        result = await service.get_user_roles(5)

        assert result == {"user_id": 5, "roles": []}

    async def test_returns_each_assigned_role_with_its_permissions(
        self,
        service: UserService,
        roles: FakeRoleRepository,
        permissions: FakePermissionRepository,
        assignments: FakeRoleAssignmentStore,
    ) -> None:
        role = roles.add(make_role("EDITOR"))
        perm = permissions.add(
            Permission(
                code="users.list",
                name="List users",
                scope="API",
                resource="users",
                action="READ",
            )
        )
        roles.link(role.id, perm.id)
        assignments.add(RoleAssignment(user_id=5, role_id=role.id))

        result = await service.get_user_roles(5)

        assert result == {
            "user_id": 5,
            "roles": [
                {
                    "id": role.id,
                    "code": "EDITOR",
                    "name": "Editor",
                    "permissions": [
                        {
                            "code": "users.list",
                            "name": "List users",
                            "scope": "API",
                            "resource": "users",
                            "action": "READ",
                        }
                    ],
                }
            ],
        }

    async def test_revoked_assignments_are_excluded(
        self,
        service: UserService,
        roles: FakeRoleRepository,
        assignments: FakeRoleAssignmentStore,
    ) -> None:
        active_role = roles.add(make_role("ACTIVE"))
        revoked_role = roles.add(make_role("REVOKED"))
        assignments.add(RoleAssignment(user_id=5, role_id=active_role.id))
        assignments.add(RoleAssignment(user_id=5, role_id=revoked_role.id, is_active=False))

        result = await service.get_user_roles(5)

        assert [r["code"] for r in result["roles"]] == ["ACTIVE"]

    async def test_inactive_roles_are_excluded(
        self,
        service: UserService,
        roles: FakeRoleRepository,
        assignments: FakeRoleAssignmentStore,
    ) -> None:
        live = roles.add(make_role("LIVE"))
        retired = roles.add(make_role("RETIRED", is_active=False))
        assignments.add(RoleAssignment(user_id=5, role_id=live.id))
        assignments.add(RoleAssignment(user_id=5, role_id=retired.id))

        result = await service.get_user_roles(5)

        assert [r["code"] for r in result["roles"]] == ["LIVE"]

    async def test_inactive_permissions_are_excluded_from_a_role(
        self,
        service: UserService,
        roles: FakeRoleRepository,
        permissions: FakePermissionRepository,
        assignments: FakeRoleAssignmentStore,
    ) -> None:
        role = roles.add(make_role("EDITOR"))
        live = permissions.add(Permission(code="a.live"))
        dead = permissions.add(Permission(code="a.dead", is_active=False))
        roles.link(role.id, live.id)
        roles.link(role.id, dead.id)
        assignments.add(RoleAssignment(user_id=5, role_id=role.id))

        result = await service.get_user_roles(5)

        assert [p["code"] for p in result["roles"][0]["permissions"]] == ["a.live"]

    async def test_other_users_roles_are_not_included(
        self,
        service: UserService,
        roles: FakeRoleRepository,
        assignments: FakeRoleAssignmentStore,
    ) -> None:
        role = roles.add(make_role("EDITOR"))
        assignments.add(RoleAssignment(user_id=6, role_id=role.id))

        result = await service.get_user_roles(5)

        assert result["roles"] == []


class TestGetLoginHistory:
    @staticmethod
    def _entry(
        *,
        actor_id: int | None,
        username: str = "bob",
        action: str = "LOGIN_SUCCESS",
        resource_type: str = "Authentication",
        minutes_ago: int = 0,
        ip: str = "10.0.0.1",
    ) -> AuditLog:
        return AuditLog(
            actor_id=actor_id,
            actor_username=username,
            action=action,
            resource_type=resource_type,
            ip_address=ip,
            user_agent="pytest",
            created_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
        )

    async def test_returns_the_users_authentication_entries_newest_first(
        self, service: UserService, audit: FakeAuditLogRepository
    ) -> None:
        old = self._entry(actor_id=5, action="LOGIN_FAILED", minutes_ago=60)
        new = self._entry(actor_id=5, action="LOGIN_SUCCESS", minutes_ago=1)
        audit.seed(old)
        audit.seed(new)

        history = await service.get_login_history(5)

        assert [h["action"] for h in history] == ["LOGIN_SUCCESS", "LOGIN_FAILED"]
        assert history[0] == {
            "action": "LOGIN_SUCCESS",
            "ip_address": "10.0.0.1",
            "user_agent": "pytest",
            "created_at": new.created_at.isoformat(),
        }

    async def test_other_users_and_other_resource_types_are_ignored(
        self, service: UserService, audit: FakeAuditLogRepository
    ) -> None:
        audit.seed(self._entry(actor_id=5))
        audit.seed(self._entry(actor_id=6))
        audit.seed(self._entry(actor_id=5, resource_type="Role"))

        history = await service.get_login_history(5)

        assert len(history) == 1

    async def test_limit_caps_the_number_of_entries(
        self, service: UserService, audit: FakeAuditLogRepository
    ) -> None:
        for minutes_ago in range(5):
            audit.seed(self._entry(actor_id=5, minutes_ago=minutes_ago))

        history = await service.get_login_history(5, limit=2)

        assert len(history) == 2

    async def test_default_limit_is_twenty(
        self, service: UserService, audit: FakeAuditLogRepository
    ) -> None:
        for minutes_ago in range(25):
            audit.seed(self._entry(actor_id=5, minutes_ago=minutes_ago))

        history = await service.get_login_history(5)

        assert len(history) == 20

    async def test_falls_back_to_the_username_for_legacy_entries_without_an_actor_id(
        self,
        service: UserService,
        users: FakeUserRepository,
        audit: FakeAuditLogRepository,
    ) -> None:
        user = users.add(make_user("bob"))
        audit.seed(self._entry(actor_id=None, username="bob", action="LOGIN_FAILED"))
        audit.seed(self._entry(actor_id=None, username="someone_else", action="LOGIN_FAILED"))

        history = await service.get_login_history(user.id)

        assert [h["action"] for h in history] == ["LOGIN_FAILED"]

    async def test_username_fallback_is_skipped_when_actor_id_entries_exist(
        self,
        service: UserService,
        users: FakeUserRepository,
        audit: FakeAuditLogRepository,
    ) -> None:
        user = users.add(make_user("bob"))
        audit.seed(self._entry(actor_id=user.id, action="LOGIN_SUCCESS"))
        audit.seed(self._entry(actor_id=None, username="bob", action="LOGIN_FAILED"))

        history = await service.get_login_history(user.id)

        assert [h["action"] for h in history] == ["LOGIN_SUCCESS"]

    async def test_unknown_user_with_no_entries_has_an_empty_history(
        self, service: UserService
    ) -> None:
        assert await service.get_login_history(999_999) == []

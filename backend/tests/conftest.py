"""
Root test configuration and shared fixtures.

Provides three layers of fixtures:

1. Entity fixtures (`sample_user`, ...) — pure in-memory domain objects.
2. Database fixtures (`db_session`) — a real Postgres transaction that is
   rolled back after every test, so tests never see each other's writes.
3. API fixtures (`client`, `admin_client`) — httpx client bound to the ASGI
   app with the DB dependency pointed at the test transaction.

The test database is separate from the development database. Its name must end
with `_test`; anything else aborts the run. Set TEST_DATABASE_URL to override.

DB-backed tests skip automatically (rather than fail) when Postgres is not
reachable, so the pure unit tests still run in environments without a server.
"""

import asyncio
from collections.abc import AsyncGenerator, Callable
from datetime import UTC, datetime
from urllib.parse import urlparse, urlunparse

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import NullPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config.settings import settings
from src.domain.entities.user import User
from src.infrastructure.database.models.base_model import Base
from src.infrastructure.security.jwt_provider import JWTProvider
from src.infrastructure.security.password_encoder import hash_password

# ─────────────────────────── Entity fixtures ───────────────────────────
# Note: is_validate_ad=False keeps AuthManager on the local bcrypt path.
# With the default (True) it would call the external Darwin AD service and
# unit tests would depend on the network.


@pytest.fixture
def jwt_provider() -> JWTProvider:
    """Provide a JWTProvider instance for tests."""
    return JWTProvider()


@pytest.fixture
def sample_user() -> User:
    """Provide a sample active user entity."""
    return User(
        id=1,
        username="testuser",
        password_hash=hash_password("StrongPass123!"),
        is_active=True,
        is_blocked=False,
        is_validate_ad=False,
        created_by="system",
        created_date=datetime.now(UTC),
        modified_by="system",
        modified_date=datetime.now(UTC),
    )


@pytest.fixture
def inactive_user() -> User:
    """Provide an inactive user entity."""
    return User(
        id=1,
        username="inactiveuser",
        password_hash=hash_password("StrongPass123!"),
        is_active=False,
        is_blocked=False,
        is_validate_ad=False,
    )


@pytest.fixture
def blocked_user() -> User:
    """Provide a blocked user entity."""
    return User(
        id=1,
        username="blockeduser",
        password_hash=hash_password("StrongPass123!"),
        is_active=True,
        is_blocked=True,
        is_validate_ad=False,
    )


# ─────────────────────────── HTTP stubbing ───────────────────────────


@pytest.fixture(autouse=True)
def _forbid_real_http(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Fail any test that tries to open a real outbound HTTP connection.

    This is a safety net, not a convenience. `EMPLOYEE_AD_BASE_URL` defaults to a
    live internal production host, so a test that forgets to stub is not just
    slow — it issues real requests against production from whatever machine or CI
    runner is running the suite. That has already happened once in this suite's
    history.

    Only the real network transports are blocked. `MockTransport` (used by
    `stub_http`) and `ASGITransport` (used by the `client` fixtures to call the
    app in-process) do not go through these methods, so they keep working.
    Database connections use asyncpg, not httpx, and are unaffected.
    """

    def _blocked(kind: str) -> str:
        return (
            f"This test attempted a real outbound {kind} request. Tests must not "
            "touch the network: use the `stub_http` fixture to serve the call "
            "from an in-process MockTransport."
        )

    async def _blocked_async(
        self: httpx.AsyncHTTPTransport, request: httpx.Request
    ) -> httpx.Response:
        raise RuntimeError(f"{_blocked('HTTP')} Blocked: {request.method} {request.url}")

    def _blocked_sync(
        self: httpx.HTTPTransport, request: httpx.Request
    ) -> httpx.Response:
        raise RuntimeError(f"{_blocked('HTTP')} Blocked: {request.method} {request.url}")

    monkeypatch.setattr(
        httpx.AsyncHTTPTransport, "handle_async_request", _blocked_async
    )
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", _blocked_sync)


@pytest.fixture
def stub_http(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[Callable[[httpx.Request], httpx.Response]], list[httpx.Request]]:
    """
    Route every httpx.AsyncClient through an in-process MockTransport.

    The external adapters build their own `httpx.AsyncClient` inside each method,
    so there is no transport to inject. Patching the class on the `httpx` module
    is what makes them testable without touching the network — and the default
    base URLs in settings point at real production hosts, so an un-stubbed call
    is not merely slow, it is a live request. Nothing here can escape the
    transport.

    Usage:
        requests = stub_http(lambda req: httpx.Response(200, json={"ok": True}))

    Returns the list the transport records requests into, so a test can assert on
    the URL, headers and body the adapter actually sent.
    """
    real_client = httpx.AsyncClient

    def _install(
        handler: Callable[[httpx.Request], httpx.Response],
    ) -> list[httpx.Request]:
        recorded: list[httpx.Request] = []

        def _recording(request: httpx.Request) -> httpx.Response:
            recorded.append(request)
            return handler(request)

        def _factory(*args: object, **kwargs: object) -> httpx.AsyncClient:
            # `verify` is meaningless against a mock transport and httpx warns
            # when both are supplied.
            kwargs.pop("verify", None)
            kwargs["transport"] = httpx.MockTransport(_recording)
            return real_client(*args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(httpx, "AsyncClient", _factory)
        return recorded

    return _install


# ─────────────────────────── Database fixtures ───────────────────────────


def _resolve_test_database_url() -> str:
    """
    Work out the test database URL, defaulting to DATABASE_URL + '_test'.

    Raises:
        RuntimeError: If the resolved database name does not end with '_test'.
            This guards against a misconfiguration wiping the dev database.
    """
    url = settings.TEST_DATABASE_URL
    if not url:
        parts = urlparse(settings.DATABASE_URL)
        parts = parts._replace(path=f"{parts.path.rstrip('/')}_test")
        url = urlunparse(parts)

    name = urlparse(url).path.lstrip("/")
    if not name.endswith("_test"):
        raise RuntimeError(
            f"Refusing to run tests against database '{name}': "
            "the test database name must end with '_test'."
        )
    return url


async def _ensure_database_exists(url: str) -> None:
    """Create the test database if it is not there yet (idempotent)."""
    # asyncpg ships no py.typed marker, so mypy cannot see its types. This is a
    # missing-stubs problem in the library, not an error being suppressed here.
    import asyncpg  # type: ignore[import-untyped]

    parsed = urlparse(url)
    name = parsed.path.lstrip("/")
    admin_dsn = urlunparse(
        parsed._replace(scheme="postgresql", path="/postgres")
    ).replace("postgresql+asyncpg", "postgresql")

    conn = await asyncpg.connect(admin_dsn)
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name)
        if not exists:
            await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()


async def _ensure_schema(url: str) -> None:
    """
    Create any missing tables from the SQLAlchemy metadata.

    `create_all` is idempotent (checkfirst), and deliberately not paired with a
    `drop_all`: dropping needs an exclusive lock, which fails when a previous
    test run's connections are still closing — that turned the entire DB-backed
    suite into skips when two runs happened back to back.

    Not dropping is safe because nothing here commits data: every test runs in a
    transaction that is rolled back, so the test database never accumulates rows.
    If the models change, drop the test database once and it will be rebuilt.
    """
    # Import every model so metadata is complete before create_all.
    import src.infrastructure.database.models  # noqa: F401

    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def test_database_url() -> str:
    """
    Prepare the test schema once per session and return the URL.

    Intentionally a *synchronous* fixture that drives its own event loop via
    asyncio.run. A session-scoped async fixture is finalised whenever
    pytest-asyncio decides to close the session loop, which is not guaranteed to
    be the end of the run — that dropped the schema mid-suite and made the DB
    tests fail in a block. Owning the loop here makes setup deterministic.

    Returns a URL rather than an engine because asyncpg connections belong to the
    loop that opened them, and each test gets its own loop; `db_session` builds a
    fresh engine per test.

    The schema is left in place afterwards: the database is disposable, and not
    dropping it avoids both a teardown-ordering hazard and lock contention with
    a subsequent run.
    """
    url = _resolve_test_database_url()

    try:
        asyncio.run(_ensure_database_exists(url))
        asyncio.run(_ensure_schema(url))
    except Exception as exc:  # pragma: no cover - environment dependent
        # When TEST_DATABASE_URL is set explicitly (as CI does), an unreachable
        # database is a hard failure. Skipping would be a false green: the whole
        # DB-backed suite would vanish while pytest still exited 0.
        if settings.TEST_DATABASE_URL:
            pytest.fail(
                f"TEST_DATABASE_URL is set but the database is unreachable: {exc}",
                pytrace=False,
            )
        # Otherwise (a developer with no local Postgres) skip so the pure unit
        # tests still run.
        pytest.skip(f"Test database unavailable: {exc}")

    return url


@pytest_asyncio.fixture
async def db_session(test_database_url: str) -> AsyncGenerator[AsyncSession, None]:
    """
    Provide a session wrapped in a transaction that is always rolled back.

    Each test starts from the same clean schema and cannot leak state into the
    next one, without paying to recreate tables per test.
    """
    engine = create_async_engine(test_database_url, poolclass=NullPool)
    connection = await engine.connect()
    transaction = await connection.begin()
    session_factory = async_sessionmaker(
        bind=connection, class_=AsyncSession, expire_on_commit=False
    )
    session = session_factory()

    try:
        yield session
    finally:
        await session.close()
        if transaction.is_active:
            await transaction.rollback()
        await connection.close()
        await engine.dispose()


# ─────────────────────────── API fixtures ───────────────────────────


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    HTTP client bound to the ASGI app, sharing the test transaction.

    Unauthenticated: use this for public routes and for asserting that
    protected routes reject anonymous callers.
    """
    from src.infrastructure.database.session import get_db_session
    from src.main import app

    async def _override_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db_session] = _override_session
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    finally:
        app.dependency_overrides.clear()


# Master-data resources guarded by API permissions, used to seed the admin role.
MASTER_RESOURCES = (
    "countries",
    "states",
    "categories_of_law",
    "legislations",
    "rules",
    "task_types",
)
CRUD_ACTIONS = ("READ", "CREATE", "UPDATE", "DELETE")

# Non-master resources that are also guarded by (resource, action) pairs.
OTHER_CRUD_RESOURCES = (
    "users",
    "workflows",
    "workflow_instances",
    "approval_matrices",
)

# The RBAC and audit endpoints guard with `require_permission(code)` — matched on
# the permission code alone — rather than the (resource, action) pair the masters
# use. They therefore need seeding by explicit code.
#
# One MENU and one FIELD permission are included so the `my-permissions/menu`
# and `my-permissions/fields` endpoints have something to resolve.
# Tuples are (code, scope, resource, action).
CODE_PERMISSIONS = (
    ("users.import", "API", "users", "IMPORT"),
    ("services.employee_ad", "API", "services", "READ"),
    ("rbac.read", "API", "rbac", "READ"),
    ("rbac.create", "API", "rbac", "CREATE"),
    ("rbac.update", "API", "rbac", "UPDATE"),
    ("audit.read", "API", "audit_logs", "READ"),
    ("menu.masters", "MENU", "masters", "READ"),
    # One per master screen, plus the section key above. Mirrors seed_rbac so a
    # test asserting on menu keys sees the same shape as a real deployment.
    ("menu.masters.countries", "MENU", "masters.countries", "READ"),
    ("menu.masters.states", "MENU", "masters.states", "READ"),
    ("menu.masters.categories_of_law", "MENU", "masters.categories_of_law", "READ"),
    ("menu.masters.legislations", "MENU", "masters.legislations", "READ"),
    ("menu.masters.rules", "MENU", "masters.rules", "READ"),
    ("menu.masters.task_types", "MENU", "masters.task_types", "READ"),
    ("menu.workflows", "MENU", "workflows", "READ"),
    ("users.salary.read", "FIELD", "users.salary", "READ"),
)


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    """
    Seed a real user + role + API permissions + assignment in the test DB.

    Seeding real RBAC rows (rather than overriding the permission dependency)
    means API tests exercise the actual permission-resolution path.
    """
    from src.infrastructure.database.models.role_model import (
        PermissionModel,
        RoleAssignmentModel,
        RoleModel,
        RolePermissionModel,
    )
    from src.infrastructure.database.models.user_model import UserModel

    password_hash = hash_password("AdminPass123!")

    user_model = UserModel(
        username="admin-test",
        password_hash=password_hash,
        is_active=True,
        is_blocked=False,
        is_validate_ad=False,
        created_by="test",
        modified_by="test",
    )
    db_session.add(user_model)
    role = RoleModel(
        code="ADMIN_TEST",
        name="Admin (test)",
        is_system=True,
        is_active=True,
        created_by="test",
        modified_by="test",
    )
    db_session.add(role)
    await db_session.flush()
    user_id = user_model.id

    specs = [
        (f"{resource}.{action.lower()}", "API", resource, action)
        for resource in MASTER_RESOURCES + OTHER_CRUD_RESOURCES
        for action in CRUD_ACTIONS
    ]
    specs.extend(CODE_PERMISSIONS)

    for code, scope, resource, action in specs:
        permission = PermissionModel(
            code=code,
            name=f"{action} {resource}",
            scope=scope,
            resource=resource,
            action=action,
            is_active=True,
            created_by="test",
            modified_by="test",
        )
        db_session.add(permission)
        await db_session.flush()
        db_session.add(
            RolePermissionModel(
                role_id=role.id,
                permission_id=permission.id,
                created_by="test",
                modified_by="test",
            )
        )

    db_session.add(
        RoleAssignmentModel(
            user_id=user_id,
            role_id=role.id,
            is_active=True,
            created_by="test",
            modified_by="test",
        )
    )
    await db_session.flush()

    return User(
        id=user_id,
        username="admin-test",
        password_hash=password_hash,
        is_active=True,
        is_blocked=False,
        is_validate_ad=False,
    )


@pytest_asyncio.fixture
async def admin_client(client: AsyncClient, admin_user: User) -> AsyncClient:
    """Authenticated client carrying a real JWT for the seeded admin user."""
    token = JWTProvider().create_access_token(admin_user.username, admin_user.id)
    client.headers["Authorization"] = f"Bearer {token}"
    return client

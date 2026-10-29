"""
Integration tests for login throttling on POST /api/v1/auth/login.

The full request path through the ASGI app: routing, the dependency graph, the real
controller and the real throttle service over an in-process store. Dependencies are swapped
with `app.dependency_overrides`, not `unittest.mock.patch`: FastAPI resolves `Depends(...)`
targets when routes are declared, so patching a module attribute afterwards changes nothing.

Small limits keep the tests short: 3 attempts per account per IP, 6 per account overall,
5 failures per IP, a 60 s lockout.
"""

import asyncio
from collections.abc import AsyncGenerator

import bcrypt
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import (
    get_audit_service,
    get_auth_manager,
    get_login_throttle_service,
    get_user_repository,
)
from src.api.v1.endpoints.auth_controller import THROTTLED_DETAIL
from src.application.services.login_throttle_service import (
    LoginThrottlePolicy,
    LoginThrottleService,
)
from src.config.settings import settings
from src.domain.entities.user import User
from src.infrastructure.cache.in_memory_login_attempt_store import InMemoryLoginAttemptStore
from src.infrastructure.database.models.audit_log_model import AuditLogModel
from src.infrastructure.database.session import get_db_session
from src.infrastructure.security.auth_manager import AuthManager, AuthTokenResponse
from src.infrastructure.security.jwt_provider import JWTProvider
from src.main import app

POLICY = LoginThrottlePolicy(
    window_seconds=300,
    max_attempts_per_account_ip=3,
    max_attempts_per_account=6,
    max_failures_per_ip=5,
    lockout_seconds=60,
)
USERNAME = "integrationuser"
PASSWORD = "TestPass123!"


def cheap_hash(password: str) -> str:
    """
    A real bcrypt hash at the lowest cost.

    `verify_password` uses the cost stored in the hash, so the code under test is unchanged;
    only the ~300 ms the production cost spends on every wrong guess is saved.
    """
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=4)).decode()


class NullAudit:
    """Audit sink for tests that fire many requests at once (they share one test session)."""

    async def log_login(self, **_: object) -> None:
        return None

    async def log_login_locked(self, **_: object) -> None:
        return None


class FakeUserRepo:
    """Knows one account; everything else is unknown, as in a real directory."""

    def __init__(self, user: User) -> None:
        self._user = user

    async def get_by_username(self, username: str) -> User | None:
        return self._user if username == self._user.username else None


class CountingAuthManager(AuthManager):
    """The real AuthManager, counting how often credentials were actually checked."""

    def __init__(self, user_repository: FakeUserRepo, jwt_provider: JWTProvider) -> None:
        super().__init__(user_repository, jwt_provider)  # type: ignore[arg-type]
        self.checked = 0

    async def login(self, username: str, password: str) -> AuthTokenResponse:
        self.checked += 1
        return await super().login(username, password)


@pytest.fixture(autouse=True)
def no_trusted_proxies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 0)


@pytest.fixture
def user() -> User:
    return User(
        id=1,  # a bigint in this app, not a UUID
        username=USERNAME,
        password_hash=cheap_hash(PASSWORD),
        is_active=True,
        is_blocked=False,
        is_validate_ad=False,  # local bcrypt path: no dependency on the Darwin AD service
    )


@pytest.fixture
def auth_manager(user: User) -> CountingAuthManager:
    return CountingAuthManager(FakeUserRepo(user), JWTProvider())


@pytest.fixture
def throttled_client(
    client: AsyncClient, user: User, auth_manager: CountingAuthManager
) -> AsyncClient:
    """The shared client with a known user, a counting AuthManager and small limits."""
    store = InMemoryLoginAttemptStore()
    app.dependency_overrides[get_user_repository] = lambda: FakeUserRepo(user)
    app.dependency_overrides[get_auth_manager] = lambda: auth_manager
    app.dependency_overrides[get_login_throttle_service] = lambda: LoginThrottleService(
        store, POLICY
    )
    return client


def client_from(address: str) -> AsyncClient:
    """A client whose requests arrive from `address`, for tests about who is throttled."""
    return AsyncClient(
        transport=ASGITransport(app=app, client=(address, 40000)), base_url="http://test"
    )


async def attempt(
    client: AsyncClient,
    username: str = USERNAME,
    password: str = "wrong-password",
    headers: dict[str, str] | None = None,
) -> Response:
    return await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
        headers=headers or {},
    )


async def exhaust_budget(client: AsyncClient, username: str = USERNAME) -> None:
    """Fail as often as one account is allowed to from one address."""
    for _ in range(POLICY.max_attempts_per_account_ip):
        assert (await attempt(client, username)).status_code == 401


class TestRefusal:
    async def test_failures_within_the_limit_are_401_and_the_next_is_429(
        self, throttled_client: AsyncClient
    ) -> None:
        statuses = [(await attempt(throttled_client)).status_code for _ in range(5)]

        assert statuses == [401, 401, 401, 429, 429]

    async def test_the_refusal_says_how_long_to_wait(
        self, throttled_client: AsyncClient
    ) -> None:
        await exhaust_budget(throttled_client)

        refused = await attempt(throttled_client)

        assert refused.status_code == 429
        assert refused.headers["retry-after"] == str(POLICY.lockout_seconds)

    async def test_the_refusal_body_is_the_same_generic_message(
        self, throttled_client: AsyncClient
    ) -> None:
        await exhaust_budget(throttled_client)

        refused = await attempt(throttled_client)

        assert refused.json() == {"detail": THROTTLED_DETAIL}

    async def test_the_correct_password_is_refused_during_a_lockout(
        self, throttled_client: AsyncClient
    ) -> None:
        await exhaust_budget(throttled_client)

        refused = await attempt(throttled_client, password=PASSWORD)

        assert refused.status_code == 429
        assert "set-cookie" not in refused.headers
        assert "access_token" not in refused.text

    async def test_a_refused_attempt_never_gets_as_far_as_checking_credentials(
        self, throttled_client: AsyncClient, auth_manager: CountingAuthManager
    ) -> None:
        """So it costs no bcrypt and can never reach the corporate AD service."""
        await exhaust_budget(throttled_client)
        checked_before = auth_manager.checked

        for _ in range(10):
            await attempt(throttled_client)

        assert auth_manager.checked == checked_before

    async def test_a_burst_gets_no_more_guesses_than_the_limit(
        self, throttled_client: AsyncClient, auth_manager: CountingAuthManager
    ) -> None:
        # Production gives each request its own session; the test client shares one, and
        # 30 requests writing audit rows into it at once would only test SQLAlchemy.
        app.dependency_overrides[get_audit_service] = lambda: NullAudit()

        responses = await asyncio.gather(*(attempt(throttled_client) for _ in range(30)))

        assert sorted({r.status_code for r in responses}) == [401, 429]
        assert auth_manager.checked == POLICY.max_attempts_per_account_ip


class TestNoAccountEnumeration:
    async def test_an_account_that_does_not_exist_is_throttled_exactly_like_one_that_does(
        self, throttled_client: AsyncClient
    ) -> None:
        # Different addresses, so the two runs cannot draw on each other's per-IP budget.
        real = [await attempt(throttled_client, USERNAME) for _ in range(5)]
        async with client_from("203.0.113.50") as elsewhere:
            ghost = [await attempt(elsewhere, "no-such-account") for _ in range(5)]

        assert [r.status_code for r in real] == [401, 401, 401, 429, 429]
        assert [r.status_code for r in real] == [r.status_code for r in ghost]
        assert [r.json() for r in real] == [r.json() for r in ghost]
        assert [r.headers.get("retry-after") for r in real] == [
            r.headers.get("retry-after") for r in ghost
        ]

    async def test_the_throttle_runs_before_the_account_is_looked_up(
        self, throttled_client: AsyncClient, auth_manager: CountingAuthManager
    ) -> None:
        for _ in range(POLICY.max_attempts_per_account_ip):
            await attempt(throttled_client, "no-such-account")
        looked_up = auth_manager.checked

        await attempt(throttled_client, "no-such-account")

        assert auth_manager.checked == looked_up


class TestSuccess:
    async def test_a_good_login_before_the_limit_works_and_clears_the_count(
        self, throttled_client: AsyncClient
    ) -> None:
        await attempt(throttled_client)
        await attempt(throttled_client)

        good = await attempt(throttled_client, password=PASSWORD)
        after = [(await attempt(throttled_client)).status_code for _ in range(4)]

        assert good.status_code == 200
        assert good.json()["access_token"]
        assert after == [401, 401, 401, 429]  # a full budget again, not the one that was left

    async def test_logging_in_as_yourself_does_not_clear_someone_elses_count(
        self, throttled_client: AsyncClient
    ) -> None:
        await exhaust_budget(throttled_client)

        await attempt(throttled_client, "another-account")

        assert (await attempt(throttled_client)).status_code == 429


class TestScope:
    async def test_the_same_account_from_another_address_is_not_locked_out(
        self, throttled_client: AsyncClient
    ) -> None:
        """The real admin must still get in while someone else hammers `admin`."""
        await exhaust_budget(throttled_client)

        async with client_from("203.0.113.77") as elsewhere:
            response = await attempt(elsewhere, password=PASSWORD)

        assert response.status_code == 200

    async def test_another_account_from_the_same_address_is_not_locked_out(
        self, throttled_client: AsyncClient
    ) -> None:
        await exhaust_budget(throttled_client)

        assert (await attempt(throttled_client, "someone-else")).status_code == 401

    async def test_one_address_trying_many_usernames_is_stopped(
        self, throttled_client: AsyncClient
    ) -> None:
        statuses = [
            (await attempt(throttled_client, f"user-{n}")).status_code for n in range(8)
        ]

        assert statuses == [401] * POLICY.max_failures_per_ip + [429] * 3

    async def test_a_spread_out_guesser_is_stopped_by_the_account_wide_limit(
        self, throttled_client: AsyncClient
    ) -> None:
        statuses: list[int] = []
        for n in range(POLICY.max_attempts_per_account // POLICY.max_attempts_per_account_ip):
            async with client_from(f"192.0.2.{n + 1}") as source:
                statuses += [
                    (await attempt(source)).status_code
                    for _ in range(POLICY.max_attempts_per_account_ip)
                ]
        async with client_from("192.0.2.200") as fresh_address:
            refused = await attempt(fresh_address)

        assert set(statuses) == {401}
        assert refused.status_code == 429


HOME = "203.0.113.5"


async def lock_out_strangers(guesses_from: str = "192.0.2") -> list[int]:
    """
    One wrong guess from each of many different addresses, as a botnet would send them.

    Returns the statuses in order. Each address stays far under its own limit, so only the
    account-wide cap on strangers can end this run in a 429.
    """
    statuses: list[int] = []
    for n in range(POLICY.max_attempts_per_account + 3):
        async with client_from(f"{guesses_from}.{n + 1}") as source:
            statuses.append((await attempt(source)).status_code)
    return statuses


class TestFamiliarAddresses:
    """A spread-out attack must not lock the real user out of the network they log in from."""

    async def test_the_owner_still_gets_in_while_the_attack_locks_everyone_else_out(
        self, throttled_client: AsyncClient
    ) -> None:
        async with client_from(HOME) as owner:
            assert (await attempt(owner, password=PASSWORD)).status_code == 200  # now familiar

        statuses = await lock_out_strangers()
        async with client_from(HOME) as owner:
            response = await attempt(owner, password=PASSWORD)

        assert statuses[-1] == 429  # the attack did lock the account for strangers
        assert response.status_code == 200
        assert response.json()["access_token"]

    async def test_a_stranger_with_the_right_password_is_still_refused(
        self, throttled_client: AsyncClient
    ) -> None:
        """The exemption is for addresses the account has logged in from, not for the password."""
        async with client_from(HOME) as owner:
            await attempt(owner, password=PASSWORD)
        await lock_out_strangers()

        async with client_from("198.51.100.77") as traveller:
            refused = await attempt(traveller, password=PASSWORD)

        assert refused.status_code == 429
        assert "set-cookie" not in refused.headers
        assert "access_token" not in refused.text

    async def test_a_familiar_address_cannot_guess_without_limit(
        self, throttled_client: AsyncClient
    ) -> None:
        async with client_from(HOME) as owner:
            await attempt(owner, password=PASSWORD)
        await lock_out_strangers()

        async with client_from(HOME) as same_address:
            statuses = [
                (await attempt(same_address)).status_code
                for _ in range(POLICY.max_attempts_per_account_ip + 1)
            ]

        assert statuses == [401] * POLICY.max_attempts_per_account_ip + [429]

    async def test_without_a_login_from_the_address_the_attack_does_lock_the_owner_out(
        self, throttled_client: AsyncClient
    ) -> None:
        """The case this does not cover, pinned so nobody assumes it does: a new address."""
        await lock_out_strangers()

        async with client_from(HOME) as owner_somewhere_new:
            refused = await attempt(owner_somewhere_new, password=PASSWORD)

        assert refused.status_code == 429

    async def test_a_wrong_password_from_a_familiar_address_is_an_ordinary_401(
        self, throttled_client: AsyncClient
    ) -> None:
        async with client_from(HOME) as owner:
            await attempt(owner, password=PASSWORD)
        await lock_out_strangers()

        async with client_from(HOME) as owner:
            response = await attempt(owner, password="typo")

        assert response.status_code == 401


class TestForgedForwardedHeader:
    async def test_rotating_the_header_does_not_buy_a_fresh_budget(
        self, throttled_client: AsyncClient
    ) -> None:
        """The whole point of resolving the address from the right-hand side."""
        forged = [{"X-Forwarded-For": f"10.9.{n}.1"} for n in range(6)]

        statuses = [(await attempt(throttled_client, headers=h)).status_code for h in forged]

        assert statuses == [401, 401, 401, 429, 429, 429]

    async def test_with_trusted_proxies_the_address_the_proxy_reports_is_throttled(
        self, throttled_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 1)
        attacker = {"X-Forwarded-For": "198.51.100.9"}
        for _ in range(POLICY.max_attempts_per_account_ip):
            await attempt(throttled_client, headers=attacker)

        blocked = await attempt(throttled_client, headers=attacker)
        bystander = await attempt(
            throttled_client, headers={"X-Forwarded-For": "198.51.100.10"}
        )

        assert blocked.status_code == 429
        assert bystander.status_code == 401  # same proxy, different client behind it

    async def test_with_trusted_proxies_a_client_prepended_address_is_ignored(
        self, throttled_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 1)
        statuses = [
            (
                await attempt(
                    throttled_client,
                    headers={"X-Forwarded-For": f"10.9.{n}.1, 198.51.100.9"},
                )
            ).status_code
            for n in range(5)
        ]

        assert statuses == [401, 401, 401, 429, 429]


class TestKillSwitch:
    async def test_a_disabled_throttle_never_refuses(
        self, throttled_client: AsyncClient
    ) -> None:
        from dataclasses import replace

        store = InMemoryLoginAttemptStore()
        app.dependency_overrides[get_login_throttle_service] = lambda: LoginThrottleService(
            store, replace(POLICY, enabled=False)
        )

        statuses = {(await attempt(throttled_client)).status_code for _ in range(15)}

        assert statuses == {401}


class TestCors:
    async def test_retry_after_is_readable_by_a_cross_origin_browser_client(
        self, throttled_client: AsyncClient
    ) -> None:
        await exhaust_budget(throttled_client)

        refused = await attempt(
            throttled_client, headers={"Origin": settings.CORS_ORIGINS[0]}
        )

        exposed = refused.headers.get("access-control-expose-headers", "").lower()
        assert "retry-after" in exposed


@pytest_asyncio.fixture
async def commits_like_production(
    throttled_client: AsyncClient, db_session: AsyncSession
) -> AsyncGenerator[AsyncClient, None]:
    """
    The shared client, with the session behaving as `get_db_session` does in production.

    The ordinary `client` fixture hands every request the same never-committed session, so
    a row written before an error is visible whether or not production would have kept it.
    Production commits when the route returns and rolls back when it raises, which is what
    once discarded the audit row of every failed login. This reproduces that contract on a
    SAVEPOINT of the test's own transaction, so nothing outlives the test.
    """

    async def _session() -> AsyncGenerator[AsyncSession, None]:
        savepoint = await db_session.begin_nested()
        try:
            yield db_session
            await savepoint.commit()
        except Exception:
            await savepoint.rollback()
            raise

    app.dependency_overrides[get_db_session] = _session
    yield throttled_client


async def audit_count(db_session: AsyncSession, action: str) -> int:
    rows = await db_session.execute(
        select(AuditLogModel).where(
            AuditLogModel.action == action, AuditLogModel.resource_id == USERNAME
        )
    )
    return len(rows.scalars().all())


class TestAuditTrail:
    async def test_failed_logins_are_recorded_and_the_record_survives_the_error_response(
        self, commits_like_production: AsyncClient, db_session: AsyncSession
    ) -> None:
        for _ in range(POLICY.max_attempts_per_account_ip):
            await attempt(commits_like_production)

        assert await audit_count(db_session, "LOGIN_FAILED") == POLICY.max_attempts_per_account_ip

    async def test_a_lockout_is_recorded_once(
        self, commits_like_production: AsyncClient, db_session: AsyncSession
    ) -> None:
        for _ in range(POLICY.max_attempts_per_account_ip + 5):
            await attempt(commits_like_production)

        assert await audit_count(db_session, "LOGIN_LOCKED") == 1

    async def test_refused_attempts_write_nothing_so_flooding_cannot_fill_the_table(
        self, commits_like_production: AsyncClient, db_session: AsyncSession
    ) -> None:
        for _ in range(POLICY.max_attempts_per_account_ip + 1):
            await attempt(commits_like_production)
        failed_before = await audit_count(db_session, "LOGIN_FAILED")

        for _ in range(25):
            await attempt(commits_like_production)

        assert await audit_count(db_session, "LOGIN_FAILED") == failed_before
        assert await audit_count(db_session, "LOGIN_LOCKED") == 1

    async def test_a_spread_out_attack_is_recorded_as_a_lockout_of_unfamiliar_addresses(
        self, commits_like_production: AsyncClient, db_session: AsyncSession
    ) -> None:
        await lock_out_strangers()

        row = (
            await db_session.execute(
                select(AuditLogModel).where(AuditLogModel.action == "LOGIN_LOCKED")
            )
        ).scalars().one()
        assert "account_unfamiliar_lockout" in (row.extra_data or "")

    async def test_the_lockout_entry_names_the_account_and_the_cause(
        self, commits_like_production: AsyncClient, db_session: AsyncSession
    ) -> None:
        for _ in range(POLICY.max_attempts_per_account_ip + 1):
            await attempt(commits_like_production)

        row = (
            await db_session.execute(
                select(AuditLogModel).where(AuditLogModel.action == "LOGIN_LOCKED")
            )
        ).scalars().one()
        assert row.actor_username == USERNAME
        assert row.resource_type == "Authentication"
        assert "account_ip_lockout" in (row.extra_data or "")
        assert "60s" in (row.extra_data or "")

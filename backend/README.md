# Enterprise Architecture — Backend

FastAPI backend for tracking statutory compliance obligations. Reference data is
organised as a jurisdiction hierarchy — **Country → State → Category of Law →
Legislation → Rule** — with role-based access control and a full audit trail.

## Stack

| Concern | Choice |
|---|---|
| Runtime | Python 3.12+ |
| Web | FastAPI, Uvicorn |
| Database | PostgreSQL via SQLAlchemy 2.x (async) + asyncpg |
| Migrations | Alembic |
| Auth | JWT (PyJWT), bcrypt, optional Microsoft/Azure SSO |
| Logging | structlog, with a correlation id per request |
| Quality | ruff, mypy (strict), pytest |

## Prerequisites

- Python 3.12 or newer
- PostgreSQL 14+ reachable from your machine

## Setup

```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux / macOS

pip install -e ".[dev]"

copy .env.example .env         # then edit DATABASE_URL and JWT_SECRET_KEY
```

Optional dependency groups, installed only when the features that need them are
built: `pip install -e ".[background]"` (Celery/Redis) and
`.[observability]` (OpenTelemetry).

Create the schema and seed the initial admin user plus RBAC permissions:

```bash
make migrate
make seed
```

`make seed` creates the `admin` user and every default permission and role
mapping. It is idempotent, so re-running it is safe.

## Running

```bash
make run        # uvicorn with reload on http://localhost:6769
```

- Swagger UI: `/docs` (use **Authorize** with a bearer token from `POST /api/v1/auth/login`)
- ReDoc: `/redoc`

## Testing

```bash
make test          # full suite
make test-cov      # with a coverage report
```

Tests run against a **separate** database, derived from `DATABASE_URL` by
appending `_test` unless `TEST_DATABASE_URL` says otherwise. Two safeguards:

- the database name must end in `_test`, or the run aborts
- if `TEST_DATABASE_URL` is set explicitly but unreachable, the suite **fails**
  rather than skipping, so a dead database cannot produce a green build

Each test runs inside a transaction that is rolled back afterwards, so tests
never see each other's writes.

## Quality gates

```bash
make check     # lint + type + drift + test — exactly what CI runs
```

| Gate | Command | Rule |
|---|---|---|
| Lint | `make lint` | ruff, no rules globally ignored |
| Types | `make type` | mypy `strict`; new modules are checked from day one |
| Schema | `make drift` | `alembic check` fails if models and migrations disagree |
| Tests | `make test` | includes architecture tests (below) |

CI runs the same four on every push and pull request touching `backend/`
(`.github/workflows/backend-ci.yml`, at the repository root).

## Architecture

Clean architecture with dependencies pointing inwards:

```
api  ──►  application  ──►  domain  ◄──  infrastructure
```

- **domain** — entities, repository interfaces (ports), domain exceptions. No
  FastAPI, no SQLAlchemy, no outward imports.
- **application** — services orchestrating business rules. Depends on ports
  only; never imports infrastructure or the ORM.
- **infrastructure** — SQLAlchemy models, repository implementations, security,
  external clients.
- **api** — thin controllers that wire concrete adapters and translate errors to
  HTTP status codes.

These rules are **enforced by tests**, not convention — see
`tests/unit/test_architecture.py`, which fails the build on: an outward import
from `domain`, an infrastructure or ORM import in `application`, a `commit()`
outside the session/Unit-of-Work modules, a byte-order mark, or a
double-encoded source line.

### Transactions

- `get_db_session` opens one session per request and commits **once** if the
  request succeeds. FastAPI caches it, so every repository in a request shares
  that session and therefore one transaction.
- Repositories `flush()`, never `commit()`. The caller decides when the unit of
  work is complete.
- `UnitOfWork` (`infrastructure/database/unit_of_work.py`) owns the boundary
  outside a request — scripts and background tasks — and provides `savepoint()`
  for per-record isolation in bulk operations. It requires an explicit
  `commit()`, so a forgotten call rolls back rather than half-persisting.

### Authorization

Permissions are rows, not hardcoded role names, and come in three scopes: `MENU`,
`API`, and `FIELD`.

```python
dependencies=[Depends(require_api_permission("countries", "CREATE"))]  # resource + action
dependencies=[Depends(require_permission("rbac.read"))]                # by code
```

Every security-relevant change is written to `audit_logs`, both explicitly by
services and automatically by a SQLAlchemy `before_flush` listener.

## Project structure

```
backend/
├── pyproject.toml          # dependencies + ruff / mypy / pytest / coverage config
├── alembic.ini
├── Makefile                # dev commands (make help)
├── src/
│   ├── main.py             # app factory, middleware order, router mounting
│   ├── api/
│   │   ├── middleware/     # exception handling, request logging, correlation id, audit context
│   │   └── v1/
│   │       ├── endpoints/   # one controller per resource
│   │       ├── schemas/     # request/response models
│   │       ├── dependencies.py
│   │       └── router.py
│   ├── application/
│   │   └── services/        # one service per aggregate
│   ├── domain/
│   │   ├── entities/        # dataclasses with audit fields
│   │   ├── repositories/    # ports (interfaces)
│   │   ├── services/        # ports for non-repository collaborators
│   │   └── exceptions/
│   ├── infrastructure/
│   │   ├── database/
│   │   │   ├── models/          # SQLAlchemy ORM
│   │   │   ├── repositories/    # port implementations
│   │   │   ├── migrations/      # Alembic versions
│   │   │   ├── session.py
│   │   │   └── unit_of_work.py
│   │   ├── security/        # JWT, password hashing, permission resolution, audit
│   │   └── external/        # Azure SSO, Employee AD clients
│   ├── config/
│   └── observability/
├── tests/
│   ├── conftest.py         # db_session / client / admin_client fixtures
│   ├── unit/
│   └── integration/api/
├── scripts/                # seed_data, seed_rbac, db_migration, generate_openapi
├── docs/architecture/      # design notes and ADRs
└── deployment/             # docker / kubernetes / helm (not yet implemented)
```

## Migrations

```bash
make migration m="create widgets table"   # autogenerate from model changes
make migrate                              # apply to head
make downgrade                            # roll back one revision
make drift                                # verify models match migration history
```

Generated migrations are exempt from the line-length rule; review them before
committing, as autogenerate does not always infer intent.

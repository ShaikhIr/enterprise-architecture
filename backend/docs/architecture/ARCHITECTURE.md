# Architecture Overview

## System Summary

This is a base full-stack scaffold, built to be extended into a domain application
without its own bones needing to change: master-data CRUD, RBAC (Menu/API/Field scoped),
automatic audit logging, dual local/Darwin-AD/Microsoft-OAuth2 authentication, and a
generic workflow/approval engine are all real, working infrastructure rather than
placeholders — the six master screens (Country/State/CategoryOfLaw/Legislation/Rule/
TaskType) exist to prove the CRUD pattern out, not because this project's domain is
country/state data.

- **Backend**: FastAPI (Python 3.12), Clean Architecture (API → Application → Domain ← Infrastructure)
- **Frontend**: React 19 + TypeScript + Vite + PrimeReact (Sakai-compact theme, Emcure brand)
- **Database**: PostgreSQL with async SQLAlchemy (asyncpg)
- **Auth**: JWT (access + HttpOnly-cookie refresh) + dual local/Darwin-AD + Microsoft OAuth2 (Azure AD SSO)
- **RBAC**: Granular permission system (Menu / API / Field-level), no hardcoded role checks
- **Audit**: Automatic before/after change tracking on all tables, same-transaction as the write
- **Workflow**: Generic state-machine + approval-matrix engine, reusable by any entity type that wants an approval flow

---

## High-Level Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                     FRONTEND (React + Vite)                     │
│                                                                │
│  PrimeReact UI │ Redux Toolkit │ TanStack Query │ React Router │
│  RBAC Gates    │ Permission Hooks │ Tree-based permission UI   │
└───────────────────────────────┬────────────────────────────────┘
                                │ REST API (JWT Bearer)
┌───────────────────────────────┼────────────────────────────────┐
│                     BACKEND (FastAPI)                           │
│                                                                │
│  ┌──────────┐  ┌──────────────┐  ┌────────────────────────┐   │
│  │ API Layer│  │ Domain Layer │  │ Infrastructure Layer   │   │
│  │ (routes, │  │ (entities,   │  │ (DB, external APIs,   │   │
│  │ schemas, │  │ repositories,│  │  security, audit)     │   │
│  │ deps)    │  │ services)    │  │                        │   │
│  └──────────┘  └──────────────┘  └────────────────────────┘   │
│                                                                │
│  Middleware: CORS │ Correlation ID │ Auth │ Audit Context      │
│  Security: Permission Manager │ JWT Provider │ Password Hasher │
└───────────────────────────────┬────────────────────────────────┘
                                │
┌───────────────────────────────┼────────────────────────────────┐
│                     DATABASE (PostgreSQL)                       │
│                                                                │
│  countries │ states │ categories_of_law │ legislations │ rules  │
│  task_types │ workflow_* │ approval_* │ users │ user_details    │
│  tenants │ roles │ permissions │ role_permissions               │
│  role_assignments │ audit_logs                                  │
└────────────────────────────────────────────────────────────────┘
```

The dependency rule runs inwards only: `api` depends on `application`/`domain`, `domain`
never imports `infrastructure`, and `infrastructure` implements the interfaces `domain`
defines. This is not just documentation — it is asserted by
`backend/tests/unit/test_architecture.py`'s import-boundary tests, which fail `make check`
on a violation.

---

## Project Structure

```
base-app-setup/
├── backend/
│   ├── src/
│   │   ├── api/
│   │   │   ├── middleware/         # Auth, CORS, correlation, audit context
│   │   │   ├── v1/
│   │   │   │   ├── endpoints/      # Controllers — one file per resource
│   │   │   │   ├── schemas/        # Pydantic request/response models
│   │   │   │   ├── dependencies.py # FastAPI DI — current user, repos, adapters
│   │   │   │   └── router.py       # Aggregates every v1 router
│   │   │   └── v2/                 # Placeholder for a future versioned API
│   │   ├── application/
│   │   │   ├── services/           # Business logic, orchestrates repositories
│   │   │   ├── ports/              # Interfaces for bulk/multi-statement writers
│   │   │   └── exceptions/
│   │   ├── domain/                 # Business logic, framework-free
│   │   │   ├── entities/           # Dataclasses inheriting BaseEntity
│   │   │   ├── repositories/       # Abstract interfaces (I<Entity>Repository)
│   │   │   ├── services/           # Domain-layer ports (e.g. IPermissionResolver)
│   │   │   ├── value_objects/
│   │   │   └── enums/
│   │   ├── infrastructure/         # Adapters and implementations
│   │   │   ├── database/
│   │   │   │   ├── models/         # SQLAlchemy ORM models (BaseModel + AuditMixin)
│   │   │   │   ├── repositories/   # Concrete repo implementations
│   │   │   │   ├── migrations/     # Alembic migrations
│   │   │   │   ├── unit_of_work.py # Session/transaction boundary
│   │   │   │   ├── audit_listener.py  # Automatic before/after audit (SQLAlchemy event)
│   │   │   │   └── audit_context.py   # Request-scoped actor context (ContextVar)
│   │   │   ├── security/           # JWT, password hashing, permission manager, audit service
│   │   │   ├── external/           # Darwin AD client, Azure SSO client
│   │   │   ├── background/, cache/ # Scaffolded for future use
│   │   ├── config/                 # Settings (Pydantic BaseSettings), logging config
│   │   ├── common/
│   │   └── observability/          # Structured logging, OpenTelemetry
│   ├── scripts/                    # seed_rbac.py, seed_data.py, seed_workflow.py, ...
│   ├── deployment/                 # Docker, Helm, Kubernetes
│   └── docs/                       # This directory, plus OpenAPI spec, ADRs
│
└── frontend/
    └── src/
        ├── app/
        │   ├── layouts/            # MainLayout (sidebar + topbar)
        │   ├── router/             # AppRouter, PrivateRoute/PublicRoute (RBAC-gated)
        │   └── store/              # Redux store configuration
        ├── core/
        │   └── rbac/               # The one fully implemented core module: types,
        │                           #   rbacApi, rbacSlice, usePermissions hooks,
        │                           #   PermissionGate.tsx (MenuGate/PermissionGate/FieldGate)
        ├── features/
        │   ├── authentication/     # Local login, Microsoft/Azure AD SSO callback, auth slice
        │   ├── user-management/    # User CRUD, role viewer, employee import
        │   ├── rbac-admin/         # RolesPage (tree-based permission UI), AuditLogsPage
        │   ├── service-menu/       # Employee AD (Darwin) service test/verification page
        │   ├── masters/            # 6 CRUD pages: countries, states, categories of law,
        │   │                       #   legislations, rules, task types
        │   ├── workflow-admin/     # Workflow definitions, builder, approval matrices
        │   ├── audit/, notifications/, dashboard/  # Scaffolded (.gitkeep only), not
        │                           #   implemented — the working audit UI is
        │                           #   rbac-admin/pages/AuditLogsPage.tsx
        ├── shared/                 # Reusable components, services (apiClient, storageService,
        │                           #   sessionCache, sessionBus), utils
        └── assets/                 # Styles, theme overrides, design reference
```

`core/api/`, `core/auth/`, `core/error-handling/`, `core/logging/`, `core/security/`,
`core/telemetry/` and `app/config/`, `app/providers/`, `app/routes/` are also present as
empty `.gitkeep`-only scaffolds — don't assume code exists there just because the folder
does. `shared/services/apiClient.ts` covers the concern `core/api/` implies; the
authentication feature module covers `core/auth/`.

---

## Registered API Routers

All under `/api/v1`, aggregated in `src/api/v1/router.py`:

| Group | Routers |
|-------|---------|
| Identity & access | `auth`, `user`, `rbac`, `employee_import`, `health`, `employee_ad` |
| Master data | `country`, `state`, `category_of_law`, `legislation`, `rule`, `task_type` |
| Workflow engine | `approval_matrix`, `workflow`, `workflow_instance` (approval matrices registered first, so the literal `/workflow/approval-matrices` path is matched ahead of any `/workflow/{...}` route) |

`src/api/v2/router.py` exists as a placeholder for a future versioned API — currently a
one-line stub, not an active second version.

---

## The Generic Building Blocks

### Master data (code-keyed reference data)

Country, State, CategoryOfLaw, Legislation, Rule, and TaskType all follow the identical
CRUD shape: `I<Entity>Repository` extends `IRepository[TEntity]`
(`src/domain/repositories/base_repository.py`), the implementation extends
`SqlAlchemyRepository[TEntity, TModel]` (`src/infrastructure/database/repositories/base_repository_impl.py`),
and the frontend re-exports generic `createMasterHooks`/`MasterCrudPage`/`useMasterCrudController`
per master rather than each screen reinventing dialog/toast/confirm wiring. Country → State
→ CategoryOfLaw and Country → Legislation → Rule form the only hierarchy; a nullable
`state_id` on a child means country-wide (central), not "not set".

Adding a new master means: domain entity + repository interface, ORM model + repository
impl, Pydantic schemas + controller, and on the frontend a models file + api client +
`createMasterHooks` call + a page built on `MasterCrudPage`. See
`.kiro/steering/api-layer-standard.md` for the exact layer contract.

### Workflow engine

`WorkflowDefinition` → `WorkflowStatus`/`WorkflowTransition` (the designed state machine)
and `WorkflowInstance` → `WorkflowHistoryEntry` (a running instance of one) are entity-type
agnostic — a workflow is keyed by `entity_type` (a free-text string) plus `entity_id`
(a UUID), not a foreign key to any specific table. `ApprovalMatrix` → `ApprovalRule` →
`ApprovalAssignment` layer routing-by-condition on top: the lowest-priority matrix whose
rules match an entity's data decides who has to approve it, producing `ApprovalTask` rows.
`scripts/seed_workflow.py` seeds one demonstration workflow (`COMPLIANCE_TASK_APPROVAL`
against `entity_type="compliance_task"`) purely so the engine has something to exercise
end-to-end; nothing in this codebase yet has a real domain entity wired to it — that wiring
is the next project's job, not this scaffold's.

`src/application/services/workflow/` holds the engine's logic:
`state_machine_service.py` (status/transition CRUD, validity checks), `workflow_engine.py`
(instance start/action execution), `rule_evaluator.py` (matches an entity's data against an
`ApprovalMatrix`'s rules), `approval_matrix_resolver.py` (picks the winning matrix), and
`approval_task_coordinator.py` (creates/resolves `ApprovalTask` rows as an instance moves).

---

## Database Schema

| Table | Purpose |
|-------|---------|
| `countries`, `states`, `categories_of_law`, `legislations`, `rules`, `task_types` | Master/reference data |
| `workflow_definitions`, `workflow_statuses`, `workflow_transitions`, `workflow_instances`, `workflow_history` | Workflow engine (design + runtime) |
| `approval_matrices`, `approval_rules`, `approval_assignments`, `approval_tasks` | Approval-matrix routing |
| `users` | Authentication accounts (username, password_hash, is_active, is_blocked, is_validate_ad) |
| `user_details` | Employee AD data (one-to-one with users) |
| `tenants` | Multi-tenant organization boundaries |
| `roles`, `permissions`, `role_permissions`, `role_assignments` | RBAC |
| `audit_logs` | Immutable before/after change log for all tables |

**Note on `users.role`**: there is no `role` column on `users`. Role assignment is
exclusively via the `role_assignments` table (see [ENTERPRISE_RBAC.md](./ENTERPRISE_RBAC.md)),
which is what makes multiple roles per user possible.

**Note on multi-tenancy**: `tenants` and `tenant_id` columns exist and are plumbed through
the schema, but nothing in `permission_manager.py`'s `require_permission`/
`require_api_permission`/`require_field_permission` dependency functions actually filters
by tenant yet — the plumbing is present for a future multi-tenant feature, not an active
constraint today.

---

## Authentication Flow

1. User submits credentials → `POST /auth/login`.
2. Backend branches on the user's `is_validate_ad` flag: `true` calls the Darwin AD service
   (`POST /validatecredentials`) to authenticate; `false` verifies the local bcrypt hash.
3. On success: `is_active`/`is_blocked` are checked, then a JWT access token is returned in
   the response body and a refresh token is set as an HttpOnly, path-scoped cookie.
4. Frontend stores the access token in memory only (`shared/services/storageService.ts`,
   never localStorage/sessionStorage) and attaches it as `Authorization: Bearer <token>`.
5. On a 401, `apiClient.ts`'s `refreshAccessTokenOnce()` de-duplicates concurrent refresh
   attempts into one call to `/auth/refresh`, then retries the original request once.
6. On reload, `authSlice`'s `bootstrapSession` thunk silently restores the session from the
   refresh cookie before the app renders past the splash.

Alternative: Microsoft OAuth2 SSO via Azure AD (Authorization Code flow, confidential
client) — see [MICROSOFT_OAUTH_ANALYSIS.md](./MICROSOFT_OAUTH_ANALYSIS.md). A first-time SSO
login auto-provisions a local user by email, with a random password the user never uses and
no role assigned.

---

## Authorization (RBAC)

All access control is permission-based. Zero `require_role()`-style hardcoded role checks
exist anywhere in the codebase.

| Layer | Mechanism | Example |
|-------|-----------|---------|
| API endpoints | `require_permission("rbac.create")` | Protects one RBAC-management action |
| API endpoints | `require_api_permission("users", "READ")` | Protects the user list endpoint |
| Frontend routes | `<PrivateRoute menuKey="users">` | Redirects if no permission |
| Frontend sidebar | `useMenuPermissions()` hook | Hides/shows nav items |
| Frontend fields | `<FieldGate resource="users" field="salary">` | Hides sensitive fields |

Note: RBAC management itself has no single catch-all permission — it splits into
`rbac.read`, `rbac.create`, and `rbac.update`, matching the granularity every other
resource gets.

### Permission Scopes

| Scope | Controls | Example |
|-------|----------|---------|
| MENU | Sidebar/navigation visibility | `menu.users` → shows Users link |
| API | Endpoint access | `users.list` → allows GET /users |
| FIELD | Field read/write visibility | `users.salary.read` → shows salary |

### Seeded roles

`scripts/seed_rbac.py` seeds three roles — `ADMIN`, `MANAGER`, `USER` — each with a
distinct, real set of granted permissions (see the file's `ROLE_PERMISSIONS` table for the
exact grants). Creating a fourth role, or changing what these three can do, is a normal
`RoleModel`/`RolePermissionModel` row change; no role name is hardcoded in application
logic.

See [ENTERPRISE_RBAC.md](./ENTERPRISE_RBAC.md) for the full permission catalogue.

---

## Audit Logging

Two complementary layers:

| Layer | Trigger | Use Case |
|-------|---------|----------|
| **Automatic** (`audit_listener.py`, a SQLAlchemy `before_flush` event) | Every INSERT/UPDATE/DELETE | Full before/after snapshots, no per-repository code needed |
| **Manual** (`AuditService`) | Explicit calls | Domain events without a row change (login success/failure, permission grant/revoke) |

Both write to `audit_logs` with: actor (from the request-scoped `audit_context.py`
`ContextVar`), action, old/new values (JSON, secret fields redacted), IP, user agent,
timestamp — in the same transaction as the change itself, so an audit row and its data
change are atomically consistent.

See: [ENTERPRISE_AUDIT.md](./ENTERPRISE_AUDIT.md)

---

## Frontend Design System

- **Theme**: PrimeReact Lara Light Blue + Emcure brand overrides (see
  `frontend/src/assets/design/EMCURE_THEME_REFERENCE.md` and
  `.kiro/steering/frontend-ui-standard.md`)
- **Density**: Compact (Sakai-style) — 13px base font, tight padding
- **Responsive**: Scales down at 1440px and 1280px breakpoints
- **Sidebar**: 220px fixed (60px collapsed), hidden below 768px
- **Components**: PrimeReact DataTable, Tree, Dialog, Toast, Tag

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| No `users.role` column | Multiple roles per user via `role_assignments` |
| `require_permission()`/`require_api_permission()` over any `require_role()` | Granular, no hardcoded role names |
| Async SQLAlchemy | Non-blocking DB calls for high concurrency |
| JWT access token in memory (not localStorage) | XSS protection |
| Refresh token as HttpOnly cookie, single de-duplicated refresh in-flight | Session survives reload without racing concurrent 401s into multiple refreshes |
| Audit in same transaction as the write | Atomically consistent with data changes |
| Workflow engine keyed by `entity_type`/`entity_id`, not a foreign key | Reusable by any future entity that wants an approval flow, without schema changes to the engine |
| Tree-based permission UI | Visual, feature-grouped, checkbox selection |
| Clean Architecture layers | Testable, framework-independent domain logic; enforced by `test_architecture.py` |

---

## Related Documents

- [ENTERPRISE_RBAC.md](./ENTERPRISE_RBAC.md) — Full RBAC system design
- [ENTERPRISE_AUDIT.md](./ENTERPRISE_AUDIT.md) — Automatic audit logging
- [EMPLOYEE_AD_SERVICE.md](./EMPLOYEE_AD_SERVICE.md) — Darwin AD integration
- [MICROSOFT_OAUTH_ANALYSIS.md](./MICROSOFT_OAUTH_ANALYSIS.md) — Azure AD SSO
- [VALIDATE_AD_IMPLEMENTATION.md](./VALIDATE_AD_IMPLEMENTATION.md) — Dual local/AD auth strategy
- [`.kiro/steering/api-layer-standard.md`](../../../.kiro/steering/api-layer-standard.md) — Mandatory 4-layer flow, mechanically enforced

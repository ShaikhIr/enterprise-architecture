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
(a bigint), not a foreign key to any specific table. `ApprovalMatrix` → `ApprovalRule` →
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

### Login throttling

`POST /auth/login` is protected against password guessing and credential stuffing (WAPT
finding EMC-WA-1). `LoginThrottleService` (`application/services/`) decides, before any
password is checked, whether an attempt may be evaluated at all, so a refused request costs no
bcrypt and never reaches the Darwin AD service. The counters live behind the
`ILoginAttemptStore` port; the policy is in settings, nothing is hardcoded.

Checked in this order:

| Check | Default | Effect |
|-------|---------|--------|
| Lockout already in force | | 429, `Retry-After` = time left. Attempts made during it touch no counter, so they neither extend it nor use up other budgets. |
| Failures per client IP, any username | 50 per 300 s | 429 until the window ends. Counts failures only, so successful logins from a shared office or proxy address never use it up. |
| Attempts per account **from one IP** | 5 per 300 s | That account is locked **for that IP** for 900 s. |
| Attempts per account, **all unfamiliar IPs together** | 20 per 300 s | The account is locked **for unfamiliar IPs** for 900 s. Caps a guess spread over many addresses. Familiar IPs are neither counted nor locked. |

The per-IP account limit is deliberate. A lockout keyed on the username alone lets anyone who
knows it (`admin`) keep that account locked for the real user indefinitely. Keyed per IP, the
guesser is locked out and the real user, on another address, is not.

**Familiar addresses.** A distributed attack does reach the account-wide cap, and a cap that
locked the account for everyone would then lock out its owner too: anyone with many IP
addresses could keep an account unusable, 900 s at a time. So that cap applies only to
*unfamiliar* addresses, the ones this account has no successful login from. A successful login
makes its address familiar for `LOGIN_FAMILIAR_IP_TTL_SECONDS` (30 days, restarted by each
login). A guesser cannot fake one, because it takes the correct password. Familiar and
unfamiliar failures are counted separately, as in Microsoft's smart lockout, and a familiar
address keeps its own per-account budget (5 per 300 s) and the per-IP failure limit, so it is
not licensed to guess without limit. A stranger is refused even with the correct password,
because the exemption is for addresses and not for passwords.

What it does not cover:

- **The owner on a brand-new address** (travelling, a new network) while an attack on their
  account is under way is refused until the 900 s lockout ends. Closing that needs something
  stronger than an address: a second factor, a trusted-device cookie or a CAPTCHA.
- **A wrong `TRUSTED_PROXY_HOPS`.** If every user appears to come from the proxy's address,
  that address is familiar to everyone, the attacker included, and the per-IP account limit
  then behaves like an account-wide one. Fix the setting (see below).

Behaviour worth knowing:

- **Reserved before verifying.** The account counters are incremented atomically *before*
  credentials are checked, so a burst of parallel guesses is counted one by one before any is
  evaluated. At most the limit's worth ever run. A success clears the count for the address it
  came from and nothing else: clearing the strangers' count would refill a distributed
  guesser's budget every time the owner signed in.
- **No account enumeration.** Unknown usernames are counted exactly like real ones, and
  every refusal carries the same body (`Too many login attempts. Please try again later.`).
  Usernames are case/whitespace/Unicode-folded and hashed before they become keys.
- **429 is returned, not raised.** The login route *returns* its error responses.
  `get_db_session` rolls the request back when a route raises, which used to discard the
  `LOGIN_FAILED` audit row written just before the `HTTPException`. Do not turn those
  returns back into `raise`.
- **Audit and logs.** Every failed login is audited (`LOGIN_FAILED`). A lockout writes
  **one** `LOGIN_LOCKED` entry when it starts, never one per refused attempt, so a flood
  cannot fill `audit_logs`. Lockouts and IP-limit trips are also logged at WARNING.
- **Storage.** Redis (`REDIS_URL`), shared by every replica; `redis` is therefore a core
  dependency, not part of the optional `background` extra. If Redis is unreachable the
  limiter falls back to per-process counters (one WARNING per outage, and the primary is not
  retried for 30 s so logins do not wait out a connect timeout). Per-process counters are
  correct for one replica and multiply across several, so run Redis wherever there is more
  than one. The in-process store is bounded, because attackers choose the usernames. Familiar
  addresses live in the same store, so those recorded in Redis are not visible to the
  fallback: during an outage they revert to strangers, which is the stricter side.
- **Client IP.** Taken from the socket peer, or from `X-Forwarded-For` counted from the
  **right** by `TRUSTED_PROXY_HOPS` (see `api/client_ip.py`). The client controls the left
  of that header, so a forged value cannot buy a fresh budget. IPv6 clients are bucketed by
  /64. The address written to audit rows is a separate, older helper that still reads the
  left-most hop.
- **Kill switches.** `LOGIN_THROTTLE_ENABLED=false` turns the whole throttle off without a
  deploy; startup logs a warning when it is off. `LOGIN_FAMILIAR_IP_TTL_SECONDS=0` turns off
  only the familiar-address exemption, so every address is a stranger again.

`TRUSTED_PROXY_HOPS` must match the real proxy chain. Each proxy appends the address it saw,
so with `client → load balancer → nginx → api` the header reaches the API as
`<forged…>, <client>, <load balancer>` and the right value is **2**; with nginx directly in
front it is **1**. Left at 0 behind a reverse proxy, every user shares the proxy's address and
the per-IP limit applies to all of them together; set too high, it trusts entries the client
wrote. It is only sound when the API is reachable solely through that chain. Two warnings help
catch a wrong value: startup warns when it is 0 and `COOKIE_SECURE=true`, and, independent of
any other setting, the first request that arrives with a forwarding header while it is 0 (or
with a shorter chain than it expects) is logged once as `trusted_proxy_hops_too_low` /
`trusted_proxy_chain_shorter_than_hops`, naming the proxy address the API sees. Look for those
after a deploy.

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

### Content Security Policy

The security headers (CSP, HSTS, COOP, COEP, CORP and the rest) are set by the nginx in front
of the SPA, not by this repository's code. `frontend/docker/nginx.conf` is the reference copy
that the deployed nginx should match (WAPT findings EMC-WA-2, EMC-WA-3 and EMC-WA-4).

- **`style-src 'self' 'nonce-…'`, no `'unsafe-inline'`.** PrimeReact injects its structural
  CSS at runtime as `<style>` elements. nginx writes a fresh nonce (`$request_id`) into the
  CSP header and, through `sub_filter`, into `<meta name="csp-nonce">` in `index.html`.
  `App.tsx` reads it (`shared/utils/cspNonce.ts`) and passes it to `PrimeReactProvider`,
  which stamps it on every `<style>` it creates.
- **A nonce authorises `<style>` elements, not `style=""` attributes.** React inline styles
  go through the CSSOM and are allowed. Markup built as a string must not contain a `style`
  attribute (the JSON viewer colours its tokens with the `em-json-*` classes for this
  reason). If one slips in, the console reports "Refused to apply inline style"; the fix is a
  class, not `'unsafe-inline'`.
- **`index.html` is never cached or revalidated** (`Cache-Control: no-store`, no ETag). A
  reused page would pair an old nonce with a new header and lose every runtime style.
- **Same-origin only.** The CSP and `Cross-Origin-Embedder-Policy: require-corp` together
  block any third-party asset (a CDN font, an image host, analytics) until the policy is
  changed on purpose.
- **No version in error pages.** `server_tokens off`, and nginx's own error responses use
  generic pages that name nothing about the server.
- **Vite dev server and unit tests** send no policy and no nonce; `readCspNonce()` returns
  `undefined` there and PrimeReact injects its styles as before.

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

# Base App Setup — Frontend

React 19 + TypeScript + Vite frontend for the base scaffold this workspace's domain
projects are built from. Master-data CRUD, RBAC, and a generic workflow/approval engine
are real, working infrastructure — the six master screens exist to prove the CRUD pattern
out, not because this scaffold's domain is country/state data. See
`../backend/docs/architecture/ARCHITECTURE.md` for the system-wide picture; this file
covers the frontend tree as it actually exists.

## Stack

| Concern | Choice |
|---|---|
| Framework | React 19, TypeScript (strict) |
| Build | Vite 6 |
| UI | PrimeReact 10 + PrimeFlex + PrimeIcons (Sakai-compact layout, Emcure brand theme — see `.kiro/steering/frontend-ui-standard.md`) |
| Global state | Redux Toolkit |
| Server state | TanStack Query |
| Routing | React Router v7 |
| Forms | React Hook Form + Zod |
| Testing | Vitest + Testing Library |
| Lint/format | ESLint (flat config), Prettier, Husky + lint-staged, commitlint |

## Setup

```bash
npm install
npm run dev      # Vite dev server, http://localhost:6769
```

The backend is expected at `http://127.0.0.1:8000` (see `../dev.ps1`, which starts both).

## Scripts

| Command | Purpose |
|---|---|
| `npm run dev` | Vite dev server |
| `npm run build` | Type-check (`tsconfig.json` + `tsconfig.node.json`) then `vite build` |
| `npm run preview` | Preview a production build locally |
| `npm run type-check` | `tsc --noEmit` against app and test configs, no emit |
| `npm run lint` / `lint:fix` | ESLint, zero warnings allowed |
| `npm run format` | Prettier over `src/**/*.{ts,tsx,css,json}` |
| `npm test` | Vitest, single run (not watch mode) |

## Project Structure (as it actually exists)

```
frontend/
├── public/
│   └── config.json              # Runtime env config placeholder (apiBaseUrl, featureFlags, ...)
├── ci/, docker/                  # Scaffolded, empty (.gitkeep only) — no pipeline/Dockerfile yet
├── tests/
│   ├── unit/                    # Scaffolded, empty (.gitkeep only) — no test files exist
│   │                            #   anywhere in this project yet, under tests/ or src/
│   ├── integration/, e2e/       # Scaffolded, empty (.gitkeep only) — no Playwright/API
│   │                            #   integration suite yet, despite what folder names imply
└── src/
    ├── main.tsx                  # Entry point
    ├── app/
    │   ├── App.tsx                # Root component
    │   ├── router/                # AppRouter (route table), PrivateRoute/PublicRoute (RBAC-gated)
    │   ├── layouts/                 # MainLayout (sidebar + topbar)
    │   ├── store/                   # Redux store configuration
    │   ├── config/, providers/, routes/  # Scaffolded, empty (.gitkeep only)
    ├── core/
    │   ├── rbac/                    # The one fully implemented core module: types, rbacApi,
    │   │                            #   rbacSlice (Redux), usePermissions hooks, PermissionGate.tsx
    │   │                            #   (exports MenuGate, PermissionGate, FieldGate)
    │   ├── api/, auth/, error-handling/, logging/, security/, telemetry/
    │   │                            # Scaffolded, empty (.gitkeep only) — see "Where things
    │   │                            #   actually live" below for what covers these concerns today
    ├── features/
    │   ├── authentication/          # Local login, Microsoft/Azure AD SSO callback, auth Redux slice
    │   ├── user-management/         # User CRUD, role viewer, employee import
    │   ├── rbac-admin/               # RolesPage (tree-based permission UI), AuditLogsPage
    │   ├── service-menu/             # Employee AD (Darwin) service test/verification page
    │   ├── masters/                  # 6 CRUD pages: countries, states, categories of law,
    │   │                            #   legislations, rules, task types
    │   ├── workflow-admin/           # Workflow definitions, builder, approval matrices
    │   ├── audit/                    # Scaffolded, empty (.gitkeep only) — NOT implemented.
    │   │                            #   The working audit-log UI is rbac-admin/pages/AuditLogsPage.tsx
    │   ├── dashboard/, notifications/  # Scaffolded, empty (.gitkeep only) — NOT implemented
    ├── shared/
    │   ├── components/, hooks/, constants/, types/, utils/, styles/
    │   └── services/                # apiClient (Axios + 401 refresh interceptor + correlation id),
    │                                #   storageService (in-memory access token), sessionBus,
    │                                #   sessionCache
    ├── assets/
    │   └── design/EMCURE_THEME_REFERENCE.md   # Color/spacing/badge token reference
    └── i18n/
        └── locales/               # Present but not wired into any component yet
```

### Where things actually live, vs. where the folder names might suggest

Several top-level directories under `app/` and `core/` exist only as `.gitkeep` placeholders
— they describe an intended future structure, not current implementation. Don't assume code
exists there just because the folder does. As of this writing:

| Folder | Status | What actually covers this concern today |
|---|---|---|
| `core/api/` | empty scaffold | `shared/services/apiClient.ts` |
| `core/auth/` | empty scaffold | `features/authentication/` (slice, API, pages) + `shared/services/storageService.ts` |
| `core/error-handling/`, `core/logging/`, `core/security/`, `core/telemetry/` | empty scaffolds | not yet implemented anywhere |
| `core/rbac/` | **implemented** | itself — this is the one core module actually built out |
| `app/config/`, `app/providers/`, `app/routes/` | empty scaffolds | routing lives in `app/router/`; app-level bootstrap in `app/App.tsx` / `main.tsx` |
| `features/audit/` | empty scaffold | `features/rbac-admin/pages/AuditLogsPage.tsx` |
| `features/dashboard/`, `features/notifications/` | empty scaffolds | not yet implemented |
| `ci/`, `docker/` | empty scaffolds | no pipeline config or Dockerfile checked in yet |
| `tests/unit/`, `tests/integration/`, `tests/e2e/` | empty scaffolds | no test files, Playwright suite, or integration suite yet |

Test coverage on the frontend today is zero — there is no `*.test.ts`/`*.test.tsx` file
anywhere in the project. Don't infer test coverage from the `tests/` folder structure —
most of it, like several `src/` folders above, is scaffolding for work that hasn't
happened yet.

## Rules

Frontend UI, RBAC gating, and the full-stack Clean Architecture rules that this project is
held to are documented in `.kiro/steering/` (loaded automatically on every request in Kiro):

- `.kiro/steering/frontend-ui-standard.md` — PrimeReact/Sakai/Emcure UI conventions
- `.kiro/steering/enterprise-standards.md` — cross-stack architecture and security standards
- `.kiro/steering/api-layer-standard.md` — backend layering (relevant when touching API contracts this frontend consumes)

In short: PrimeReact only (no other component library), no `any` in TypeScript, RBAC via
`menuKey`/`PermissionGate`/`FieldGate` rather than any role-name check, and API calls go
through hooks/API modules — never directly inside a component.

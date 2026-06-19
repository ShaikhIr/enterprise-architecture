# Enterprise RBAC Architecture

## Overview

This document describes the enterprise-grade Role-Based Access Control (RBAC) system implemented across the full stack. The system provides:

1. **Audit logging** — Immutable trail for all role/permission changes
2. **Menu-level permissions** — Controls UI sidebar/navigation visibility
3. **API-level permissions** — Controls endpoint access
4. **Field-level permissions** — Controls field read/write visibility per resource
5. **Multi-tenant RBAC** — Tenant-scoped roles and assignments (SaaS-ready)

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                           FRONTEND (React)                          │
│                                                                     │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────────┐   │
│  │  MenuGate   │  │PermissionGate│  │      FieldGate          │   │
│  │  Component  │  │  Component   │  │      Component          │   │
│  └──────┬──────┘  └──────┬───────┘  └───────────┬─────────────┘   │
│         │                 │                      │                  │
│         └─────────────────┼──────────────────────┘                  │
│                           │                                         │
│                    ┌──────┴───────┐                                  │
│                    │  rbacSlice   │  (Redux — loads on login)        │
│                    └──────┬───────┘                                  │
│                           │ GET /rbac/my-permissions/*               │
└───────────────────────────┼─────────────────────────────────────────┘
                            │
┌───────────────────────────┼─────────────────────────────────────────┐
│                      BACKEND (FastAPI)                               │
│                           │                                         │
│  ┌────────────────────────▼──────────────────────────────────┐      │
│  │              rbac_controller.py (API layer)               │      │
│  │  • /rbac/roles         • /rbac/permissions                │      │
│  │  • /rbac/assignments   • /rbac/audit-logs                 │      │
│  │  • /rbac/my-permissions/menu                              │      │
│  │  • /rbac/my-permissions/fields/{resource}                 │      │
│  └────────────────────────┬──────────────────────────────────┘      │
│                           │                                         │
│  ┌────────────────────────▼──────────────────────────────────┐      │
│  │         permission_manager.py (Business Logic)            │      │
│  │  • Resolves effective permissions per user                │      │
│  │  • Handles role hierarchy (parent_role_id inheritance)    │      │
│  │  • Tenant-scoped permission resolution                   │      │
│  │  • require_permission() / require_api_permission()        │      │
│  └────────────────────────┬──────────────────────────────────┘      │
│                           │                                         │
│  ┌────────────────────────▼──────────────────────────────────┐      │
│  │              audit_service.py (Cross-cutting)             │      │
│  │  • Non-blocking audit writes                             │      │
│  │  • Captures actor, action, before/after, IP, timestamp   │      │
│  └───────────────────────────────────────────────────────────┘      │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                            │
┌───────────────────────────┼─────────────────────────────────────────┐
│                     DATABASE (PostgreSQL)                            │
│                                                                     │
│  ┌──────────┐  ┌───────┐  ┌─────────────┐  ┌──────────────────┐   │
│  │ tenants  │  │ roles │  │ permissions │  │ role_permissions │   │
│  └──────────┘  └───┬───┘  └──────┬──────┘  │   (M:N join)    │   │
│                    │              │          └──────────────────┘   │
│              ┌─────┴──────┐      │                                  │
│              │   role_    │      │                                  │
│              │assignments │      │                                  │
│              └─────┬──────┘      │                                  │
│                    │             │                                  │
│              ┌─────┴──────┐     │                                  │
│              │   users    │     │                                  │
│              └────────────┘     │                                  │
│                                 │                                  │
│  ┌──────────────────────────────┴──────────────────────────────┐   │
│  │              audit_logs (append-only, immutable)             │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Database Schema

### Tables

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `tenants` | Multi-tenant org boundaries | code, name, domain, is_active |
| `roles` | Named roles (system or custom) | code, name, tenant_id, parent_role_id, is_system |
| `permissions` | Granular permission definitions | code, scope (MENU/API/FIELD), resource, action |
| `role_permissions` | M:N join (role ↔ permission) | role_id, permission_id |
| `role_assignments` | Links users to roles | user_id, role_id, tenant_id, is_active |
| `audit_logs` | Immutable event log | actor_id, action, resource_type, old/new_value, ip, created_at |

### Permission Scopes

| Scope | Purpose | Example Code | Effect |
|-------|---------|--------------|--------|
| `MENU` | Sidebar visibility | `menu.users` | User sees "Users" nav link |
| `API` | Endpoint access | `users.create` | User can call POST /users |
| `FIELD` | Field read/write | `users.salary` | User can see salary column |

### Default Roles (seeded)

| Role | Type | Permissions |
|------|------|-------------|
| ADMIN | System | All 25 permissions (full access) |
| MANAGER | System | 9 permissions (view users, reports, services) |
| USER | System | 2 permissions (dashboard, services only) |

---

## File Structure

### Backend

```
backend/src/
├── api/v1/
│   ├── endpoints/
│   │   └── rbac_controller.py          # RBAC REST API (roles, permissions, audit)
│   └── schemas/
│       └── rbac_schema.py              # Pydantic request/response models
├── domain/entities/
│   ├── role.py                         # Role, Permission, RoleAssignment entities
│   ├── tenant.py                       # Tenant entity
│   └── audit_log.py                    # AuditLog entity + AuditAction enum
├── infrastructure/
│   ├── database/
│   │   ├── models/
│   │   │   ├── role_model.py           # SQLAlchemy: roles, permissions, role_permissions, role_assignments
│   │   │   ├── tenant_model.py         # SQLAlchemy: tenants
│   │   │   └── audit_log_model.py      # SQLAlchemy: audit_logs (append-only)
│   │   └── migrations/versions/
│   │       └── b7e2f1c4d9a3_*.py       # Alembic migration for RBAC tables
│   └── security/
│       ├── permission_manager.py       # Permission resolution engine + FastAPI deps
│       ├── audit_service.py            # Audit log writer (non-blocking)
│       └── rbac_manager.py             # Legacy role hierarchy (still works)
└── scripts/
    └── seed_rbac.py                    # Seed default permissions + role mappings
```

### Frontend

```
frontend/src/
├── core/rbac/
│   ├── index.ts                        # Public barrel export
│   ├── types.ts                        # Permission, Role, response types
│   ├── rbacApi.ts                      # API client (GET /rbac/my-permissions/*)
│   ├── rbacSlice.ts                    # Redux state (menu keys, field perms)
│   ├── usePermissions.ts              # Hooks: useMenuPermission, useFieldPermissions
│   └── PermissionGate.tsx             # Components: MenuGate, PermissionGate, FieldGate
├── features/rbac-admin/
│   ├── api/rbacAdminApi.ts            # Admin API (CRUD roles, permissions, audit logs)
│   ├── models/rbac-admin.types.ts     # Admin feature types
│   ├── pages/
│   │   ├── RolesPage.tsx              # Roles CRUD + permission assignment UI
│   │   └── AuditLogsPage.tsx          # Audit log viewer with filters + JSON popup
│   └── index.ts
├── shared/components/
│   └── ContentViewerDialog.tsx        # Generic popup: JSON / PDF / text viewer
└── app/
    ├── store/index.ts                 # Redux store (includes rbacReducer)
    ├── router/AppRouter.tsx           # Routes: /roles, /audit-logs
    └── layouts/MainLayout.tsx         # Sidebar with Roles & Audit nav items
```

---

## API Reference

### Permission Management (ADMIN only)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/rbac/permissions?scope=MENU` | List permissions (optional scope filter) |
| POST | `/api/v1/rbac/permissions` | Create a new permission definition |

### Role Management (ADMIN only)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/rbac/roles?tenant_id=...` | List roles with permissions |
| POST | `/api/v1/rbac/roles` | Create a new role |
| PATCH | `/api/v1/rbac/roles/{role_id}` | Update role (name, description, active) |
| POST | `/api/v1/rbac/roles/grant-permission` | Grant a permission to a role |
| POST | `/api/v1/rbac/roles/revoke-permission` | Revoke a permission from a role |

### Role Assignment (ADMIN only)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/rbac/assignments` | Assign role to user (with optional tenant) |
| POST | `/api/v1/rbac/assignments/revoke` | Revoke role from user |

### User Permission Queries (Authenticated)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/rbac/my-permissions/menu` | Menu keys + permissions for current user |
| GET | `/api/v1/rbac/my-permissions/fields/{resource}` | Field-level perms for a resource |

### Audit Logs (ADMIN only)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/rbac/audit-logs?action=...&actor_username=...&resource_type=...&skip=0&limit=50` | Query with filters |

---

## Backend Usage Examples

### Protect endpoint with specific permission code

```python
from src.infrastructure.security.permission_manager import require_permission

@router.get(
    "/sensitive-data",
    dependencies=[Depends(require_permission("users.salary.read"))],
)
async def get_sensitive_data(...):
    ...
```

### Protect endpoint with API-level permission (resource + action)

```python
from src.infrastructure.security.permission_manager import require_api_permission

@router.post(
    "/reports/export",
    dependencies=[Depends(require_api_permission("reports", "EXPORT"))],
)
async def export_report(...):
    ...
```

### Legacy role-based check (still supported)

```python
from src.infrastructure.security.rbac_manager import require_role

@router.get("/admin-only", dependencies=[Depends(require_role("ADMIN"))])
async def admin_endpoint(...):
    ...
```

### Write an audit log entry

```python
from src.infrastructure.security.audit_service import AuditService

audit = AuditService(session)
await audit.log(
    actor_id=current_user.id,
    actor_username=current_user.username,
    action=AuditAction.ROLE_ASSIGNED,
    resource_type="RoleAssignment",
    resource_id=str(user_id),
    new_value={"role_code": "MANAGER"},
    ip_address=request.client.host,
)
```

---

## Frontend Usage Examples

### Menu-level gating (hide nav items)

```tsx
import { MenuGate } from '@core/rbac';

<MenuGate menuKey="users">
  <NavItem to="/users" icon="pi pi-users" label="Users" />
</MenuGate>
```

### Permission-based button visibility

```tsx
import { PermissionGate } from '@core/rbac';

<PermissionGate permission="users.create">
  <Button label="Create User" />
</PermissionGate>
```

### Field-level visibility

```tsx
import { FieldGate } from '@core/rbac';

<FieldGate resource="users" field="salary" action="READ">
  <Column field="salary" header="Salary" />
</FieldGate>
```

### Hook-based checks

```tsx
import { useMenuPermission, useFieldPermissions, useHasPermission } from '@core/rbac';

const MyComponent = () => {
  const { canAccess } = useMenuPermission('reports');
  const { canReadField, canWriteField } = useFieldPermissions('users');
  const canExport = useHasPermission('reports.export');

  return (
    <div>
      {canAccess && <ReportsLink />}
      {canReadField('salary') && <span>{user.salary}</span>}
      {canWriteField('email') && <InputText ... />}
      {canExport && <Button label="Export" />}
    </div>
  );
};
```

### Dynamic role loading in forms

```tsx
import { useRoles } from '@features/user-management/hooks/useRoles';

const { roleOptions, loading } = useRoles();
// roleOptions = [{ label: "Administrator", value: "ADMIN" }, ...]
// Loaded from GET /api/v1/rbac/roles
```

---

## Multi-Tenant Support

| Feature | Implementation |
|---------|---------------|
| Tenant-scoped roles | `roles.tenant_id` — NULL means global role |
| Scoped assignments | `role_assignments.tenant_id` — assigns role within a tenant |
| Resolution logic | PermissionManager merges global + tenant roles for a user |
| Tenant auto-assign | `Tenant.matches_email_domain()` — maps email domain to tenant |
| API filtering | `GET /rbac/roles?tenant_id=...` returns global + tenant roles |

---

## Audit Trail

### What's Logged

| Category | Actions |
|----------|---------|
| Roles | ROLE_CREATED, ROLE_UPDATED, ROLE_DELETED |
| Permissions | PERMISSION_CREATED, PERMISSION_GRANTED, PERMISSION_REVOKED |
| Assignments | ROLE_ASSIGNED, ROLE_REVOKED |
| Authentication | LOGIN_SUCCESS, LOGIN_FAILED, TOKEN_REFRESHED |
| Users | USER_BLOCKED, USER_UNBLOCKED, USER_ACTIVATED, USER_DEACTIVATED |
| Tenants | TENANT_CREATED, TENANT_UPDATED |

### Entry Structure

Each audit log entry captures:
- **Who**: actor_id, actor_username
- **What**: action, resource_type, resource_id
- **Change**: old_value (JSON), new_value (JSON)
- **Context**: tenant_id, ip_address, user_agent, extra_data
- **When**: created_at (UTC, indexed)

### Design Decisions

- **Append-only**: No UPDATE/DELETE on audit_logs table
- **Non-blocking**: Audit writes never fail the parent operation (errors are logged internally)
- **Denormalized**: actor_username stored for fast querying without JOINs
- **Indexed**: action, actor_username, resource_type, created_at for efficient filtering

---

## Admin UI Pages

### Roles & Permissions (`/roles`)

- DataTable listing all roles with permission count
- Create new custom roles
- Manage permissions per role via MultiSelect dialog
- System roles (ADMIN, MANAGER, USER) are read-only

### Audit Logs (`/audit-logs`)

- Paginated, lazy-loaded DataTable
- Filters: action type, resource type, actor username
- Clickable Details column opens JSON viewer popup (ContentViewerDialog)
- Supports formatted JSON with syntax highlighting + copy to clipboard

### User Management (`/users`)

- Role dropdown dynamically loaded from roles table
- New roles created in RBAC admin appear immediately in user forms

---

## Setup & Operations

### Initial Setup

```bash
# 1. Run migration (creates all RBAC tables)
alembic upgrade head

# 2. Seed default permissions and role mappings
python -m scripts.seed_rbac

# 3. Reset admin password (if needed for testing)
python -m scripts.reset_admin_pw
```

### Adding a New Permission

1. Create via API: `POST /api/v1/rbac/permissions`
2. Grant to role: `POST /api/v1/rbac/roles/grant-permission`
3. Use in code: `require_permission("your.new.code")`

### Adding a New Role

1. Create via UI: Navigate to `/roles` → "New Role"
2. Assign permissions via the shield icon
3. Assign to users via API or user edit form

---

## Migration Strategy (Legacy → New RBAC)

The existing `users.role` string column coexists with the new granular system:

| Mechanism | Checks | Use Case |
|-----------|--------|----------|
| `require_role("ADMIN")` | `users.role` column | Simple role gates (backward compat) |
| `require_permission("code")` | `role_assignments` + `role_permissions` | Granular permission checks |
| `require_api_permission(resource, action)` | Same as above, scoped by resource+action | API-level gates |

Both systems work simultaneously. Migration path:
1. Assign users to roles in `role_assignments` table
2. Gradually replace `require_role()` with `require_permission()` in endpoints
3. Eventually deprecate the `users.role` column

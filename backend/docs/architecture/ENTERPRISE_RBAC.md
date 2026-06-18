# Enterprise RBAC Architecture

## Overview

This document describes the enterprise-grade Role-Based Access Control (RBAC) system with:

1. **Audit logging** for all role/permission changes
2. **Menu-level permissions** (controls UI navigation visibility)
3. **API-level permissions** (controls endpoint access)
4. **Field-level permissions** (controls field read/write visibility)
5. **Multi-tenant RBAC** support

---

## Data Model

```
┌──────────┐     ┌─────────────────┐     ┌─────────────┐
│  Tenant  │◄────│  Role           │────►│ Permission  │
└──────────┘     │  (tenant-scoped)│     │ (scope-based)│
                 └────────┬────────┘     └─────────────┘
                          │ M:N via
                 ┌────────┴────────┐
                 │ RoleAssignment   │
                 │ (user+tenant)    │
                 └────────┬────────┘
                          │
                 ┌────────┴────────┐
                 │     User        │
                 └─────────────────┘

┌─────────────────────────────────┐
│         AuditLog (append-only)  │
│  actor, action, resource,       │
│  old_value, new_value, IP, etc. │
└─────────────────────────────────┘
```

## Permission Scopes

| Scope | Purpose | Example |
|-------|---------|---------|
| `MENU` | Controls sidebar/navigation visibility | `menu.users` → user can see "Users" nav item |
| `API` | Controls backend endpoint access | `users.create` → can POST /users |
| `FIELD` | Controls individual field read/write | `users.salary` → can see salary column |

## API Endpoints

### Permission Management (ADMIN only)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/rbac/permissions` | List all permissions (filter by scope) |
| POST | `/api/v1/rbac/permissions` | Create a new permission |

### Role Management (ADMIN only)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/rbac/roles` | List all roles with permissions |
| POST | `/api/v1/rbac/roles` | Create a new role |
| PATCH | `/api/v1/rbac/roles/{id}` | Update a role |
| POST | `/api/v1/rbac/roles/grant-permission` | Grant permission to a role |
| POST | `/api/v1/rbac/roles/revoke-permission` | Revoke permission from a role |

### Role Assignment (ADMIN only)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/rbac/assignments` | Assign role to user |
| POST | `/api/v1/rbac/assignments/revoke` | Revoke role from user |

### User Permission Queries (Authenticated)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/rbac/my-permissions/menu` | Get menu keys user can access |
| GET | `/api/v1/rbac/my-permissions/fields/{resource}` | Get field permissions |

### Audit Logs (ADMIN only)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/rbac/audit-logs` | Query audit logs with filters |

## Backend Usage

### Protecting an endpoint with API-level permission:

```python
from src.infrastructure.security.permission_manager import require_api_permission

@router.post(
    "/reports/export",
    dependencies=[Depends(require_api_permission("reports", "EXPORT"))],
)
async def export_report(...):
    ...
```

### Protecting with a permission code:

```python
from src.infrastructure.security.permission_manager import require_permission

@router.get(
    "/sensitive-data",
    dependencies=[Depends(require_permission("users.salary.read"))],
)
async def get_sensitive_data(...):
    ...
```

### The existing `require_role()` still works for simple cases:

```python
from src.infrastructure.security.rbac_manager import require_role

@router.get("/admin-only", dependencies=[Depends(require_role("ADMIN"))])
async def admin_endpoint(...):
    ...
```

## Frontend Usage

### Menu-level gating (hide nav items):

```tsx
import { MenuGate } from '@core/rbac';

<MenuGate menuKey="users">
  <NavItem to="/users" icon="pi pi-users" label="Users" />
</MenuGate>
```

### Permission-based button visibility:

```tsx
import { PermissionGate } from '@core/rbac';

<PermissionGate permission="users.create">
  <Button label="Create User" />
</PermissionGate>
```

### Field-level visibility:

```tsx
import { FieldGate } from '@core/rbac';

<FieldGate resource="users" field="salary" action="READ">
  <Column field="salary" header="Salary" />
</FieldGate>
```

### Hook-based checks:

```tsx
import { useMenuPermission, useFieldPermissions } from '@core/rbac';

const MyComponent = () => {
  const { canAccess } = useMenuPermission('reports');
  const { canReadField, canWriteField } = useFieldPermissions('users');

  return (
    <div>
      {canAccess && <ReportsLink />}
      {canReadField('salary') && <span>{user.salary}</span>}
      {canWriteField('email') && <InputText ... />}
    </div>
  );
};
```

## Multi-Tenant Support

- Roles can be scoped to a tenant (`tenant_id` on RoleModel)
- Role assignments carry optional `tenant_id`
- PermissionManager resolves global + tenant-specific roles
- API supports `tenant_id` filter on role listing

## Audit Trail

Every RBAC operation is recorded in `audit_logs`:
- Role created/updated/deleted
- Permission created/granted/revoked
- Role assigned/revoked to/from user
- Login success/failure

Each entry includes: actor, action, before/after state, IP address, timestamp.

## Setup

1. Run migration: `alembic upgrade head`
2. Seed default permissions: `python -m scripts.seed_rbac`
3. Assign roles to users via the API or admin UI

## Migration from Legacy Role Field

The existing `users.role` string column remains for backward compatibility.
The new system uses `role_assignments` for granular control. Both can coexist
during the transition period, with `require_role()` checking the legacy field
and `require_permission()` checking the new tables.

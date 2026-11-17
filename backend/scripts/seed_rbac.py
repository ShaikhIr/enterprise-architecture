"""
Seed script for RBAC permissions.
Populates default menu, API, and field-level permissions.
Run via: python -m scripts.seed_rbac

This is idempotent - re-running will skip existing permissions.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select

from src.infrastructure.database.models.role_model import (
    PermissionModel,
    RoleAssignmentModel,
    RoleModel,
    RolePermissionModel,
)
from src.infrastructure.database.models.user_model import UserModel
from src.infrastructure.database.unit_of_work import UnitOfWork

# --- Default Permission Definitions ---

# Permission table - one row per line so it reads as a table rather than as
# 50-plus wrapped dict literals.
# Columns: (code, scope, resource, action, name)
_PERMISSION_TABLE = [
    # Menu permissions - control sidebar/navigation visibility
    ("menu.dashboard", "MENU", "dashboard", "READ", "Dashboard Menu"),
    ("menu.users", "MENU", "users", "READ", "Users Menu"),
    ("menu.roles", "MENU", "roles", "READ", "Roles Menu"),
    ("menu.audit_logs", "MENU", "audit_logs", "READ", "Audit Logs Menu"),
    ("menu.services", "MENU", "services", "READ", "Services Menu"),
    ("menu.workflows", "MENU", "workflows", "READ", "Workflows Menu"),

    # Masters navigation - `masters` gates the section as a whole, and each
    # `masters.<x>` gates one screen within it. Both are required to reach a
    # screen, so revoking `menu.masters` hides the section outright while
    # revoking one child hides just that screen.
    #
    # The dotted resource is what nests these under a single "Masters" folder on
    # the RBAC screen, which groups by the first segment of the resource.
    ("menu.masters", "MENU", "masters", "READ", "Masters Menu"),
    ("menu.masters.countries", "MENU", "masters.countries", "READ", "Countries Menu"),
    ("menu.masters.states", "MENU", "masters.states", "READ", "States Menu"),
    (
        "menu.masters.categories_of_law",
        "MENU",
        "masters.categories_of_law",
        "READ",
        "Categories of Law Menu",
    ),
    (
        "menu.masters.legislations",
        "MENU",
        "masters.legislations",
        "READ",
        "Legislations Menu",
    ),
    ("menu.masters.rules", "MENU", "masters.rules", "READ", "Rules Menu"),
    ("menu.masters.task_types", "MENU", "masters.task_types", "READ", "Task Types Menu"),

    # API permissions - control endpoint access
    ("users.list", "API", "users", "READ", "List Users"),
    ("users.create", "API", "users", "CREATE", "Create User"),
    ("users.update", "API", "users", "UPDATE", "Update User"),
    ("users.delete", "API", "users", "DELETE", "Delete User"),
    ("users.export", "API", "users", "EXPORT", "Export Users"),
    ("users.import", "API", "users", "IMPORT", "Import Users"),
    ("roles.list", "API", "roles", "READ", "List Roles"),
    ("roles.create", "API", "roles", "CREATE", "Create Role"),
    ("roles.update", "API", "roles", "UPDATE", "Update Role"),
    ("roles.assign", "API", "roles", "EXECUTE", "Assign Roles"),
    ("audit.read", "API", "audit_logs", "READ", "View Audit Logs"),

    # RBAC management permissions - granular control over roles & permissions CRUD
    ("rbac.read", "API", "rbac", "READ", "View Roles & Permissions"),
    ("rbac.create", "API", "rbac", "CREATE", "Create Roles & Permissions"),
    ("rbac.update", "API", "rbac", "UPDATE", "Update Roles & Permissions"),

    # Employee AD service permission
    ("services.employee_ad", "API", "services", "EXECUTE", "Access Employee AD Service"),

    # Master data permissions - compliance reference data CRUD
    ("countries.list", "API", "countries", "READ", "List Countries"),
    ("countries.create", "API", "countries", "CREATE", "Create Country"),
    ("countries.update", "API", "countries", "UPDATE", "Update Country"),
    ("countries.delete", "API", "countries", "DELETE", "Delete Country"),
    ("states.list", "API", "states", "READ", "List States"),
    ("states.create", "API", "states", "CREATE", "Create State"),
    ("states.update", "API", "states", "UPDATE", "Update State"),
    ("states.delete", "API", "states", "DELETE", "Delete State"),
    ("categories_of_law.list", "API", "categories_of_law", "READ", "List Categories of Law"),
    ("categories_of_law.create", "API", "categories_of_law", "CREATE", "Create Category of Law"),
    ("categories_of_law.update", "API", "categories_of_law", "UPDATE", "Update Category of Law"),
    ("categories_of_law.delete", "API", "categories_of_law", "DELETE", "Delete Category of Law"),
    ("legislations.list", "API", "legislations", "READ", "List Legislations"),
    ("legislations.create", "API", "legislations", "CREATE", "Create Legislation"),
    ("legislations.update", "API", "legislations", "UPDATE", "Update Legislation"),
    ("legislations.delete", "API", "legislations", "DELETE", "Delete Legislation"),
    ("rules.list", "API", "rules", "READ", "List Rules"),
    ("rules.create", "API", "rules", "CREATE", "Create Rule"),
    ("rules.update", "API", "rules", "UPDATE", "Update Rule"),
    ("rules.delete", "API", "rules", "DELETE", "Delete Rule"),
    ("task_types.list", "API", "task_types", "READ", "List Task Types"),
    ("task_types.create", "API", "task_types", "CREATE", "Create Task Type"),
    ("task_types.update", "API", "task_types", "UPDATE", "Update Task Type"),
    ("task_types.delete", "API", "task_types", "DELETE", "Delete Task Type"),

    # Workflow engine permissions - three resources so designing a workflow,
    # running one, and configuring approval routing stay separately grantable.
    ("workflows.list", "API", "workflows", "READ", "List Workflows"),
    ("workflows.create", "API", "workflows", "CREATE", "Create Workflow"),
    ("workflows.update", "API", "workflows", "UPDATE", "Update Workflow"),
    ("workflows.delete", "API", "workflows", "DELETE", "Delete Workflow"),
    ("workflow_instances.list", "API", "workflow_instances", "READ", "View Workflow Instances"),
    ("workflow_instances.create", "API", "workflow_instances", "CREATE", "Start Workflow"),
    ("workflow_instances.update", "API", "workflow_instances", "UPDATE", "Act on Workflow"),
    ("workflow_instances.delete", "API", "workflow_instances", "DELETE", "Delete Instance"),
    ("approval_matrices.list", "API", "approval_matrices", "READ", "List Approval Matrices"),
    ("approval_matrices.create", "API", "approval_matrices", "CREATE", "Create Approval Matrix"),
    ("approval_matrices.update", "API", "approval_matrices", "UPDATE", "Update Approval Matrix"),
    ("approval_matrices.delete", "API", "approval_matrices", "DELETE", "Delete Approval Matrix"),

    # Field-level permissions - control visibility of sensitive fields
    ("users.salary.read", "FIELD", "users.salary", "READ", "View Salary"),
    ("users.salary.update", "FIELD", "users.salary", "UPDATE", "Edit Salary"),
    ("users.email.read", "FIELD", "users.email", "READ", "View Email"),
    ("users.email.update", "FIELD", "users.email", "UPDATE", "Edit Email"),
    ("users.phone.read", "FIELD", "users.phone", "READ", "View Phone"),
]

# Expanded to the dict shape the seeding code below consumes.
DEFAULT_PERMISSIONS = [
    {"code": c, "scope": s, "resource": r, "action": a, "name": n}
    for c, s, r, a, n in _PERMISSION_TABLE
]

# Role -> permission code assignments
ROLE_PERMISSIONS = {
    "ADMIN": [
        # Admin gets ALL permissions
        "menu.dashboard", "menu.users", "menu.roles", "menu.audit_logs",
        "menu.services",
        "users.list", "users.create", "users.update", "users.delete",
        "users.export", "users.import",
        "roles.list", "roles.create", "roles.update", "roles.assign",
        "audit.read",
        "rbac.read", "rbac.create", "rbac.update", "services.employee_ad",
        "menu.masters",
        "menu.masters.countries", "menu.masters.states",
        "menu.masters.categories_of_law", "menu.masters.legislations",
        "menu.masters.rules", "menu.masters.task_types",
        "countries.list", "countries.create", "countries.update", "countries.delete",
        "states.list", "states.create", "states.update", "states.delete",
        "categories_of_law.list", "categories_of_law.create",
        "categories_of_law.update", "categories_of_law.delete",
        "legislations.list", "legislations.create",
        "legislations.update", "legislations.delete",
        "rules.list", "rules.create", "rules.update", "rules.delete",
        "task_types.list", "task_types.create", "task_types.update", "task_types.delete",
        "menu.workflows",
        "workflows.list", "workflows.create", "workflows.update", "workflows.delete",
        "workflow_instances.list", "workflow_instances.create",
        "workflow_instances.update", "workflow_instances.delete",
        "approval_matrices.list", "approval_matrices.create",
        "approval_matrices.update", "approval_matrices.delete",
        "users.salary.read", "users.salary.update",
        "users.email.read", "users.email.update", "users.phone.read",
    ],
    "MANAGER": [
        "menu.dashboard", "menu.users", "menu.services",
        "users.list", "users.export",
        "users.email.read", "users.phone.read",
        # Masters are read-only for managers
        "menu.masters",
        "menu.masters.countries", "menu.masters.states",
        "menu.masters.categories_of_law", "menu.masters.legislations",
        "menu.masters.rules", "menu.masters.task_types",
        "countries.list", "states.list", "categories_of_law.list",
        "legislations.list", "rules.list", "task_types.list",
        # Managers run workflows and read the routing config, but do not design
        # either: no workflows.create/update/delete, no approval_matrices writes.
        "menu.workflows",
        "workflows.list",
        "workflow_instances.list", "workflow_instances.create",
        "workflow_instances.update",
        "approval_matrices.list",
    ],
    "USER": [
        "menu.dashboard", "menu.services",
        "menu.masters",
        "menu.masters.countries", "menu.masters.states",
        "menu.masters.categories_of_law", "menu.masters.legislations",
        "menu.masters.rules", "menu.masters.task_types",
        "countries.list", "states.list", "categories_of_law.list",
        "legislations.list", "rules.list", "task_types.list",
        # Read-only visibility into workflows they are involved in; /my-tasks
        # needs no API permission because it is scoped to the caller.
        "menu.workflows",
        "workflows.list",
        "workflow_instances.list",
    ],
}


async def seed() -> None:
    """Seed default permissions and role-permission mappings."""
    async with UnitOfWork() as uow:
        session = uow.session
        # 1. Create permissions (skip existing)
        perm_map: dict[str, int] = {}  # code -> id
        new_perms: list[PermissionModel] = []

        for perm_def in DEFAULT_PERMISSIONS:
            existing = await session.execute(
                select(PermissionModel).where(PermissionModel.code == perm_def["code"])
            )
            perm = existing.scalar_one_or_none()

            if perm:
                perm_map[perm.code] = perm.id
                print(f"  [skip] Permission '{perm_def['code']}' already exists")
            else:
                new_perm = PermissionModel(
                    code=perm_def["code"],
                    name=perm_def["name"],
                    description="",
                    scope=perm_def["scope"],
                    resource=perm_def["resource"],
                    action=perm_def["action"],
                    is_active=True,
                    created_by="seed_script",
                    modified_by="seed_script",
                )
                session.add(new_perm)
                new_perms.append(new_perm)
                print(f"  [new]  Permission '{perm_def['code']}' created")

        # Flush so the DB assigns each new permission's bigint id, then record it.
        await session.flush()
        for new_perm in new_perms:
            perm_map[new_perm.code] = new_perm.id

        # 2. Assign permissions to roles
        for role_code, perm_codes in ROLE_PERMISSIONS.items():
            role_result = await session.execute(
                select(RoleModel).where(RoleModel.code == role_code)
            )
            role = role_result.scalar_one_or_none()
            if not role:
                print(f"  [warn] Role '{role_code}' not found - skipping assignments")
                continue

            for perm_code in perm_codes:
                perm_id = perm_map.get(perm_code)
                if not perm_id:
                    continue

                existing_rp = await session.execute(
                    select(RolePermissionModel).where(
                        RolePermissionModel.role_id == role.id,
                        RolePermissionModel.permission_id == perm_id,
                    )
                )
                if existing_rp.scalar_one_or_none():
                    continue

                rp = RolePermissionModel(
                    role_id=role.id,
                    permission_id=perm_id,
                    created_by="seed_script",
                    modified_by="seed_script",
                )
                session.add(rp)
                print(f"  [link] {role_code} <- {perm_code}")

        await uow.commit()
        print("\nOK RBAC seed complete.")

    # 3. Assign ADMIN role to all existing users who don't have any role assignment
    async with UnitOfWork() as uow:
        session = uow.session
        print("\nAssigning default role to existing users without role assignments...")

        # Find the ADMIN role
        admin_role_result = await session.execute(
            select(RoleModel).where(RoleModel.code == "ADMIN")
        )
        admin_role = admin_role_result.scalar_one_or_none()
        if not admin_role:
            print("  [warn] ADMIN role not found - skipping user assignments")
        else:
            # Find all users
            users_result = await session.execute(select(UserModel))
            users = users_result.scalars().all()

            for user in users:
                # Check if user already has any role assignment
                existing_assignment = await session.execute(
                    select(RoleAssignmentModel).where(
                        RoleAssignmentModel.user_id == user.id,
                    )
                )
                if existing_assignment.scalar_one_or_none():
                    print(f"  [skip] User '{user.username}' already has a role assignment")
                    continue

                # Assign ADMIN role as default for existing users
                assignment = RoleAssignmentModel(
                    user_id=user.id,
                    role_id=admin_role.id,
                    tenant_id=None,
                    is_active=True,
                    created_by="seed_script",
                    modified_by="seed_script",
                )
                session.add(assignment)
                print(f"  [new]  User '{user.username}' -> Role 'ADMIN'")

        await uow.commit()
        print("\nOK Role assignments complete.")


if __name__ == "__main__":
    print("Seeding RBAC permissions...")
    asyncio.run(seed())

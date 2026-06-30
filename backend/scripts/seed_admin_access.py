"""
Seed script: Grant all permissions to the ADMIN role and assign it to the admin user.

Usage:
    python -m scripts.seed_admin_access
"""

import asyncio
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models.role_model import (
    PermissionModel,
    RoleAssignmentModel,
    RoleModel,
    RolePermissionModel,
)
from src.infrastructure.database.models.user_model import UserModel
from src.infrastructure.database.session import async_session_factory


# All permissions to create (covers menu, API, and key operations)
PERMISSIONS = [
    # MENU permissions (control sidebar visibility)
    {"code": "menu.dashboard", "name": "Dashboard Menu", "scope": "MENU", "resource": "dashboard", "action": "READ"},
    {"code": "menu.reports", "name": "Reports Menu", "scope": "MENU", "resource": "reports", "action": "READ"},
    {"code": "menu.users", "name": "Users Menu", "scope": "MENU", "resource": "users", "action": "READ"},
    {"code": "menu.roles", "name": "Roles & Permissions Menu", "scope": "MENU", "resource": "roles", "action": "READ"},
    {"code": "menu.audit_logs", "name": "Audit Logs Menu", "scope": "MENU", "resource": "audit_logs", "action": "READ"},
    {"code": "menu.workflows", "name": "Workflows Menu", "scope": "MENU", "resource": "workflows", "action": "READ"},
    {"code": "menu.settings", "name": "Settings Menu", "scope": "MENU", "resource": "settings", "action": "READ"},
    {"code": "menu.services", "name": "Services Menu", "scope": "MENU", "resource": "services", "action": "READ"},
    {"code": "menu.masters", "name": "Masters Menu", "scope": "MENU", "resource": "masters", "action": "READ"},
    # API permissions (control endpoint access)
    {"code": "rbac.read", "name": "RBAC Read", "scope": "API", "resource": "rbac", "action": "READ"},
    {"code": "rbac.create", "name": "RBAC Create", "scope": "API", "resource": "rbac", "action": "CREATE"},
    {"code": "rbac.update", "name": "RBAC Update", "scope": "API", "resource": "rbac", "action": "UPDATE"},
    {"code": "rbac.delete", "name": "RBAC Delete", "scope": "API", "resource": "rbac", "action": "DELETE"},
    {"code": "audit.read", "name": "Audit Log Read", "scope": "API", "resource": "audit", "action": "READ"},
    {"code": "users.read", "name": "Users Read", "scope": "API", "resource": "users", "action": "READ"},
    {"code": "users.create", "name": "Users Create", "scope": "API", "resource": "users", "action": "CREATE"},
    {"code": "users.update", "name": "Users Update", "scope": "API", "resource": "users", "action": "UPDATE"},
    {"code": "users.delete", "name": "Users Delete", "scope": "API", "resource": "users", "action": "DELETE"},
    {"code": "orders.read", "name": "Orders Read", "scope": "API", "resource": "orders", "action": "READ"},
    {"code": "orders.create", "name": "Orders Create", "scope": "API", "resource": "orders", "action": "CREATE"},
    {"code": "orders.update", "name": "Orders Update", "scope": "API", "resource": "orders", "action": "UPDATE"},
    {"code": "reports.export", "name": "Reports Export", "scope": "API", "resource": "reports", "action": "EXPORT"},
    {"code": "workflows.read", "name": "Workflows Read", "scope": "API", "resource": "workflows", "action": "READ"},
    {"code": "workflows.create", "name": "Workflows Create", "scope": "API", "resource": "workflows", "action": "CREATE"},
    {"code": "workflows.update", "name": "Workflows Update", "scope": "API", "resource": "workflows", "action": "UPDATE"},
]


async def seed_admin_access() -> None:
    """Create permissions, assign all to ADMIN role, assign ADMIN role to admin user."""
    async with async_session_factory() as session:
        # 1. Find the ADMIN role
        result = await session.execute(
            select(RoleModel).where(RoleModel.code == "ADMIN")
        )
        admin_role = result.scalar_one_or_none()
        if not admin_role:
            print("ERROR: ADMIN role not found! Run migrations first.")
            return

        print(f"Found ADMIN role: {admin_role.id}")

        # 2. Create permissions (skip if already exists)
        permission_ids = []
        for perm_data in PERMISSIONS:
            existing = await session.execute(
                select(PermissionModel).where(PermissionModel.code == perm_data["code"])
            )
            perm = existing.scalar_one_or_none()
            if perm:
                print(f"  Permission '{perm_data['code']}' already exists.")
                permission_ids.append(str(perm.id))
            else:
                perm = PermissionModel(
                    id=uuid4(),
                    code=perm_data["code"],
                    name=perm_data["name"],
                    description=f"{perm_data['name']} permission",
                    scope=perm_data["scope"],
                    resource=perm_data["resource"],
                    action=perm_data["action"],
                    is_active=True,
                    created_by="seed_script",
                    modified_by="seed_script",
                )
                session.add(perm)
                permission_ids.append(str(perm.id))
                print(f"  Created permission: {perm_data['code']}")

        await session.flush()

        # 3. Grant all permissions to ADMIN role (skip duplicates)
        for perm_id in permission_ids:
            existing_rp = await session.execute(
                select(RolePermissionModel).where(
                    RolePermissionModel.role_id == str(admin_role.id),
                    RolePermissionModel.permission_id == perm_id,
                )
            )
            if existing_rp.scalar_one_or_none():
                continue
            rp = RolePermissionModel(
                id=uuid4(),
                role_id=str(admin_role.id),
                permission_id=perm_id,
                created_by="seed_script",
                modified_by="seed_script",
            )
            session.add(rp)

        print(f"\nGranted {len(permission_ids)} permissions to ADMIN role.")

        # 4. Assign ADMIN role to admin user
        admin_user_result = await session.execute(
            select(UserModel).where(UserModel.username == "admin")
        )
        admin_user = admin_user_result.scalar_one_or_none()
        if not admin_user:
            print("ERROR: admin user not found!")
            return

        existing_assignment = await session.execute(
            select(RoleAssignmentModel).where(
                RoleAssignmentModel.user_id == str(admin_user.id),
                RoleAssignmentModel.role_id == str(admin_role.id),
                RoleAssignmentModel.is_active == True,  # noqa: E712
            )
        )
        if existing_assignment.scalar_one_or_none():
            print(f"Admin user already has ADMIN role assigned.")
        else:
            assignment = RoleAssignmentModel(
                id=uuid4(),
                user_id=str(admin_user.id),
                role_id=str(admin_role.id),
                tenant_id=None,
                is_active=True,
                created_by="seed_script",
                modified_by="seed_script",
            )
            session.add(assignment)
            print(f"Assigned ADMIN role to admin user ({admin_user.id}).")

        await session.commit()
        print("\nDone! Admin user now has full access.")


if __name__ == "__main__":
    asyncio.run(seed_admin_access())

"""
Seed script for RBAC permissions.
Populates default menu, API, and field-level permissions.
Run via: python -m scripts.seed_rbac

This is idempotent — re-running will skip existing permissions.
"""

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from src.infrastructure.database.session import async_session_factory
from src.infrastructure.database.models.role_model import (
    PermissionModel,
    RoleAssignmentModel,
    RoleModel,
    RolePermissionModel,
)
from src.infrastructure.database.models.user_model import UserModel

# ─── Default Permission Definitions ───

DEFAULT_PERMISSIONS = [
    # Menu permissions — control sidebar/navigation visibility
    {"code": "menu.dashboard", "name": "Dashboard Menu", "scope": "MENU", "resource": "dashboard", "action": "READ"},
    {"code": "menu.users", "name": "Users Menu", "scope": "MENU", "resource": "users", "action": "READ"},
    {"code": "menu.roles", "name": "Roles Menu", "scope": "MENU", "resource": "roles", "action": "READ"},
    {"code": "menu.audit_logs", "name": "Audit Logs Menu", "scope": "MENU", "resource": "audit_logs", "action": "READ"},
    {"code": "menu.services", "name": "Services Menu", "scope": "MENU", "resource": "services", "action": "READ"},
    {"code": "menu.reports", "name": "Reports Menu", "scope": "MENU", "resource": "reports", "action": "READ"},
    {"code": "menu.settings", "name": "Settings Menu", "scope": "MENU", "resource": "settings", "action": "READ"},
    {"code": "menu.workflows", "name": "Workflows Menu", "scope": "MENU", "resource": "workflows", "action": "READ"},

    # Masters menu permissions — control visibility of masters sub-items
    {"code": "menu.entities", "name": "Entities Menu", "scope": "MENU", "resource": "entities", "action": "READ"},
    {"code": "menu.vendors", "name": "Vendors Menu", "scope": "MENU", "resource": "vendors", "action": "READ"},
    {"code": "menu.customers", "name": "Customers Menu", "scope": "MENU", "resource": "customers", "action": "READ"},
    {"code": "menu.products", "name": "Products Menu", "scope": "MENU", "resource": "products", "action": "READ"},
    {"code": "menu.product_details", "name": "Product Details Menu", "scope": "MENU", "resource": "product_details", "action": "READ"},
    {"code": "menu.agreements", "name": "Agreements Menu", "scope": "MENU", "resource": "agreements", "action": "READ"},
    {"code": "menu.mappings", "name": "Mappings Menu", "scope": "MENU", "resource": "mappings", "action": "READ"},
    {"code": "menu.invoices", "name": "Invoices Menu", "scope": "MENU", "resource": "invoices", "action": "READ"},

    # Masters CRUD permissions — control action buttons on masters pages
    {"code": "entity.read", "name": "Read Entity", "scope": "API", "resource": "entities", "action": "READ"},
    {"code": "entity.create", "name": "Create Entity", "scope": "API", "resource": "entities", "action": "CREATE"},
    {"code": "entity.update", "name": "Update Entity", "scope": "API", "resource": "entities", "action": "UPDATE"},
    {"code": "vendor.read", "name": "Read Vendor", "scope": "API", "resource": "vendors", "action": "READ"},
    {"code": "vendor.create", "name": "Create Vendor", "scope": "API", "resource": "vendors", "action": "CREATE"},
    {"code": "vendor.update", "name": "Update Vendor", "scope": "API", "resource": "vendors", "action": "UPDATE"},
    {"code": "vendor.deactivate", "name": "Deactivate Vendor", "scope": "API", "resource": "vendors", "action": "DELETE"},
    {"code": "vendor.bulk_upload", "name": "Bulk Upload Vendors", "scope": "API", "resource": "vendors", "action": "IMPORT"},
    {"code": "customer.read", "name": "Read Customer", "scope": "API", "resource": "customers", "action": "READ"},
    {"code": "customer.create", "name": "Create Customer", "scope": "API", "resource": "customers", "action": "CREATE"},
    {"code": "customer.update", "name": "Update Customer", "scope": "API", "resource": "customers", "action": "UPDATE"},
    {"code": "customer.delete", "name": "Delete Customer", "scope": "API", "resource": "customers", "action": "DELETE"},
    {"code": "customer.bulk_upload", "name": "Bulk Upload Customers", "scope": "API", "resource": "customers", "action": "IMPORT"},
    {"code": "product_master.read", "name": "Read Product Master", "scope": "API", "resource": "products", "action": "READ"},
    {"code": "product_master.create", "name": "Create Product Master", "scope": "API", "resource": "products", "action": "CREATE"},
    {"code": "product_master.update", "name": "Update Product Master", "scope": "API", "resource": "products", "action": "UPDATE"},
    {"code": "product_detail.read", "name": "Read Product Detail", "scope": "API", "resource": "product_details", "action": "READ"},
    {"code": "product_detail.create", "name": "Create Product Detail", "scope": "API", "resource": "product_details", "action": "CREATE"},
    {"code": "product_detail.update", "name": "Update Product Detail", "scope": "API", "resource": "product_details", "action": "UPDATE"},
    {"code": "agreement.read", "name": "Read Agreement", "scope": "API", "resource": "agreements", "action": "READ"},
    {"code": "agreement.create", "name": "Create Agreement", "scope": "API", "resource": "agreements", "action": "CREATE"},
    {"code": "agreement.update", "name": "Update Agreement", "scope": "API", "resource": "agreements", "action": "UPDATE"},
    {"code": "agreement.bulk_upload", "name": "Bulk Upload Agreements", "scope": "API", "resource": "agreements", "action": "IMPORT"},
    {"code": "mapping.read", "name": "Read Mapping", "scope": "API", "resource": "mappings", "action": "READ"},
    {"code": "mapping.create", "name": "Create Mapping", "scope": "API", "resource": "mappings", "action": "CREATE"},
    {"code": "mapping.update", "name": "Update Mapping", "scope": "API", "resource": "mappings", "action": "UPDATE"},
    {"code": "mapping.delete", "name": "Delete Mapping", "scope": "API", "resource": "mappings", "action": "DELETE"},
    {"code": "mapping.bulk_upload", "name": "Bulk Upload Mappings", "scope": "API", "resource": "mappings", "action": "IMPORT"},
    {"code": "invoice.read", "name": "Read Invoice", "scope": "API", "resource": "invoices", "action": "READ"},
    {"code": "invoice.create", "name": "Create Invoice", "scope": "API", "resource": "invoices", "action": "CREATE"},
    {"code": "invoice.update_payment", "name": "Update Invoice Payment", "scope": "API", "resource": "invoices", "action": "UPDATE"},
    {"code": "invoice.settle", "name": "Settle Invoice", "scope": "API", "resource": "invoices", "action": "EXECUTE"},

    # API permissions — control endpoint access
    {"code": "users.list", "name": "List Users", "scope": "API", "resource": "users", "action": "READ"},
    {"code": "users.create", "name": "Create User", "scope": "API", "resource": "users", "action": "CREATE"},
    {"code": "users.update", "name": "Update User", "scope": "API", "resource": "users", "action": "UPDATE"},
    {"code": "users.delete", "name": "Delete User", "scope": "API", "resource": "users", "action": "DELETE"},
    {"code": "users.export", "name": "Export Users", "scope": "API", "resource": "users", "action": "EXPORT"},
    {"code": "users.import", "name": "Import Users", "scope": "API", "resource": "users", "action": "IMPORT"},
    {"code": "roles.list", "name": "List Roles", "scope": "API", "resource": "roles", "action": "READ"},
    {"code": "roles.create", "name": "Create Role", "scope": "API", "resource": "roles", "action": "CREATE"},
    {"code": "roles.update", "name": "Update Role", "scope": "API", "resource": "roles", "action": "UPDATE"},
    {"code": "roles.assign", "name": "Assign Roles", "scope": "API", "resource": "roles", "action": "EXECUTE"},
    {"code": "audit.read", "name": "View Audit Logs", "scope": "API", "resource": "audit_logs", "action": "READ"},
    {"code": "reports.export", "name": "Export Reports", "scope": "API", "resource": "reports", "action": "EXPORT"},

    # RBAC management permissions — granular control over roles & permissions CRUD
    {"code": "rbac.read", "name": "View Roles & Permissions", "scope": "API", "resource": "rbac", "action": "READ"},
    {"code": "rbac.create", "name": "Create Roles & Permissions", "scope": "API", "resource": "rbac", "action": "CREATE"},
    {"code": "rbac.update", "name": "Update Roles & Permissions", "scope": "API", "resource": "rbac", "action": "UPDATE"},

    # Employee AD service permission
    {"code": "services.employee_ad", "name": "Access Employee AD Service", "scope": "API", "resource": "services", "action": "EXECUTE"},

    # Field-level permissions — control visibility of sensitive fields
    {"code": "users.salary.read", "name": "View Salary", "scope": "FIELD", "resource": "users.salary", "action": "READ"},
    {"code": "users.salary.update", "name": "Edit Salary", "scope": "FIELD", "resource": "users.salary", "action": "UPDATE"},
    {"code": "users.email.read", "name": "View Email", "scope": "FIELD", "resource": "users.email", "action": "READ"},
    {"code": "users.email.update", "name": "Edit Email", "scope": "FIELD", "resource": "users.email", "action": "UPDATE"},
    {"code": "users.phone.read", "name": "View Phone", "scope": "FIELD", "resource": "users.phone", "action": "READ"},
]

# Role → permission code assignments
ROLE_PERMISSIONS = {
    "ADMIN": [
        # Admin gets ALL permissions
        "menu.dashboard", "menu.users", "menu.roles", "menu.audit_logs",
        "menu.services", "menu.reports", "menu.settings", "menu.workflows",
        # Masters menu permissions
        "menu.entities", "menu.vendors", "menu.customers", "menu.products",
        "menu.product_details", "menu.agreements", "menu.mappings", "menu.invoices",
        # User management
        "users.list", "users.create", "users.update", "users.delete",
        "users.export", "users.import",
        "roles.list", "roles.create", "roles.update", "roles.assign",
        "audit.read", "reports.export",
        "rbac.read", "rbac.create", "rbac.update", "services.employee_ad",
        "users.salary.read", "users.salary.update",
        "users.email.read", "users.email.update", "users.phone.read",
        # Masters CRUD permissions
        "entity.read", "entity.create", "entity.update",
        "vendor.read", "vendor.create", "vendor.update", "vendor.deactivate", "vendor.bulk_upload",
        "customer.read", "customer.create", "customer.update", "customer.delete", "customer.bulk_upload",
        "product_master.read", "product_master.create", "product_master.update",
        "product_detail.read", "product_detail.create", "product_detail.update",
        "agreement.read", "agreement.create", "agreement.update", "agreement.bulk_upload",
        "mapping.read", "mapping.create", "mapping.update", "mapping.delete", "mapping.bulk_upload",
        "invoice.read", "invoice.create", "invoice.update_payment", "invoice.settle",
    ],
    "MANAGER": [
        "menu.dashboard", "menu.users", "menu.reports", "menu.services",
        # Masters menu permissions (read-only view)
        "menu.entities", "menu.vendors", "menu.customers", "menu.products",
        "menu.product_details", "menu.agreements", "menu.mappings", "menu.invoices",
        # Masters API READ permissions (view-only)
        "entity.read", "vendor.read", "customer.read",
        "product_master.read", "product_detail.read",
        "agreement.read", "mapping.read", "invoice.read",
        "users.list", "users.export",
        "reports.export",
        "users.email.read", "users.phone.read",
    ],
    "USER": [
        "menu.dashboard", "menu.services",
    ],
}


async def seed() -> None:
    """Seed default permissions and role-permission mappings."""
    async with async_session_factory() as session:
        # 1. Create permissions (skip existing)
        perm_map: dict[str, str] = {}  # code → id

        for perm_def in DEFAULT_PERMISSIONS:
            existing = await session.execute(
                select(PermissionModel).where(PermissionModel.code == perm_def["code"])
            )
            perm = existing.scalar_one_or_none()

            if perm:
                perm_map[perm.code] = str(perm.id)
                print(f"  [skip] Permission '{perm_def['code']}' already exists")
            else:
                new_perm = PermissionModel(
                    id=uuid4(),
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
                perm_map[perm_def["code"]] = str(new_perm.id)
                print(f"  [new]  Permission '{perm_def['code']}' created")

        await session.flush()

        # 2. Assign permissions to roles
        for role_code, perm_codes in ROLE_PERMISSIONS.items():
            role_result = await session.execute(
                select(RoleModel).where(RoleModel.code == role_code)
            )
            role = role_result.scalar_one_or_none()
            if not role:
                print(f"  [warn] Role '{role_code}' not found — skipping assignments")
                continue

            for perm_code in perm_codes:
                perm_id = perm_map.get(perm_code)
                if not perm_id:
                    continue

                existing_rp = await session.execute(
                    select(RolePermissionModel).where(
                        RolePermissionModel.role_id == str(role.id),
                        RolePermissionModel.permission_id == perm_id,
                    )
                )
                if existing_rp.scalar_one_or_none():
                    continue

                rp = RolePermissionModel(
                    id=uuid4(),
                    role_id=str(role.id),
                    permission_id=perm_id,
                    created_by="seed_script",
                    modified_by="seed_script",
                )
                session.add(rp)
                print(f"  [link] {role_code} ← {perm_code}")

        await session.commit()
        print("\n✓ RBAC seed complete.")

    # 3. Assign ADMIN role to all existing users who don't have any role assignment
    async with async_session_factory() as session:
        print("\nAssigning default role to existing users without role assignments...")

        # Find the ADMIN role
        admin_role_result = await session.execute(
            select(RoleModel).where(RoleModel.code == "ADMIN")
        )
        admin_role = admin_role_result.scalar_one_or_none()
        if not admin_role:
            print("  [warn] ADMIN role not found — skipping user assignments")
        else:
            # Find all users
            users_result = await session.execute(select(UserModel))
            users = users_result.scalars().all()

            for user in users:
                # Check if user already has any role assignment
                existing_assignment = await session.execute(
                    select(RoleAssignmentModel).where(
                        RoleAssignmentModel.user_id == str(user.id),
                    )
                )
                if existing_assignment.scalar_one_or_none():
                    print(f"  [skip] User '{user.username}' already has a role assignment")
                    continue

                # Assign ADMIN role as default for existing users
                assignment = RoleAssignmentModel(
                    id=uuid4(),
                    user_id=str(user.id),
                    role_id=str(admin_role.id),
                    tenant_id=None,
                    is_active=True,
                    created_by="seed_script",
                    modified_by="seed_script",
                )
                session.add(assignment)
                print(f"  [new]  User '{user.username}' → Role 'ADMIN'")

        await session.commit()
        print("\n✓ Role assignments complete.")


if __name__ == "__main__":
    print("Seeding RBAC permissions...")
    asyncio.run(seed())

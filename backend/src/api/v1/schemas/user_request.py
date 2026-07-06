"""
User request schemas (Pydantic v2).

Covers the Create User page (Requirement 4), the Edit User page
(Requirement 5), and HR-system import rows (Requirement 3). Business rules
that depend on cross-field/conditional logic (for example, the password
length requirement that only applies when Validate-with-AD is disabled, or
Entity/Role reference existence) are enforced in ``UserService`` so that the
service can raise the precise master validation/conflict errors.
"""

from uuid import UUID

from pydantic import BaseModel, Field


class CreateUserRequest(BaseModel):
    """Request to create a new user (Create User page, Requirement 4)."""

    employee_id: str = Field(..., description="HR Employee ID (required, unique)")
    username: str = Field(..., description="User Name / login (required, unique)")
    email: str | None = Field(default=None, max_length=255)
    first_name: str | None = Field(default=None, max_length=255)
    last_name: str | None = Field(default=None, max_length=255)
    entity_id: UUID | None = Field(
        default=None, description="Entity the user belongs to (must be active)"
    )
    role_ids: list[UUID] = Field(
        default_factory=list, description="Roles to assign (may be empty)"
    )
    password: str | None = Field(
        default=None,
        max_length=128,
        description="Required (>= 8 chars) unless Validate-with-AD is enabled",
    )
    is_validate_ad: bool = Field(
        default=True, description="If true, authenticate via Active Directory"
    )


class EditUserRequest(BaseModel):
    """Request to edit an existing user (Edit User page, Requirement 5).

    Employee ID and User Name are intentionally absent — they are immutable on
    edit (Requirement 5.1). Only fields explicitly supplied are applied.
    """

    email: str | None = Field(default=None, max_length=255)
    first_name: str | None = Field(default=None, max_length=255)
    last_name: str | None = Field(default=None, max_length=255)
    entity_id: UUID | None = Field(
        default=None, description="Entity the user belongs to (must be active)"
    )
    role_ids: list[UUID] | None = Field(
        default=None,
        description="When supplied, replaces all existing role assignments",
    )
    is_active: bool | None = Field(
        default=None, description="When false, blocks the user from authenticating"
    )
    is_blocked: bool | None = Field(
        default=None, description="When true, blocks the user regardless of active status"
    )
    is_validate_ad: bool | None = Field(
        default=None, description="Toggle Active Directory authentication"
    )
    change_password: str | None = Field(
        default=None,
        max_length=128,
        description=(
            "Non-empty (>= 8 chars) sets a new password when AD is disabled; "
            "empty/omitted leaves the existing password unchanged"
        ),
    )


class HrImportRow(BaseModel):
    """A single user row imported from the HR system (Requirement 3)."""

    employee_id: str = Field(..., description="HR Employee ID — the upsert key")
    username: str | None = Field(
        default=None, description="Login name; defaults to Employee ID when absent"
    )
    email: str | None = Field(default=None, max_length=255)
    first_name: str | None = Field(default=None, max_length=255)
    last_name: str | None = Field(default=None, max_length=255)
    company_code: str | None = Field(
        default=None, description="Used to resolve the Entity when non-empty"
    )
    entity_name: str | None = Field(
        default=None, description="Used to resolve the Entity when Company Code is empty"
    )
    is_validate_ad: bool = Field(default=True)


class UpdateUserRequest(BaseModel):
    """Legacy lightweight update request (retained for backward compatibility)."""

    is_active: bool | None = None
    is_blocked: bool | None = None
    is_validate_ad: bool | None = None
    role_id: UUID | None = Field(default=None, description="Role ID to assign (replaces existing)")

"""
Entity Master request/response schemas (Pydantic v2).

These adapt the Pydantic-agnostic ``EntityService`` (which speaks in terms of
``EntityCreateInput`` / ``EntityUpdateInput`` and returns ``EntityEntity``) to
the HTTP boundary.

Partial updates rely on ``model_fields_set`` so the controller can distinguish
"field not supplied" (leave unchanged, Req 1.8) from "field set to null"
(explicitly clear a nullable field).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.application.services.masters.entity_service import EntityDropdownItem
from src.domain.entities.masters.entity import EntityEntity


class CreateEntityRequest(BaseModel):
    """Payload for creating an Entity.

    Field-level required/length/uniqueness rules (Req 1.2–1.4) and the
    ``is_active`` default (Req 1.5) are enforced by ``EntityService``.
    """

    entity_name: str = Field(..., description="Entity (legal company) name")
    short_code: str | None = Field(default=None, description="Optional short code")
    company_code: str | None = Field(default=None, description="Optional company code")
    is_active: bool | None = Field(
        default=None,
        description="Active flag; defaults to true when omitted",
    )
    workflow_definition_id: UUID | None = Field(
        default=None,
        description="Workflow definition to use for claim approvals under this entity",
    )


class UpdateEntityRequest(BaseModel):
    """Partial-update payload for an Entity.

    Every field is optional. Only fields present in the request body are
    applied; omitted fields are left unchanged (Req 1.8). ``short_code`` and
    ``company_code`` may be explicitly set to ``null`` to clear them.
    """

    entity_name: str | None = Field(default=None)
    short_code: str | None = Field(default=None)
    company_code: str | None = Field(default=None)
    is_active: bool | None = Field(default=None)
    workflow_definition_id: UUID | None = Field(default=None)


class EntityResponse(BaseModel):
    """Entity representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    entity_name: str
    short_code: str | None = None
    company_code: str | None = None
    is_active: bool
    workflow_definition_id: UUID | None = None
    created_by: str
    created_date: datetime
    modified_by: str
    modified_date: datetime

    @classmethod
    def from_entity(cls, entity: EntityEntity) -> "EntityResponse":
        """Build a response from a domain ``EntityEntity``."""
        return cls(
            id=entity.id,
            entity_name=entity.entity_name,
            short_code=entity.short_code,
            company_code=entity.company_code,
            is_active=entity.is_active,
            workflow_definition_id=entity.workflow_definition_id,
            created_by=entity.created_by,
            created_date=entity.created_date,
            modified_by=entity.modified_by,
            modified_date=entity.modified_date,
        )


class EntityDropdownItemResponse(BaseModel):
    """A single active-entity dropdown option (id + display label)."""

    id: UUID
    label: str

    @classmethod
    def from_item(cls, item: EntityDropdownItem) -> "EntityDropdownItemResponse":
        """Build a response from the service's dropdown dataclass."""
        return cls(id=item.id, label=item.label)

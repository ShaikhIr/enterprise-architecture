"""
Entity (legal company) domain entity.

Represents a legal company entity (e.g. Emcure Pharmaceuticals Ltd) that each
user belongs to. Inherits identity and audit fields from ``BaseEntity``.
"""

from dataclasses import dataclass, field
from uuid import UUID

from src.domain.entities.base_entity import BaseEntity


@dataclass
class EntityEntity(BaseEntity):
    """
    Entity Master aggregate root.

    Business Rules:
    - Entity Name is required and must be unique, compared case-insensitively
      after trimming surrounding whitespace (enforced at repository level).
    - Company Code, when supplied, must be unique under the same trimmed,
      case-insensitive comparison.
    - New entities default to active.
    - workflow_definition_id links to the approval workflow used for claims
      under this entity.
    """

    entity_name: str = field(default="")
    short_code: str | None = field(default=None)
    company_code: str | None = field(default=None)
    is_active: bool = field(default=True)
    workflow_definition_id: UUID | None = field(default=None)

    def deactivate(self, modified_by: str) -> None:
        """Mark the entity inactive."""
        self.is_active = False
        self.mark_modified(modified_by)

    def activate(self, modified_by: str) -> None:
        """Mark the entity active."""
        self.is_active = True
        self.mark_modified(modified_by)

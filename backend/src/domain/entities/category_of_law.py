"""
Category of law domain entity.
Classifies legislations, e.g. "Labour Law", "Environmental Law".
"""

from dataclasses import dataclass
from uuid import UUID

from src.domain.entities.base_entity import BaseEntity


@dataclass(kw_only=True)
class CategoryOfLaw(BaseEntity):
    """
    A classification of law used to group legislations.

    Declared `kw_only` so mandatory fields can stay mandatory despite
    BaseEntity supplying defaults for the audit fields.

    Attributes:
        code: Unique business key, e.g. "LABOUR".
        name: Display name. Unique within its state scope.
        description: Optional explanatory text.
        state_id: Owning state when the category is state specific.
            Left empty for categories that apply country-wide.
        is_active: Soft retirement flag.
    """

    code: str
    name: str
    description: str = ""
    state_id: UUID | None = None
    is_active: bool = True

    @property
    def is_state_specific(self) -> bool:
        """True when the category is scoped to a single state."""
        return self.state_id is not None

    def deactivate(self) -> None:
        """Retire the category without deleting history."""
        self.is_active = False

    def activate(self) -> None:
        """Restore a retired category."""
        self.is_active = True

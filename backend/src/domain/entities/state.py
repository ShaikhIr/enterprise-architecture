"""
State domain entity.
Second-level jurisdiction master, always owned by a country.
"""

from dataclasses import dataclass

from src.domain.entities.base_entity import BaseEntity


@dataclass(kw_only=True)
class State(BaseEntity):
    """
    A state, province or union territory belonging to a country.

    Declared `kw_only` so mandatory fields can stay mandatory despite
    BaseEntity supplying defaults for the audit fields.

    Attributes:
        code: Unique business key, e.g. "IN-MH".
        name: Display name, e.g. "Maharashtra". Unique within its country.
        country_id: Owning country. Required.
        is_union_territory: Distinguishes UTs from full states.
        is_active: Soft retirement flag.
    """

    code: str
    name: str
    country_id: int
    is_union_territory: bool = False
    is_active: bool = True

    def deactivate(self) -> None:
        """Retire the state without deleting history."""
        self.is_active = False

    def activate(self) -> None:
        """Restore a retired state."""
        self.is_active = True

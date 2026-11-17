"""
Legislation domain entity.
An act / statute / regulation issued by a jurisdiction.
"""

from dataclasses import dataclass
from datetime import date

from src.domain.entities.base_entity import BaseEntity


@dataclass(kw_only=True)
class Legislation(BaseEntity):
    """
    An act, statute or regulation that compliance obligations derive from.

    `country_id` and `category_of_law_id` are required. `state_id` is optional
    so central (federal) legislations can be modelled at country level only.

    Declared `kw_only` so mandatory fields can stay mandatory despite
    BaseEntity supplying defaults for the audit fields.

    Attributes:
        code: Unique business key, e.g. "IN-FACT-1948".
        name: Full title of the act.
        description: Optional summary.
        category_of_law_id: Classification this legislation belongs to.
        country_id: Owning country. Required.
        state_id: Owning state, or empty for central legislation.
        legislation_number: Official reference, e.g. "Act No. 63 of 1948".
        effective_date: Date the legislation came into force.
        is_active: Soft retirement flag (repealed acts stay referable).
    """

    code: str
    name: str
    category_of_law_id: int
    country_id: int
    description: str = ""
    state_id: int | None = None
    legislation_number: str | None = None
    effective_date: date | None = None
    is_active: bool = True

    @property
    def is_central(self) -> bool:
        """True when the legislation applies country-wide rather than per state."""
        return self.state_id is None

    def deactivate(self) -> None:
        """Retire (e.g. repeal) the legislation without deleting history."""
        self.is_active = False

    def activate(self) -> None:
        """Restore a retired legislation."""
        self.is_active = True

"""
Rule domain entity.
A rule / section / schedule framed under a legislation.
"""

from dataclasses import dataclass
from datetime import date

from src.domain.entities.base_entity import BaseEntity


@dataclass(kw_only=True)
class Rule(BaseEntity):
    """
    A rule framed under a legislation; the level compliance tasks attach to.

    `legislation_id` and `country_id` are required. `state_id` is optional and
    mirrors the parent legislation's jurisdiction.

    Declared `kw_only` so mandatory fields can stay mandatory despite
    BaseEntity supplying defaults for the audit fields.

    Attributes:
        code: Unique business key, e.g. "IN-FACT-1948-R5".
        name: Rule title.
        description: Optional text of the obligation.
        legislation_id: Parent legislation. Required.
        country_id: Owning country. Required.
        state_id: Owning state, or empty for central rules.
        rule_number: Official reference, e.g. "Rule 5(2)".
        effective_date: Date the rule came into force.
        is_active: Soft retirement flag.
    """

    code: str
    name: str
    legislation_id: int
    country_id: int
    description: str = ""
    state_id: int | None = None
    rule_number: str | None = None
    effective_date: date | None = None
    is_active: bool = True

    def deactivate(self) -> None:
        """Retire the rule without deleting history."""
        self.is_active = False

    def activate(self) -> None:
        """Restore a retired rule."""
        self.is_active = True

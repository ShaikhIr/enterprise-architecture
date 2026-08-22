"""
Country domain entity.
Top-level jurisdiction master: every legislation and rule rolls up to a country.
"""

from dataclasses import dataclass

from src.domain.entities.base_entity import BaseEntity


@dataclass(kw_only=True)
class Country(BaseEntity):
    """
    A sovereign country under whose jurisdiction legislations exist.

    Declared `kw_only` so mandatory fields can stay mandatory despite
    BaseEntity supplying defaults for the audit fields.

    Attributes:
        code: ISO 3166-1 alpha-2 code, e.g. "IN". Unique business key.
        name: Display name, e.g. "India".
        iso3_code: ISO 3166-1 alpha-3 code, e.g. "IND".
        dial_code: International dialling prefix, e.g. "+91".
        currency_code: ISO 4217 currency code, e.g. "INR".
        is_active: Soft retirement flag; inactive countries stay referable.
    """

    code: str
    name: str
    iso3_code: str | None = None
    dial_code: str | None = None
    currency_code: str | None = None
    is_active: bool = True

    def deactivate(self) -> None:
        """Retire the country without deleting history."""
        self.is_active = False

    def activate(self) -> None:
        """Restore a retired country."""
        self.is_active = True

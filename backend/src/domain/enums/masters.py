"""
Status and type enums for the LACM master entities.

All values are stored as ``String`` columns in the infrastructure layer with an
application-level constraint, so each member's value is the canonical
human-readable string used across the system.
"""

from enum import StrEnum


class VendorStatus(StrEnum):
    """Lifecycle status of a Vendor master record."""

    Active = "Active"
    Inactive = "Inactive"


class CustomerStatus(StrEnum):
    """Lifecycle status of a Customer master record."""

    Active = "Active"
    Inactive = "Inactive"


class ProductStatus(StrEnum):
    """Lifecycle status of a Product Master or Product Detail record."""

    Active = "Active"
    Inactive = "Inactive"


class AgreementType(StrEnum):
    """Whether an Agreement is the original or a renewal."""

    Original = "Original"
    Renewal = "Renewal"


class AgreementStatus(StrEnum):
    """Lifecycle status of an Agreement."""

    Active = "Active"
    Expired = "Expired"
    Renewed = "Renewed"


class MappingStatus(StrEnum):
    """Lifecycle status of a Vendor-Customer Mapping."""

    Active = "Active"
    Expired = "Expired"


class InvoiceStatus(StrEnum):
    """Lifecycle status of an Invoice Header."""

    Open = "Open"
    PaymentCleared = "Payment Cleared"
    Settled = "Settled"

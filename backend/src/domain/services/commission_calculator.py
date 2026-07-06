"""
Commission slab calculator (pure domain service).

This module implements the deterministic slab-based commission rule described in
Requirement 12. It is a pure-logic component with **no I/O**: every function is a
deterministic transformation of its inputs, which keeps the rule trivially
testable and reusable by the Agreement service and the commission engine.

Percentages are handled with :class:`decimal.Decimal` (rather than ``float``) to
avoid binary floating-point rounding error and to match the ``Numeric(5, 2)``
precision used by the Agreement model in the infrastructure layer.

Rules implemented:

* **Delay Days** = Payment Clearing Date - Due Date, measured in whole calendar
  days (Requirement 12.3).
* **Applicable Commission %**:
    - when Delay Days <= 0  -> Max Commission % (Requirement 12.1);
    - when Delay Days > 0   -> ``max(Max% - ceil(delay / slab) * Reduction%, Min%)``
      (Requirement 12.2).
"""

import math
from datetime import date
from decimal import Decimal


def compute_delay_days(due_date: date, payment_clearing_date: date) -> int:
    """Return the whole calendar days from ``due_date`` to ``payment_clearing_date``.

    Delay Days is defined as ``Payment Clearing Date - Due Date`` (Requirement
    12.3). A negative or zero result means the payment cleared on or before the
    due date.

    Args:
        due_date: The date by which the invoice payment was expected.
        payment_clearing_date: The date the payment actually cleared.

    Returns:
        The signed number of whole calendar days between the two dates.
    """
    return (payment_clearing_date - due_date).days


def compute_applicable_commission(
    delay_days: int,
    slab_in_days: int,
    max_commission: Decimal,
    min_commission: Decimal,
    reduction: Decimal,
) -> Decimal:
    """Compute the Applicable Commission % for a given payment delay.

    When ``delay_days`` is less than or equal to zero, the full Max Commission %
    applies (Requirement 12.1). Otherwise the delay is divided into slabs: the
    bucket is the ceiling of ``delay_days / slab_in_days`` and the applicable
    commission is reduced by ``bucket * reduction``, floored at the Min
    Commission % (Requirement 12.2).

    Args:
        delay_days: Whole calendar days of payment delay (see
            :func:`compute_delay_days`).
        slab_in_days: Length of one slab bucket in days; must be greater than 0.
        max_commission: The maximum (starting) commission percentage.
        min_commission: The minimum (floor) commission percentage.
        reduction: The commission percentage removed per slab bucket.

    Returns:
        The Applicable Commission % as a :class:`~decimal.Decimal`.

    Raises:
        ValueError: If ``slab_in_days`` is not greater than 0.
    """
    if slab_in_days <= 0:
        raise ValueError("slab_in_days must be greater than 0")

    if delay_days <= 0:
        return max_commission

    bucket = math.ceil(delay_days / slab_in_days)
    reduced = max_commission - bucket * reduction
    return max(reduced, min_commission)

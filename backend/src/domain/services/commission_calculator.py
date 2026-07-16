"""
Commission slab calculator (pure domain service).

This module implements the deterministic slab-based commission rule described in
Requirements 3.2–3.9.  It is a pure-logic component with **no I/O**: every
function is a deterministic transformation of its inputs, keeping the rule
trivially testable and reusable across the application.

Percentages and money amounts are handled exclusively with
:class:`decimal.Decimal` (never ``float``) to avoid binary floating-point
rounding error and to match the ``Numeric`` precision used by the ORM models.

7-step formula (Requirements 3.2 – 3.9)
----------------------------------------
1. net_amount           = max(0, bill_amount_excl_gst − amount_deducted − tds_value)
2. commission_payable_base = net_amount + tds_value + amount_deducted
3. delay_days           = (payment_clearing_date − due_date).days
4. if delay_days ≤ 0   → applicable_commission_percent = max_commission_percent
5. else                 → bucket = ceil(delay_days / slab_in_days)
                          applicable_commission_percent =
                              max(max_commission_percent − bucket × reduction_percent,
                                  min_commission_percent)
6. commission_amount    = commission_payable_base × applicable_commission_percent / 100
7. gst_on_commission    = commission_amount × 0.18   (non-overridable)
   final_line_claim_amount = commission_amount + gst_on_commission
"""

import math
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------

@dataclass
class CommissionInputs:
    """All inputs required to execute the 7-step commission formula.

    Fields correspond directly to columns on the Claim Line and the matched
    Agreement Master (Requirements 3.2 – 3.9).
    """

    bill_amount_excl_gst: Decimal
    """Invoice bill amount excluding GST."""

    amount_deducted: Decimal
    """Amount deducted from the invoice (e.g. advance, quality deduction)."""

    tds_value: Decimal
    """TDS (Tax Deducted at Source) value on the invoice."""

    invoice_date: date
    """Date of the invoice (used for pre-condition validation in the service layer)."""

    due_date: date
    """Date by which payment was expected (Invoice Date + credit_days, or override)."""

    payment_clearing_date: date
    """Date the payment actually cleared in the bank."""

    slab_in_days: int
    """Length of one delay-reduction slab bucket in calendar days; must be > 0."""

    reduction_percent: Decimal
    """Commission percentage deducted per slab bucket when payment is delayed."""

    max_commission_percent: Decimal
    """Starting (maximum) commission rate; applied when payment is on-time or early."""

    min_commission_percent: Decimal
    """Floor commission rate; the result will never go below this value."""


@dataclass
class CommissionResult:
    """All 7 intermediate and final values produced by the commission formula.

    Every field is persisted to the Claim Line row for audit and display
    (Requirement 3.10).
    """

    net_amount: Decimal
    """Step 1: max(0, bill_amount_excl_gst − amount_deducted − tds_value)."""

    commission_payable_base: Decimal
    """Step 2: net_amount + tds_value + amount_deducted."""

    delay_days: int
    """Step 3: (payment_clearing_date − due_date).days (negative = early/on-time)."""

    applicable_commission_percent: Decimal
    """Steps 4/5: slab-derived commission rate."""

    commission_amount: Decimal
    """Step 6: commission_payable_base × applicable_commission_percent / 100."""

    gst_on_commission: Decimal
    """Step 7a: commission_amount × 18% (fixed, non-overridable per Req 3.8)."""

    final_line_claim_amount: Decimal
    """Step 7b: commission_amount + gst_on_commission."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_GST_RATE = Decimal("0.18")


def calculate(inputs: CommissionInputs) -> CommissionResult:
    """Execute all 7 commission formula steps.  Pure function — no I/O.

    Args:
        inputs: A :class:`CommissionInputs` instance carrying every parameter
            needed for the formula.

    Returns:
        A :class:`CommissionResult` with all 7 intermediate and final values.

    Raises:
        ValueError: If ``slab_in_days`` is not greater than 0.
    """
    if inputs.slab_in_days <= 0:
        raise ValueError("slab_in_days must be greater than 0")

    # Step 1 — Net Amount (floored at 0, Requirement 3.2)
    raw_net = inputs.bill_amount_excl_gst - inputs.amount_deducted - inputs.tds_value
    net_amount = max(Decimal("0"), raw_net)

    # Step 2 — Commission Payable Base (Requirement 3.3)
    # Algebraically equals bill_amount_excl_gst when net_amount ≥ 0
    commission_payable_base = net_amount + inputs.tds_value + inputs.amount_deducted

    # Step 3 — Delay Days (Requirement 3.4)
    delay_days: int = (inputs.payment_clearing_date - inputs.due_date).days

    # Steps 4 / 5 — Applicable Commission Percent (Requirements 3.5, 3.6)
    if delay_days <= 0:
        # On-time or early payment: full max commission applies
        applicable_commission_percent = inputs.max_commission_percent
    else:
        bucket = math.ceil(delay_days / inputs.slab_in_days)
        reduced = inputs.max_commission_percent - Decimal(bucket) * inputs.reduction_percent
        applicable_commission_percent = max(reduced, inputs.min_commission_percent)

    # Step 6 — Commission Amount (Requirement 3.7)
    commission_amount = commission_payable_base * applicable_commission_percent / Decimal("100")

    # Step 7 — GST and Final Amount (Requirements 3.8, 3.9)
    gst_on_commission = commission_amount * _GST_RATE
    final_line_claim_amount = commission_amount + gst_on_commission

    return CommissionResult(
        net_amount=net_amount,
        commission_payable_base=commission_payable_base,
        delay_days=delay_days,
        applicable_commission_percent=applicable_commission_percent,
        commission_amount=commission_amount,
        gst_on_commission=gst_on_commission,
        final_line_claim_amount=final_line_claim_amount,
    )


# ---------------------------------------------------------------------------
# Legacy helper functions (kept for backward compatibility)
# ---------------------------------------------------------------------------

def compute_delay_days(due_date: date, payment_clearing_date: date) -> int:
    """Return the whole calendar days from ``due_date`` to ``payment_clearing_date``.

    Delay Days is defined as ``Payment Clearing Date - Due Date`` (Requirement
    3.4). A negative or zero result means the payment cleared on or before the
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
    applies (Requirement 3.5). Otherwise the delay is divided into slabs: the
    bucket is the ceiling of ``delay_days / slab_in_days`` and the applicable
    commission is reduced by ``bucket * reduction``, floored at the Min
    Commission % (Requirement 3.6).

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

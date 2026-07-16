"""
Property-based tests for CommissionCalculator — Properties 1–5.

These tests exercise the pure ``calculate()`` function from
``src.domain.services.commission_calculator`` using Hypothesis to validate
the algebraic invariants described in the design's *Correctness Properties*
section.

**Validates: Requirements 3.2, 3.3, 3.5, 3.6, 3.8, 3.9, 22.1–22.7**
"""

from datetime import date
from decimal import Decimal

from hypothesis import assume, given, settings, HealthCheck
from hypothesis import strategies as st

from src.domain.services.commission_calculator import CommissionInputs, calculate

# ---------------------------------------------------------------------------
# Shared strategy helpers (from design spec)
# ---------------------------------------------------------------------------

amount_strategy = st.decimals(
    min_value=Decimal("0"),
    max_value=Decimal("1000000"),
    allow_nan=False,
    allow_infinity=False,
)

percent_strategy = st.decimals(
    min_value=Decimal("0"),
    max_value=Decimal("100"),
    allow_nan=False,
    allow_infinity=False,
)

days_strategy = st.integers(min_value=1, max_value=365)

date_strategy = st.dates(
    min_value=date(2020, 1, 1),
    max_value=date(2030, 12, 31),
)


# ---------------------------------------------------------------------------
# Property 1: Net Amount Floor Invariant
# ---------------------------------------------------------------------------

@settings(max_examples=200)
@given(
    bill=amount_strategy,
    deducted=amount_strategy,
    tds=amount_strategy,
    invoice_date=date_strategy,
    due_date=date_strategy,
    payment_clearing_date=date_strategy,
    slab_in_days=days_strategy,
    reduction_pct=percent_strategy,
    max_pct=percent_strategy,
    min_pct=percent_strategy,
)
def test_property_1_net_amount_floor_invariant(
    bill: Decimal,
    deducted: Decimal,
    tds: Decimal,
    invoice_date: date,
    due_date: date,
    payment_clearing_date: date,
    slab_in_days: int,
    reduction_pct: Decimal,
    max_pct: Decimal,
    min_pct: Decimal,
) -> None:
    """Property 1: Net Amount Floor Invariant.

    For any non-negative bill_amount_excl_gst, amount_deducted, and tds_value,
    the calculator SHALL produce net_amount = max(0, bill − deducted − tds),
    meaning net_amount is always ≥ 0 and equals the formula result when positive.

    **Validates: Requirements 3.2, 22.1**
    """
    assume(min_pct <= max_pct)
    # Ensure payment_clearing_date is not before invoice_date (required by service layer,
    # but the pure function has no such guard — keep dates sensible to avoid confusion)
    assume(payment_clearing_date >= invoice_date)

    inputs = CommissionInputs(
        bill_amount_excl_gst=bill,
        amount_deducted=deducted,
        tds_value=tds,
        invoice_date=invoice_date,
        due_date=due_date,
        payment_clearing_date=payment_clearing_date,
        slab_in_days=slab_in_days,
        reduction_percent=reduction_pct,
        max_commission_percent=max_pct,
        min_commission_percent=min_pct,
    )

    result = calculate(inputs)

    # net_amount must always be non-negative (Req 22.1)
    assert result.net_amount >= Decimal("0")

    # net_amount must equal the floored formula result (Req 3.2)
    expected_net = max(Decimal("0"), bill - deducted - tds)
    assert result.net_amount == expected_net


# ---------------------------------------------------------------------------
# Property 2: Commission Payable Base Identity
# ---------------------------------------------------------------------------

@settings(max_examples=200)
@given(
    bill=amount_strategy,
    deducted=amount_strategy,
    tds=amount_strategy,
    invoice_date=date_strategy,
    due_date=date_strategy,
    payment_clearing_date=date_strategy,
    slab_in_days=days_strategy,
    reduction_pct=percent_strategy,
    max_pct=percent_strategy,
    min_pct=percent_strategy,
)
def test_property_2_commission_payable_base_identity(
    bill: Decimal,
    deducted: Decimal,
    tds: Decimal,
    invoice_date: date,
    due_date: date,
    payment_clearing_date: date,
    slab_in_days: int,
    reduction_pct: Decimal,
    max_pct: Decimal,
    min_pct: Decimal,
) -> None:
    """Property 2: Commission Payable Base Identity.

    For any non-negative inputs, the calculator SHALL produce
    commission_payable_base = net_amount + tds_value + amount_deducted.
    Corollary: when amount_deducted = 0 and tds_value = 0, the base equals
    bill_amount_excl_gst.

    **Validates: Requirements 3.3, 22.2, 22.3**
    """
    assume(min_pct <= max_pct)
    assume(payment_clearing_date >= invoice_date)

    inputs = CommissionInputs(
        bill_amount_excl_gst=bill,
        amount_deducted=deducted,
        tds_value=tds,
        invoice_date=invoice_date,
        due_date=due_date,
        payment_clearing_date=payment_clearing_date,
        slab_in_days=slab_in_days,
        reduction_percent=reduction_pct,
        max_commission_percent=max_pct,
        min_commission_percent=min_pct,
    )

    result = calculate(inputs)

    # Primary identity: base = net + tds + deducted (Req 3.3, 22.2)
    assert result.commission_payable_base == result.net_amount + tds + deducted

    # Corollary: when both deductions are zero, base equals the bill amount (Req 22.3)
    if deducted == Decimal("0") and tds == Decimal("0"):
        # When both are zero, net_amount = max(0, bill) = bill (bill >= 0 always),
        # so base = net_amount + 0 + 0 = bill_amount_excl_gst
        assert result.commission_payable_base == bill


# ---------------------------------------------------------------------------
# Property 3: On-Time Payment Receives Maximum Commission
# ---------------------------------------------------------------------------

@settings(max_examples=200)
@given(
    bill=amount_strategy,
    deducted=amount_strategy,
    tds=amount_strategy,
    invoice_date=date_strategy,
    due_date=date_strategy,
    payment_clearing_date=date_strategy,
    slab_in_days=days_strategy,
    reduction_pct=percent_strategy,
    max_pct=percent_strategy,
    min_pct=percent_strategy,
)
def test_property_3_on_time_payment_receives_maximum_commission(
    bill: Decimal,
    deducted: Decimal,
    tds: Decimal,
    invoice_date: date,
    due_date: date,
    payment_clearing_date: date,
    slab_in_days: int,
    reduction_pct: Decimal,
    max_pct: Decimal,
    min_pct: Decimal,
) -> None:
    """Property 3: On-Time Payment Receives Maximum Commission.

    When payment_clearing_date <= due_date (delay_days <= 0), the calculator
    SHALL set applicable_commission_percent = max_commission_percent.

    **Validates: Requirements 3.5, 22.4**
    """
    assume(min_pct <= max_pct)
    # On-time or early payment constraint
    assume(payment_clearing_date <= due_date)
    assume(payment_clearing_date >= invoice_date)

    inputs = CommissionInputs(
        bill_amount_excl_gst=bill,
        amount_deducted=deducted,
        tds_value=tds,
        invoice_date=invoice_date,
        due_date=due_date,
        payment_clearing_date=payment_clearing_date,
        slab_in_days=slab_in_days,
        reduction_percent=reduction_pct,
        max_commission_percent=max_pct,
        min_commission_percent=min_pct,
    )

    result = calculate(inputs)

    # Must receive exactly max_commission_percent (Req 3.5, 22.4)
    assert result.applicable_commission_percent == max_pct


# ---------------------------------------------------------------------------
# Property 4: Commission Percent Floor — Delayed Payments
# ---------------------------------------------------------------------------

@settings(max_examples=200, suppress_health_check=[HealthCheck.filter_too_much])
@given(
    bill=amount_strategy,
    deducted=amount_strategy,
    tds=amount_strategy,
    invoice_date=date_strategy,
    due_date=date_strategy,
    payment_clearing_date=date_strategy,
    slab_in_days=days_strategy,
    reduction_pct=percent_strategy,
    max_pct=percent_strategy,
    min_pct=percent_strategy,
)
def test_property_4_commission_percent_floor_delayed_payments(
    bill: Decimal,
    deducted: Decimal,
    tds: Decimal,
    invoice_date: date,
    due_date: date,
    payment_clearing_date: date,
    slab_in_days: int,
    reduction_pct: Decimal,
    max_pct: Decimal,
    min_pct: Decimal,
) -> None:
    """Property 4: Commission Percent Floor — Delayed Payments.

    When payment_clearing_date > due_date (payment is late), the calculator
    SHALL produce min_commission_percent <= applicable_commission_percent
    <= max_commission_percent.

    **Validates: Requirements 3.6, 22.5, 22.6**
    """
    # Delayed payment constraint
    assume(payment_clearing_date > due_date)
    # Valid percentage range
    assume(min_pct <= max_pct)
    assume(payment_clearing_date >= invoice_date)

    inputs = CommissionInputs(
        bill_amount_excl_gst=bill,
        amount_deducted=deducted,
        tds_value=tds,
        invoice_date=invoice_date,
        due_date=due_date,
        payment_clearing_date=payment_clearing_date,
        slab_in_days=slab_in_days,
        reduction_percent=reduction_pct,
        max_commission_percent=max_pct,
        min_commission_percent=min_pct,
    )

    result = calculate(inputs)

    # Result must be within [min_pct, max_pct] — floored by design (Req 3.6, 22.5, 22.6)
    assert result.applicable_commission_percent >= min_pct
    assert result.applicable_commission_percent <= max_pct


# ---------------------------------------------------------------------------
# Property 5: GST Round-Trip — Final Amount Equals Commission × 1.18
# ---------------------------------------------------------------------------

@settings(max_examples=200)
@given(
    bill=amount_strategy,
    deducted=amount_strategy,
    tds=amount_strategy,
    invoice_date=date_strategy,
    due_date=date_strategy,
    payment_clearing_date=date_strategy,
    slab_in_days=days_strategy,
    reduction_pct=percent_strategy,
    max_pct=percent_strategy,
    min_pct=percent_strategy,
)
def test_property_5_gst_round_trip(
    bill: Decimal,
    deducted: Decimal,
    tds: Decimal,
    invoice_date: date,
    due_date: date,
    payment_clearing_date: date,
    slab_in_days: int,
    reduction_pct: Decimal,
    max_pct: Decimal,
    min_pct: Decimal,
) -> None:
    """Property 5: GST Round-Trip.

    For any valid CommissionInputs, the calculator SHALL produce:
    - gst_on_commission = commission_amount × 0.18  (fixed, non-overridable)
    - final_line_claim_amount = commission_amount × 1.18
      (equivalently: commission_amount + gst_on_commission)

    **Validates: Requirements 3.8, 3.9, 22.7**
    """
    assume(min_pct <= max_pct)
    assume(payment_clearing_date >= invoice_date)

    inputs = CommissionInputs(
        bill_amount_excl_gst=bill,
        amount_deducted=deducted,
        tds_value=tds,
        invoice_date=invoice_date,
        due_date=due_date,
        payment_clearing_date=payment_clearing_date,
        slab_in_days=slab_in_days,
        reduction_percent=reduction_pct,
        max_commission_percent=max_pct,
        min_commission_percent=min_pct,
    )

    result = calculate(inputs)

    # GST = commission × 18% exactly (Req 3.8, 22.7)
    assert result.gst_on_commission == result.commission_amount * Decimal("0.18")

    # Final amount = commission + GST (Req 3.9, 22.7)
    # The × 1.18 shorthand is a mathematical identity for (commission + commission×0.18),
    # but Decimal arithmetic evaluates the two expressions through different precision
    # paths, so we assert the direct additive relationship that the implementation uses.
    assert result.final_line_claim_amount == result.commission_amount + result.gst_on_commission

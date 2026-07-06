# Feature: lacm-masters, Property 35: Commission slab calculation is correct and bounded
"""
Property-based test for the commission slab calculation rule.

Property 35: Commission slab calculation is correct and bounded.

For any valid agreement slab parameters (0 <= Min% <= Max% <= 100,
0 <= Reduction% <= 100, Slab in Days > 0) and any Delay Days value, the
Applicable Commission % computed by ``compute_applicable_commission``:

* equals the Max Commission % exactly when Delay Days <= 0 (Requirement 12.1);
* equals ``max(Max% - ceil(delay / slab) * Reduction%, Min%)`` when
  Delay Days > 0 (Requirement 12.2);
* is always bounded within the inclusive range [Min%, Max%].

**Validates: Requirements 12.1, 12.2**
"""

import math
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from src.domain.services.commission_calculator import compute_applicable_commission


def _percent() -> st.SearchStrategy[Decimal]:
    """Decimal percentages in [0, 100] with two decimal places (matches Numeric(5,2))."""
    return st.integers(min_value=0, max_value=10_000).map(lambda cents: Decimal(cents) / Decimal(100))


@st.composite
def _slab_inputs(draw: st.DrawFn) -> tuple[int, int, Decimal, Decimal, Decimal]:
    """Generate (delay_days, slab_in_days, max_commission, min_commission, reduction).

    Constraints mirror the Agreement validation rules: Min% <= Max%, percentages
    within [0, 100], and Slab in Days strictly positive.
    """
    a = draw(_percent())
    b = draw(_percent())
    min_commission, max_commission = (a, b) if a <= b else (b, a)
    reduction = draw(_percent())
    slab_in_days = draw(st.integers(min_value=1, max_value=365))
    # Cover the full signed range of delay days, including the <= 0 branch.
    delay_days = draw(st.integers(min_value=-500, max_value=5_000))
    return delay_days, slab_in_days, max_commission, min_commission, reduction


@settings(max_examples=20)
@given(_slab_inputs())
def test_commission_slab_calculation_is_correct_and_bounded(
    inputs: tuple[int, int, Decimal, Decimal, Decimal],
) -> None:
    delay_days, slab_in_days, max_commission, min_commission, reduction = inputs

    result = compute_applicable_commission(
        delay_days=delay_days,
        slab_in_days=slab_in_days,
        max_commission=max_commission,
        min_commission=min_commission,
        reduction=reduction,
    )

    if delay_days <= 0:
        # Requirement 12.1: no delay -> full Max Commission %.
        assert result == max_commission
    else:
        # Requirement 12.2: reduce by one Reduction% per slab bucket, floored at Min%.
        bucket = math.ceil(delay_days / slab_in_days)
        expected = max(max_commission - bucket * reduction, min_commission)
        assert result == expected

    # The applicable commission is always bounded within [Min%, Max%].
    assert min_commission <= result <= max_commission

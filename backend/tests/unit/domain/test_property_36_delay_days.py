# Feature: lacm-masters, Property 36: Delay Days equals the day difference (Payment Clearing Date minus Due Date).
"""Property-based test for delay-days computation.

Property 36: Delay Days equals the day difference.

**Validates: Requirements 12.3**

The pure function under test is
``src.domain.services.commission_calculator.compute_delay_days``, which defines
Delay Days as the number of whole calendar days from the Due Date to the Payment
Clearing Date (Payment Clearing Date - Due Date, Requirement 12.3).
"""

from datetime import date, timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

from src.domain.services.commission_calculator import compute_delay_days


@settings(max_examples=20)
@given(
    due_date=st.dates(),
    delta=st.integers(min_value=-3650, max_value=3650),
)
def test_delay_days_equals_day_difference(due_date: date, delta: int) -> None:
    """Delay Days equals the whole calendar days from Due Date to Clearing Date.

    For any Due Date and any signed offset, the Payment Clearing Date is the Due
    Date advanced by that offset. The computed Delay Days MUST therefore:

    * equal that offset exactly (Payment Clearing Date - Due Date), and
    * reconstruct the Payment Clearing Date when added back to the Due Date,

    which together pin the result to the day difference independently of the
    implementation's subtraction mechanics. The offset range is bounded so that
    ``due_date + timedelta`` stays within ``datetime.date``'s supported range.
    """
    # Keep the reconstructed clearing date within date.min..date.max.
    earliest = date.min + timedelta(days=3650)
    latest = date.max - timedelta(days=3650)
    if not (earliest <= due_date <= latest):
        return

    payment_clearing_date = due_date + timedelta(days=delta)

    result = compute_delay_days(due_date, payment_clearing_date)

    # Delay Days is exactly the signed day difference...
    assert result == delta
    assert result == (payment_clearing_date - due_date).days
    # ...and adding it back to the due date reconstructs the clearing date.
    assert due_date + timedelta(days=result) == payment_clearing_date

"""
Property-based tests for status transition gating and terminal state immutability.

**Validates: Requirements 11.1, 11.2, 11.3, 11.4, 22.8, 22.9**
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.domain.entities.commission_claim import (
    ClaimStatus,
    CLAIM_TRANSITIONS,
    TERMINAL_STATUSES,
)

ALL_ACTIONS = ["submit", "approve", "final_approve", "refer_back", "reject"]


# ---------------------------------------------------------------------------
# Property 8: Status Transition Gating
# ---------------------------------------------------------------------------


@settings(max_examples=300)
@given(
    status=st.sampled_from(list(ClaimStatus)),
    action=st.sampled_from(ALL_ACTIONS),
)
def test_property_8_status_transition_gating(status: ClaimStatus, action: str):
    """Property 8: For any (status, action) pair:
    - If in CLAIM_TRANSITIONS, result is a valid ClaimStatus
    - If NOT in CLAIM_TRANSITIONS (or status is terminal), a ValueError would be raised

    We test the map directly: result of CLAIM_TRANSITIONS.get() is either a valid
    ClaimStatus or None (which the service converts to ValueError).

    **Validates: Requirements 11.1, 11.2, 22.8**
    """
    result = CLAIM_TRANSITIONS.get((status, action))

    if result is not None:
        # Valid transition: result must be a member of ClaimStatus
        assert result in ClaimStatus, (
            f"Transition result {result!r} is not a valid ClaimStatus"
        )
        assert result.value in [s.value for s in ClaimStatus], (
            f"Transition result value {result.value!r} not found in ClaimStatus values"
        )
    # If result is None, the service raises ValueError — tested separately


# ---------------------------------------------------------------------------
# Property 9: Terminal State Immutability
# ---------------------------------------------------------------------------


@settings(max_examples=300)
@given(
    status=st.sampled_from(list(TERMINAL_STATUSES)),
    action=st.sampled_from(ALL_ACTIONS),
)
def test_property_9_terminal_state_immutability(status: ClaimStatus, action: str):
    """Property 9: For any action attempted on Closed or Rejected status,
    CLAIM_TRANSITIONS returns None (no valid transition exists).
    The service converts this to a ValueError, leaving status unchanged.

    **Validates: Requirements 11.3, 11.4, 22.9**
    """
    result = CLAIM_TRANSITIONS.get((status, action))
    assert result is None, (
        f"Terminal status {status.value!r} should not allow transition via "
        f"'{action}', but CLAIM_TRANSITIONS returned {result!r}"
    )


# ---------------------------------------------------------------------------
# Structural tests — verify the map and frozenset match the spec exactly
# ---------------------------------------------------------------------------


def test_claim_transitions_contains_exactly_6_edges():
    """The CLAIM_TRANSITIONS map must contain exactly 6 allowed edges per Req 11.1."""
    assert len(CLAIM_TRANSITIONS) == 6, (
        f"Expected exactly 6 transitions, got {len(CLAIM_TRANSITIONS)}: "
        f"{list(CLAIM_TRANSITIONS.keys())}"
    )


def test_terminal_statuses_contains_closed_and_rejected():
    """TERMINAL_STATUSES must contain exactly Closed and Rejected per Reqs 11.3, 11.4."""
    assert ClaimStatus.Closed in TERMINAL_STATUSES
    assert ClaimStatus.Rejected in TERMINAL_STATUSES
    assert len(TERMINAL_STATUSES) == 2, (
        f"Expected exactly 2 terminal statuses, got {len(TERMINAL_STATUSES)}: "
        f"{TERMINAL_STATUSES}"
    )


def test_all_transition_targets_are_valid_claim_statuses():
    """Every value in CLAIM_TRANSITIONS must be a valid ClaimStatus member."""
    valid_values = {s.value for s in ClaimStatus}
    for (from_status, action), to_status in CLAIM_TRANSITIONS.items():
        assert to_status in ClaimStatus, (
            f"Transition target {to_status!r} for ({from_status}, {action}) "
            f"is not a valid ClaimStatus"
        )
        assert to_status.value in valid_values


def test_no_transitions_from_terminal_statuses():
    """No transition edge may originate from a terminal status."""
    for (from_status, action) in CLAIM_TRANSITIONS:
        assert from_status not in TERMINAL_STATUSES, (
            f"Terminal status {from_status.value!r} has a defined transition "
            f"via '{action}' — this violates Reqs 11.3 and 11.4"
        )

"""
Property-based tests for CommissionClaimService.create_claim — Property 11.

Tests verify that for any valid vendor_id, a newly created claim always has:
  - claim_number = None (not assigned until first submission)
  - status = ClaimStatus.Draft
  - claim_date set to a non-None date value
  - an audit entry with action='Create' written immediately after persist

No real DB is needed — the repository collaborators are fully mocked.

**Validates: Requirements 1.2, 6.3**
"""

import asyncio
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from src.application.services.commission_claim_service import CommissionClaimService
from src.domain.entities.commission_claim import ClaimHeader, ClaimStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_actor(username: str = "agent1") -> MagicMock:
    """Build a minimal actor mock with username and id."""
    actor = MagicMock()
    actor.username = username
    actor.id = uuid4()
    return actor


def _build_service() -> CommissionClaimService:
    """
    Build a CommissionClaimService instance with fully mocked repositories.

    header_repo.create is a passthrough — returns the input ClaimHeader
    unchanged so tests can inspect the entity before any DB transformation.
    audit_repo.create is also a passthrough.
    """
    svc = CommissionClaimService.__new__(CommissionClaimService)

    # Mock header_repo: create returns the input header unchanged
    header_repo = AsyncMock()

    async def create_passthrough(header: ClaimHeader) -> ClaimHeader:
        return header

    header_repo.create = AsyncMock(side_effect=create_passthrough)
    svc._header_repo = header_repo

    # Mock audit_repo: create is a passthrough
    audit_repo = AsyncMock()
    audit_repo.create = AsyncMock(side_effect=lambda e: e)
    svc._audit_repo = audit_repo

    # Remaining collaborators — not used by create_claim
    svc._line_repo = AsyncMock()
    svc._claim_number_service = AsyncMock()
    svc._workflow_engine = AsyncMock()
    svc._audit_service = AsyncMock()

    return svc


# ---------------------------------------------------------------------------
# Property 11: Claim Number Null at Draft Creation
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(vendor_id=st.uuids())
def test_property_11_claim_number_null_at_draft_creation(vendor_id: UUID) -> None:
    """Property 11: Claim Number Null at Draft Creation.

    For any valid vendor_id, create_claim SHALL produce a ClaimHeader with:
      - claim_number = None (not assigned until first submission)
      - status = ClaimStatus.Draft
      - claim_date set to a non-None date instance

    The claim number is only assigned at first submission (Requirements 1.2, 6.3).

    **Validates: Requirements 1.2, 6.3**
    """
    svc = _build_service()
    actor = _make_actor()

    result: ClaimHeader = asyncio.run(svc.create_claim(vendor_id, actor))

    assert result.claim_number is None, (
        f"Expected claim_number to be None at Draft creation, got '{result.claim_number}'"
    )
    assert result.status == ClaimStatus.Draft, (
        f"Expected status to be Draft at creation, got '{result.status}'"
    )
    assert result.claim_date is not None, "claim_date must be set at creation"
    assert isinstance(result.claim_date, date), (
        f"claim_date must be a date, got {type(result.claim_date)}"
    )


# ---------------------------------------------------------------------------
# Property 11 corollary: Audit entry written at Draft creation
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(
    vendor_id=st.uuids(),
    username=st.text(
        min_size=1,
        max_size=50,
        alphabet=st.characters(
            whitelist_categories=("Lu", "Ll", "Nd"),
            whitelist_characters="_@.",
        ),
    ),
)
def test_property_11_audit_entry_written_at_draft_creation(
    vendor_id: UUID, username: str
) -> None:
    """Property 11 corollary: For any valid create_claim, an audit entry with
    action='Create' is always written immediately after persist (Requirement 1.5).

    Regardless of vendor_id or actor username, the audit_repo.create MUST be
    called exactly once with:
      - action = "Create"
      - to_status = ClaimStatus.Draft.value
      - from_status = None  (no prior status at creation)

    **Validates: Requirements 1.2, 6.3**
    """
    svc = _build_service()
    actor = MagicMock()
    actor.username = username
    actor.id = uuid4()

    asyncio.run(svc.create_claim(vendor_id, actor))

    # audit_repo.create must have been called exactly once
    svc._audit_repo.create.assert_awaited_once()

    audit_call_args = svc._audit_repo.create.call_args[0]
    assert len(audit_call_args) >= 1, "audit_repo.create must be called with an audit entry"
    audit_entry = audit_call_args[0]

    assert audit_entry.action == "Create", (
        f"Expected audit action 'Create', got '{audit_entry.action}'"
    )
    assert audit_entry.to_status == ClaimStatus.Draft.value, (
        f"Expected to_status '{ClaimStatus.Draft.value}', got '{audit_entry.to_status}'"
    )
    assert audit_entry.from_status is None, (
        f"Expected from_status to be None at creation, got '{audit_entry.from_status}'"
    )

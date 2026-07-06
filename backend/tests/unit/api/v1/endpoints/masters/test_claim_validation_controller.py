"""
Unit tests for the Claim Validation controller.

The controller is intentionally thin, so these tests exercise its real
responsibilities in isolation (without standing up the FastAPI app, which is
wired in a later task):

* request/response schema adaptation to/from the Pydantic-agnostic service,
* preservation of per-line order and one-error-per-failed-check shape
  (Req 18.5, 18.6), and
* master-exception-to-HTTP-status mapping (422 / 409 / 404).

The async route handler is invoked directly with a fake service.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException, status

from src.api.v1.endpoints.masters import claim_validation_controller as ctrl
from src.api.v1.schemas.masters.claim_validation_request import (
    ValidateClaimRequest,
)
from src.application.exceptions.application_exceptions import (
    MasterConflictError,
    MasterNotFoundError,
    MasterValidationError,
)
from src.application.services.masters.claim_validation_service import (
    CODE_INVOICE_NOT_CLEARED,
    CODE_NO_ACTIVE_MAPPING,
    LineValidationError,
    LineValidationResult,
)
from src.domain.entities.user import User

pytestmark = pytest.mark.asyncio


@pytest.fixture
def actor() -> User:
    return User(
        id=uuid4(),
        username="tester",
        password_hash="x",
        is_active=True,
        is_blocked=False,
    )


class FakeClaimValidationService:
    """Records calls and returns canned values."""

    def __init__(self) -> None:
        self.validated_ids = None
        self.results: list[LineValidationResult] = []
        self.raise_on_validate: Exception | None = None

    async def validate_lines(self, invoice_line_ids):  # noqa: ANN001
        self.validated_ids = invoice_line_ids
        if self.raise_on_validate is not None:
            raise self.raise_on_validate
        return self.results


async def test_validate_maps_allowed_and_blocked_lines(actor: User) -> None:
    service = FakeClaimValidationService()
    allowed_id, blocked_id = uuid4(), uuid4()
    service.results = [
        LineValidationResult(invoice_line_id=allowed_id, allowed=True, errors=[]),
        LineValidationResult(
            invoice_line_id=blocked_id,
            allowed=False,
            errors=[
                LineValidationError(
                    invoice_line_id=blocked_id,
                    code=CODE_NO_ACTIVE_MAPPING,
                    message="No active mapping covers the invoice date",
                ),
                LineValidationError(
                    invoice_line_id=blocked_id,
                    code=CODE_INVOICE_NOT_CLEARED,
                    message="The invoice is not eligible for claim",
                ),
            ],
        ),
    ]
    request = ValidateClaimRequest(invoice_line_ids=[allowed_id, blocked_id])

    response = await ctrl.validate_claim(
        request=request, current_user=actor, service=service
    )

    # Ids are forwarded to the service unchanged and order is preserved.
    assert service.validated_ids == [allowed_id, blocked_id]
    assert [r.invoice_line_id for r in response] == [allowed_id, blocked_id]
    # Valid and blocked lines coexist (Req 18.5).
    assert response[0].allowed is True
    assert response[0].errors == []
    # One distinct error per failed check is surfaced (Req 18.6).
    assert response[1].allowed is False
    assert [e.code for e in response[1].errors] == [
        CODE_NO_ACTIVE_MAPPING,
        CODE_INVOICE_NOT_CLEARED,
    ]


async def test_validate_empty_results_returns_empty_list(actor: User) -> None:
    service = FakeClaimValidationService()
    line_id = uuid4()
    request = ValidateClaimRequest(invoice_line_ids=[line_id])

    response = await ctrl.validate_claim(
        request=request, current_user=actor, service=service
    )

    assert service.validated_ids == [line_id]
    assert response == []


async def test_validate_unknown_line_maps_to_404(actor: User) -> None:
    service = FakeClaimValidationService()
    service.raise_on_validate = MasterNotFoundError("Invoice Line", uuid4())
    request = ValidateClaimRequest(invoice_line_ids=[uuid4()])

    with pytest.raises(HTTPException) as exc:
        await ctrl.validate_claim(
            request=request, current_user=actor, service=service
        )
    assert exc.value.status_code == status.HTTP_404_NOT_FOUND


def test_request_rejects_empty_id_list() -> None:
    with pytest.raises(ValueError):
        ValidateClaimRequest(invoice_line_ids=[])


# ─── exception-to-HTTP mapping helper ───


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (
            MasterValidationError("invoice_line_ids", "required"),
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ),
        (MasterConflictError("conflict"), status.HTTP_409_CONFLICT),
        (
            MasterNotFoundError("Invoice Line", uuid4()),
            status.HTTP_404_NOT_FOUND,
        ),
    ],
)
def test_to_http_exception_mapping(exc, expected) -> None:  # noqa: ANN001
    http_exc = ctrl._to_http_exception(exc)
    assert http_exc.status_code == expected

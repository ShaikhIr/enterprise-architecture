"""
Unit tests for ExceptionHandlerMiddleware's response bodies.

Every error answers with `detail`, the shape the API standard requires and the one FastAPI's own
errors use. `message`, `success` and `correlation_id` stay alongside it for existing clients.
"""

import json
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api.middleware.exception_handler import ExceptionHandlerMiddleware
from src.application.exceptions.auth_exceptions import (
    AuthServiceUnavailableError,
    InvalidTokenError,
    UserBlockedError,
)
from src.domain.exceptions.domain_exceptions import (
    BusinessRuleViolationError,
    DomainError,
    DuplicateEntityError,
    EntityNotFoundError,
)


def build_app(error: Exception) -> FastAPI:
    app = FastAPI()
    app.add_middleware(ExceptionHandlerMiddleware)

    @app.get("/boom")
    async def boom() -> None:
        raise error

    return app


async def get(error: Exception) -> tuple[int, dict[str, Any]]:
    transport = ASGITransport(app=build_app(error))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/boom")
    return response.status_code, json.loads(response.text)


class TestBodyShape:
    @pytest.mark.parametrize(
        ("error", "status"),
        [
            (EntityNotFoundError("Country", 7), 404),
            (DuplicateEntityError("Country", "code", "IN"), 409),
            (BusinessRuleViolationError("Country has states"), 409),
            (DomainError("Something else"), 400),
        ],
    )
    async def test_domain_errors_carry_detail_and_the_older_fields(
        self, error: DomainError, status: int
    ) -> None:
        code, body = await get(error)

        assert code == status
        assert body["detail"] == error.message
        assert body["message"] == error.message
        assert body["success"] is False
        assert "correlation_id" in body

    @pytest.mark.parametrize(
        ("error", "status"),
        [
            (UserBlockedError(), 403),
            (InvalidTokenError(), 401),
            (AuthServiceUnavailableError(), 503),
        ],
    )
    async def test_authentication_errors_carry_detail_and_keep_their_status(
        self, error: Any, status: int
    ) -> None:
        code, body = await get(error)

        assert code == status
        assert body["detail"] == error.message
        assert body["message"] == error.message

    async def test_unexpected_errors_are_a_generic_500_that_leaks_nothing(self) -> None:
        code, body = await get(RuntimeError("password=hunter2 in the connection string"))

        assert code == 500
        assert body["detail"] == "Internal Server Error"
        assert body["message"] == "Internal Server Error"
        assert "hunter2" not in json.dumps(body)

    async def test_detail_and_message_always_agree(self) -> None:
        for error in (EntityNotFoundError("X", 1), InvalidTokenError(), RuntimeError("y")):
            _, body = await get(error)

            assert body["detail"] == body["message"]

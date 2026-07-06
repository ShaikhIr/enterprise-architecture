"""Shared schemas for LACM master endpoints."""
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated list envelope for master listings."""

    items: list[T]
    total: int
    skip: int
    limit: int

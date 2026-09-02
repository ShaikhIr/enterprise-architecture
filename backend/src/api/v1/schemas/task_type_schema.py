"""
Pydantic schemas for the Task Type master API.
"""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class TaskTypeCreate(BaseModel):
    """Create a new task type."""

    code: str = Field(..., min_length=2, max_length=50, examples=["RETURN_FILING"])
    name: str = Field(..., min_length=1, max_length=255, examples=["Return Filing"])
    description: str = Field(
        default="", examples=["Periodic statutory return to be filed with authority"]
    )
    is_active: bool = Field(default=True)

    @field_validator("code")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.strip().upper().replace(" ", "_")

    @field_validator("name")
    @classmethod
    def _trim(cls, value: str) -> str:
        return value.strip()


class TaskTypeUpdate(BaseModel):
    """Update an existing task type. Only supplied fields are changed."""

    code: str | None = Field(default=None, min_length=2, max_length=50)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None)
    is_active: bool | None = Field(default=None)

    @field_validator("code")
    @classmethod
    def _upper(cls, value: str | None) -> str | None:
        return value.strip().upper().replace(" ", "_") if value else value

    @field_validator("name")
    @classmethod
    def _trim(cls, value: str | None) -> str | None:
        return value.strip() if value else value


class TaskTypeResponse(BaseModel):
    """Task type read response."""

    id: int
    code: str
    name: str
    description: str
    is_active: bool
    created_by: str
    created_date: datetime
    modified_by: str
    modified_date: datetime

    model_config = {"from_attributes": True}


class TaskTypeListResponse(BaseModel):
    """Paginated list of task types."""

    task_types: list[TaskTypeResponse]
    total: int
    skip: int
    limit: int

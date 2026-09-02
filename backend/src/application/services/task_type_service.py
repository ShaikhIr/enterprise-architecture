"""
Task Type Application Service.
Orchestrates task type master CRUD.
"""


from src.api.v1.schemas.task_type_schema import (
    TaskTypeCreate,
    TaskTypeListResponse,
    TaskTypeResponse,
    TaskTypeUpdate,
)
from src.domain.entities.task_type import TaskType
from src.domain.entities.user import User
from src.domain.exceptions.domain_exceptions import (
    DuplicateEntityError,
    EntityNotFoundError,
)
from src.domain.repositories.task_type_repository import ITaskTypeRepository

ENTITY = "TaskType"


class TaskTypeService:
    """
    Application service for the TaskType master.

    Responsibilities:
    - Enforce unique code and name
    - Map domain entities to API responses
    """

    def __init__(self, task_type_repo: ITaskTypeRepository) -> None:
        self._repo = task_type_repo

    # ─── List ───

    async def list_task_types(
        self,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        is_active: bool | None = None,
    ) -> TaskTypeListResponse:
        """Get a paginated page of task types plus the total match count."""
        task_types = await self._repo.list_all(
            skip=skip, limit=limit, search=search, is_active=is_active
        )
        total = await self._repo.count(search=search, is_active=is_active)
        return TaskTypeListResponse(
            task_types=[self._to_response(t) for t in task_types],
            total=total,
            skip=skip,
            limit=limit,
        )

    # ─── Get ───

    async def get_task_type(self, task_type_id: int) -> TaskTypeResponse:
        """Get a single task type. Raises EntityNotFoundError if missing."""
        return self._to_response(await self._require(task_type_id))

    # ─── Create ───

    async def create_task_type(
        self, request: TaskTypeCreate, actor: User
    ) -> TaskTypeResponse:
        """Create a task type after checking code and name uniqueness."""
        if await self._repo.exists_by_code(request.code):
            raise DuplicateEntityError(ENTITY, "code", request.code)
        if await self._repo.exists_by_name(request.name):
            raise DuplicateEntityError(ENTITY, "name", request.name)

        task_type = TaskType(
            code=request.code,
            name=request.name,
            description=request.description,
            is_active=request.is_active,
            created_by=actor.username,
            modified_by=actor.username,
        )
        created = await self._repo.create(task_type)
        return self._to_response(created)

    # ─── Update ───

    async def update_task_type(
        self, task_type_id: int, request: TaskTypeUpdate, actor: User
    ) -> TaskTypeResponse:
        """Apply a partial update to a task type."""
        task_type = await self._require(task_type_id)

        if request.code is not None and request.code != task_type.code:
            if await self._repo.exists_by_code(request.code, exclude_id=task_type_id):
                raise DuplicateEntityError(ENTITY, "code", request.code)
            task_type.code = request.code

        if request.name is not None and request.name != task_type.name:
            if await self._repo.exists_by_name(request.name, exclude_id=task_type_id):
                raise DuplicateEntityError(ENTITY, "name", request.name)
            task_type.name = request.name

        if request.description is not None:
            task_type.description = request.description
        if request.is_active is not None:
            task_type.is_active = request.is_active

        task_type.mark_modified(actor.username)
        return self._to_response(await self._repo.update(task_type))

    # ─── Delete ───

    async def delete_task_type(self, task_type_id: int) -> None:
        """Delete a task type."""
        await self._require(task_type_id)
        await self._repo.delete(task_type_id)

    # ─── Internals ───

    async def _require(self, task_type_id: int) -> TaskType:
        task_type = await self._repo.get_by_id(task_type_id)
        if task_type is None:
            raise EntityNotFoundError(ENTITY, task_type_id)
        return task_type

    @staticmethod
    def _to_response(task_type: TaskType) -> TaskTypeResponse:
        """Map domain entity to API response."""
        return TaskTypeResponse.model_validate(task_type)

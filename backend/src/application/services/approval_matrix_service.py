"""
Approval matrix application service.

Owns the routing configuration: which matrix applies to which entity type, the
conditions that select it, and the approval levels it routes to. Matrices are
treated as whole documents — an update replaces the rule set and the level set
rather than patching them row by row, because that is how the screen edits them.

`resolve` is the dry run: feed it a sample record and it reports which matrix
would win and who would be asked to approve, without writing anything.
"""

from typing import Any
from uuid import UUID, uuid4

from src.api.v1.schemas.approval_matrix_schema import (
    ApprovalAssignmentInput,
    ApprovalAssignmentResponse,
    ApprovalMatrixCreate,
    ApprovalMatrixListResponse,
    ApprovalMatrixResponse,
    ApprovalMatrixUpdate,
    ApprovalResolveResponse,
    ApprovalRuleInput,
)
from src.application.services.workflow.approval_matrix_resolver import (
    ApprovalMatrixResolver,
)
from src.domain.entities.approval_matrix import (
    ApprovalAssignment,
    ApprovalMatrix,
    ApprovalRule,
)
from src.domain.entities.user import User
from src.domain.exceptions.domain_exceptions import (
    DuplicateEntityError,
    EntityNotFoundError,
)
from src.domain.repositories.approval_matrix_repository import IApprovalMatrixRepository

ENTITY = "ApprovalMatrix"


class ApprovalMatrixService:
    """Application service for approval matrix configuration and resolution."""

    def __init__(self, approval_matrix_repo: IApprovalMatrixRepository) -> None:
        self._repo = approval_matrix_repo
        self._resolver = ApprovalMatrixResolver(approval_matrix_repo)

    # ─── List ───

    async def list_matrices(
        self,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        is_active: bool | None = None,
        entity_type: str | None = None,
    ) -> ApprovalMatrixListResponse:
        """Get a page of matrices plus the total match count."""
        matrices = await self._repo.list_all(
            skip=skip,
            limit=limit,
            search=search,
            is_active=is_active,
            entity_type=entity_type,
        )
        total = await self._repo.count(
            search=search, is_active=is_active, entity_type=entity_type
        )
        return ApprovalMatrixListResponse(
            matrices=[ApprovalMatrixResponse.model_validate(m) for m in matrices],
            total=total,
            skip=skip,
            limit=limit,
        )

    # ─── Get ───

    async def get_matrix(self, matrix_id: UUID) -> ApprovalMatrixResponse:
        """Get one matrix with its rules and levels."""
        return ApprovalMatrixResponse.model_validate(await self._require(matrix_id))

    # ─── Create ───

    async def create_matrix(
        self, request: ApprovalMatrixCreate, actor: User
    ) -> ApprovalMatrixResponse:
        """Create a matrix together with its rules and approval levels."""
        if await self._repo.exists_by_code(request.code):
            raise DuplicateEntityError(ENTITY, "code", request.code)
        if await self._repo.exists_by_name(request.name):
            raise DuplicateEntityError(ENTITY, "name", request.name)

        matrix_id = uuid4()
        matrix = ApprovalMatrix(
            id=matrix_id,
            code=request.code,
            name=request.name,
            entity_type=request.entity_type,
            priority=request.priority,
            is_active=request.is_active,
            rules=self._to_rules(request.rules, matrix_id, actor.username),
            assignments=self._to_assignments(
                request.assignments, matrix_id, actor.username
            ),
            created_by=actor.username,
            modified_by=actor.username,
        )
        return ApprovalMatrixResponse.model_validate(await self._repo.create(matrix))

    # ─── Update ───

    async def update_matrix(
        self, matrix_id: UUID, request: ApprovalMatrixUpdate, actor: User
    ) -> ApprovalMatrixResponse:
        """
        Apply a partial update to a matrix.

        `rules` and `assignments` are replace-if-supplied: passing a list swaps the
        stored collection for it, omitting the key leaves it alone. A patch-style
        merge would make it impossible to delete the last rule.
        """
        matrix = await self._require(matrix_id)

        if request.name is not None and request.name != matrix.name:
            if await self._repo.exists_by_name(request.name, exclude_id=matrix_id):
                raise DuplicateEntityError(ENTITY, "name", request.name)
            matrix.name = request.name

        if request.entity_type is not None:
            matrix.entity_type = request.entity_type
        if request.priority is not None:
            matrix.priority = request.priority
        if request.is_active is not None:
            matrix.is_active = request.is_active

        if request.rules is not None:
            matrix.rules = self._to_rules(request.rules, matrix_id, actor.username)
        if request.assignments is not None:
            matrix.assignments = self._to_assignments(
                request.assignments, matrix_id, actor.username
            )

        matrix.mark_modified(actor.username)
        return ApprovalMatrixResponse.model_validate(await self._repo.update(matrix))

    # ─── Delete ───

    async def delete_matrix(self, matrix_id: UUID) -> None:
        """Delete a matrix; its rules and levels go with it."""
        await self._require(matrix_id)
        await self._repo.delete(matrix_id)

    # ─── Resolve ───

    async def resolve(
        self, entity_type: str, entity_data: dict[str, Any]
    ) -> ApprovalResolveResponse:
        """
        Report which matrix would route a sample record, and to whom.

        A miss is a normal answer, not an error: `matched` is False and the rest
        of the response is empty.
        """
        resolved = await self._resolver.resolve(entity_type, entity_data)
        if resolved is None:
            return ApprovalResolveResponse(matched=False)

        return ApprovalResolveResponse(
            matched=True,
            matrix=ApprovalMatrixResponse.model_validate(resolved.matrix),
            levels=resolved.levels,
            assignments=[
                ApprovalAssignmentResponse.model_validate(a)
                for a in resolved.assignments
            ],
        )

    # ─── Internals ───

    async def _require(self, matrix_id: UUID) -> ApprovalMatrix:
        matrix = await self._repo.get_by_id(matrix_id)
        if matrix is None:
            raise EntityNotFoundError(ENTITY, matrix_id)
        return matrix

    @staticmethod
    def _to_rules(
        inputs: list[ApprovalRuleInput], matrix_id: UUID, actor_username: str
    ) -> list[ApprovalRule]:
        return [
            ApprovalRule(
                id=uuid4(),
                matrix_id=matrix_id,
                field=item.field,
                operator=item.operator,
                value=item.value,
                data_type=item.data_type,
                logical_group=item.logical_group,
                created_by=actor_username,
                modified_by=actor_username,
            )
            for item in inputs
        ]

    @staticmethod
    def _to_assignments(
        inputs: list[ApprovalAssignmentInput], matrix_id: UUID, actor_username: str
    ) -> list[ApprovalAssignment]:
        return [
            ApprovalAssignment(
                id=uuid4(),
                matrix_id=matrix_id,
                assignment_type=item.assignment_type,
                user_id=item.user_id,
                role_id=item.role_id,
                level=item.level,
                created_by=actor_username,
                modified_by=actor_username,
            )
            for item in inputs
        ]

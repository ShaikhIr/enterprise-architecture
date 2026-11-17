"""
Approval task coordinator.

This is the join between the two halves of the engine. The state machine says
*what* moves are legal; the approval matrix says *who* should be asked. This
coordinator is the only thing that reads both, turning a transition into concrete
tasks and deciding when the chain moves on.

The rules, driven entirely by the transition's declared `action_type`:

    SUBMIT      open level 1 of the matching matrix
    APPROVE     settle this level; open the next one, or finish the chain
    REJECT      settle this level; abandon the chain
    CANCEL      abandon the chain
    REFER_BACK  settle this level; abandon the chain so a later SUBMIT restarts
                it from level 1
    others      leave the chain alone

Two semantics worth being explicit about, because neither is the only defensible
choice:

1. A role-based level fans out to every eligible holder of the role, and the
   first one to act settles it. The peers' tasks are cancelled rather than
   deleted, so the record still shows who was asked.
2. Which matrix routes an instance is decided once, when the chain opens, and
   remembered on the tasks. Editing a matrix mid-flight does not re-route work
   already in someone's queue.
"""

import logging
from typing import Any

from src.application.services.workflow.approval_matrix_resolver import (
    ApprovalMatrixResolver,
)
from src.domain.entities.approval_matrix import (
    ApprovalAssignment,
    ApprovalMatrix,
    ApprovalTask,
)
from src.domain.entities.workflow import WorkflowInstance
from src.domain.enums.workflow_enums import (
    ApprovalTaskStatus,
    AssignmentType,
    WorkflowActionType,
)
from src.domain.repositories.approval_matrix_repository import IApprovalMatrixRepository
from src.domain.repositories.role_assignment_repository import IRoleAssignmentRepository

logger = logging.getLogger(__name__)

#: Actions that settle the acting user's task before the chain is re-evaluated.
_SETTLING_ACTIONS = frozenset(
    {
        WorkflowActionType.APPROVE,
        WorkflowActionType.REJECT,
        WorkflowActionType.REFER_BACK,
    }
)

#: Actions that abandon the chain outright.
_ABANDONING_ACTIONS = frozenset(
    {
        WorkflowActionType.REJECT,
        WorkflowActionType.CANCEL,
        WorkflowActionType.REFER_BACK,
    }
)


class ApprovalTaskCoordinator:
    """Creates, settles and advances the approval tasks behind a workflow."""

    def __init__(
        self,
        matrix_repo: IApprovalMatrixRepository,
        role_assignment_repo: IRoleAssignmentRepository,
        resolver: ApprovalMatrixResolver | None = None,
    ) -> None:
        self._matrices = matrix_repo
        self._roles = role_assignment_repo
        self._resolver = resolver or ApprovalMatrixResolver(matrix_repo)

    async def apply(
        self,
        *,
        instance: WorkflowInstance,
        action_type: WorkflowActionType,
        actor_id: int,
        actor_username: str,
        comments: str,
        reached_terminal_state: bool,
    ) -> list[ApprovalTask]:
        """
        Bring the approval chain in line with an action that has just executed.

        Mutates `instance.approval_level` in place; the caller persists the
        instance. Returns any newly created tasks.

        A terminal state always wins over the action's own semantics: whatever the
        designer declared, an instance that has finished must not leave approvals
        sitting in queues.
        """
        if action_type in _SETTLING_ACTIONS:
            await self._settle_level(
                instance_id=instance.id,
                actor_id=actor_id,
                actor_username=actor_username,
                action_type=action_type,
                comments=comments,
            )

        if reached_terminal_state or action_type in _ABANDONING_ACTIONS:
            cancelled = await self._matrices.cancel_open_tasks_for_instance(instance.id)
            instance.approval_level = 0
            if cancelled:
                logger.info(
                    "Approval chain abandoned: instance=%s action=%s cancelled=%d",
                    instance.id,
                    action_type,
                    cancelled,
                )
            return []

        if action_type == WorkflowActionType.SUBMIT:
            return await self._open_first_level(instance, actor_username)

        if action_type == WorkflowActionType.APPROVE:
            return await self._open_next_level(instance, actor_username)

        return []

    # ─── Chain steps ───

    async def _open_first_level(
        self, instance: WorkflowInstance, actor_username: str
    ) -> list[ApprovalTask]:
        """Resolve the routing matrix and open its lowest level."""
        entity_data: dict[str, Any] = dict(instance.extra_data)
        resolved = await self._resolver.resolve(instance.entity_type, entity_data)
        if resolved is None:
            logger.info(
                "No approval matrix routes %s '%s'; instance %s proceeds unapproved",
                instance.entity_type,
                instance.entity_id,
                instance.id,
            )
            instance.approval_level = 0
            return []

        levels = resolved.levels
        if not levels:
            logger.warning(
                "Approval matrix '%s' matched but defines no levels; instance %s "
                "proceeds unapproved",
                resolved.matrix.code,
                instance.id,
            )
            instance.approval_level = 0
            return []

        return await self._open_level(instance, resolved.matrix, levels[0], actor_username)

    async def _open_next_level(
        self, instance: WorkflowInstance, actor_username: str
    ) -> list[ApprovalTask]:
        """
        Open the level above the current one, if the current one is fully settled.

        Does nothing while any task at the current level is still open, which is
        what makes a fan-out level wait for a decision instead of racing ahead.
        """
        tasks = await self._matrices.list_tasks_for_instance(instance.id)
        if any(task.is_open for task in tasks):
            return []

        matrix = await self._remembered_matrix(tasks)
        if matrix is None:
            instance.approval_level = 0
            return []

        higher = [level for level in matrix.levels if level > instance.approval_level]
        if not higher:
            logger.info(
                "Approval chain complete: instance=%s matrix=%s",
                instance.id,
                matrix.code,
            )
            instance.approval_level = 0
            return []

        return await self._open_level(instance, matrix, higher[0], actor_username)

    async def _open_level(
        self,
        instance: WorkflowInstance,
        matrix: ApprovalMatrix,
        level: int,
        actor_username: str,
    ) -> list[ApprovalTask]:
        """Create one task per eligible approver at a level."""
        assignee_ids = await self._eligible_assignees(matrix.assignments_for_level(level))
        if not assignee_ids:
            logger.warning(
                "Approval level %d of matrix '%s' resolves to nobody; instance %s "
                "would stall, so the chain is left closed",
                level,
                matrix.code,
                instance.id,
            )
            instance.approval_level = 0
            return []

        created = [
            await self._matrices.create_task(
                ApprovalTask(
                    instance_id=instance.id,
                    assignee_id=assignee_id,
                    matrix_id=matrix.id,
                    level=level,
                    status=ApprovalTaskStatus.PENDING,
                    due_date=instance.due_date,
                    created_by=actor_username,
                    modified_by=actor_username,
                )
            )
            for assignee_id in assignee_ids
        ]

        instance.approval_level = level
        logger.info(
            "Approval level %d opened: instance=%s matrix=%s approvers=%d",
            level,
            instance.id,
            matrix.code,
            len(created),
        )
        return created

    async def _settle_level(
        self,
        *,
        instance_id: int,
        actor_id: int,
        actor_username: str,
        action_type: WorkflowActionType,
        comments: str,
    ) -> None:
        """
        Close the acting user's task, and cancel the peers asked alongside them.

        Nothing happens when the actor holds no open task — a maker submitting
        their own record is the normal case, not an error.
        """
        tasks = await self._matrices.list_tasks_for_instance(instance_id)
        mine = [t for t in tasks if t.is_open and t.assignee_id == actor_id]
        if not mine:
            return

        level = min(task.level for task in mine)

        for task in mine:
            task.status = ApprovalTaskStatus.COMPLETED
            task.action_taken = action_type.value
            task.comments = comments or None
            task.mark_modified(actor_username)
            await self._matrices.update_task(task)

        peers = [
            t
            for t in tasks
            if t.is_open and t.level == level and t.assignee_id != actor_id
        ]
        for peer in peers:
            peer.status = ApprovalTaskStatus.CANCELLED
            peer.action_taken = None
            peer.mark_modified(actor_username)
            await self._matrices.update_task(peer)

        logger.info(
            "Approval level %d settled by %s: instance=%s action=%s peers_cancelled=%d",
            level,
            actor_username,
            instance_id,
            action_type,
            len(peers),
        )

    # ─── Internals ───

    async def _remembered_matrix(
        self, tasks: list[ApprovalTask]
    ) -> ApprovalMatrix | None:
        """
        The matrix this instance's chain was opened against.

        Read back from the tasks rather than re-resolved, so a matrix edited while
        work is in flight cannot silently re-route it.
        """
        matrix_ids = [task.matrix_id for task in tasks if task.matrix_id is not None]
        if not matrix_ids:
            return None
        return await self._matrices.get_by_id(matrix_ids[-1])

    async def _eligible_assignees(
        self, assignments: list[ApprovalAssignment]
    ) -> list[int]:
        """
        Expand a level's assignments into distinct user ids.

        Deduplicated because one user can reach the same level twice — holding two
        assigned roles, or being named directly as well as via a role — and
        `uq_approval_tasks_instance_assignee_level` would reject the second task.
        """
        assignee_ids: list[int] = []
        seen: set[int] = set()

        for assignment in assignments:
            candidates: list[int] = []
            if assignment.assignment_type == AssignmentType.USER:
                if assignment.user_id is not None:
                    candidates = [assignment.user_id]
            elif assignment.assignment_type == AssignmentType.ROLE:
                if assignment.role_id is not None:
                    candidates = await self._roles.list_active_user_ids_for_role(
                        assignment.role_id
                    )
                    if not candidates:
                        logger.warning(
                            "Role %s has no eligible active users for approval level %d",
                            assignment.role_id,
                            assignment.level,
                        )
            else:
                # MATRIX and EXPRESSION assignment types are accepted by the schema
                # but have no resolution strategy yet; skipping is safer than
                # guessing at an approver.
                logger.warning(
                    "Assignment type %s is not resolvable yet; skipping level %d",
                    assignment.assignment_type,
                    assignment.level,
                )

            for candidate in candidates:
                if candidate not in seen:
                    seen.add(candidate)
                    assignee_ids.append(candidate)

        return assignee_ids

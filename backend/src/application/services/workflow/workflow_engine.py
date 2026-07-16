"""
Workflow Engine — Orchestration Service.
Coordinates state machine, approval matrix, events, and audit trail.
This is the primary entry point for business modules to interact with the workflow system.
"""
import logging
from uuid import UUID, uuid4
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.services.workflow.state_machine_service import StateMachineService
from src.application.services.workflow.approval_matrix_service import ApprovalMatrixService

logger = logging.getLogger(__name__)


class WorkflowEngine:
    """
    Central orchestrator for workflow execution.

    Business modules call this service to:
    - Start a workflow
    - Execute actions (approve, reject, refer back, etc.)
    - Query pending tasks
    - Cancel workflows

    No workflow logic should exist in business modules.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._state_machine = StateMachineService(session)
        self._approval_matrix = ApprovalMatrixService(session)

    async def start_workflow(
        self,
        definition_code: str,
        entity_type: str,
        entity_id: UUID,
        initiated_by: UUID,
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        """
        Start a new workflow instance.

        1. Looks up workflow definition by code
        2. Creates instance in initial state
        3. Returns instance info
        """
        from src.infrastructure.database.models.workflow.workflow_models import (
            WorkflowDefinitionModel,
            WorkflowStatusModel,
            WorkflowInstanceModel,
        )

        # Find active definition
        stmt = select(WorkflowDefinitionModel).where(
            WorkflowDefinitionModel.code == definition_code,
            WorkflowDefinitionModel.is_active == True,
        )
        result = await self._session.execute(stmt)
        definition = result.scalar_one_or_none()

        if not definition:
            raise ValueError(f"Workflow definition '{definition_code}' not found or inactive")

        # Find initial status
        status_stmt = select(WorkflowStatusModel).where(
            WorkflowStatusModel.workflow_definition_id == str(definition.id),
            WorkflowStatusModel.is_initial == True,
        )
        status_result = await self._session.execute(status_stmt)
        initial_status = status_result.scalar_one_or_none()

        if not initial_status:
            raise ValueError(f"No initial status defined for workflow '{definition_code}'")

        # Create instance
        instance = WorkflowInstanceModel(
            id=uuid4(),
            workflow_definition_id=str(definition.id),
            entity_type=entity_type,
            entity_id=str(entity_id),
            current_status_id=str(initial_status.id),
            initiated_by=str(initiated_by),
            priority=0,
            started_at=datetime.now(timezone.utc),
            extra_data=metadata or {},
            created_by="system",
            modified_by="system",
        )
        self._session.add(instance)

        # ── Create approval tasks for Level 1 approvers ──────────────────────
        # Resolve which approval matrix matches this entity + metadata
        entity_data = metadata or {}
        approvers = await self._approval_matrix.resolve_approvers(
            entity_type, entity_data, workflow_definition_id=str(definition.id)
        )

        logger.info(
            "Approval matrix resolution: entity_type=%s entity_data=%s workflow_def=%s approvers=%s",
            entity_type, entity_data, definition.id, approvers,
        )

        if approvers:
            # Create tasks for Level 1 only (subsequent levels are created when current level completes)
            level_1_approvers = [a for a in approvers if a["level"] == 1]
            logger.info("Level 1 approvers: %s", level_1_approvers)
            for assignment in level_1_approvers:
                if assignment["assignment_type"] == "USER" and assignment["user_id"]:
                    # Direct user assignment
                    await self._approval_matrix.create_approval_task(
                        instance_id=instance.id,
                        assignee_id=UUID(str(assignment["user_id"])),
                        level=1,
                    )
                elif assignment["assignment_type"] == "ROLE" and assignment["role_id"]:
                    # Role-based assignment — resolve to actual users with this role
                    user_ids = await self._resolve_users_for_role(UUID(str(assignment["role_id"])))
                    logger.info(
                        "Role %s resolved to users: %s", assignment["role_id"], user_ids
                    )
                    for uid in user_ids:
                        await self._approval_matrix.create_approval_task(
                            instance_id=instance.id,
                            assignee_id=uid,
                            level=1,
                        )
        else:
            logger.warning(
                "NO approvers resolved for entity_type=%s — L1 tasks will NOT be created!",
                entity_type,
            )

        await self._session.flush()

        logger.info(
            "Workflow started: definition=%s entity=%s/%s instance=%s",
            definition_code, entity_type, entity_id, instance.id,
        )

        return {
            "instance_id": str(instance.id),
            "definition_code": definition_code,
            "current_status": initial_status.code,
            "started_at": instance.started_at.isoformat(),
        }

    async def _resolve_users_for_role(self, role_id: UUID) -> list[UUID]:
        """
        Find all active users assigned to the given role.

        Queries role_assignments WHERE role_id = :rid AND is_active = True,
        returns a list of user UUIDs.
        """
        from src.infrastructure.database.models.role_model import RoleAssignmentModel

        stmt = select(RoleAssignmentModel.user_id).where(
            RoleAssignmentModel.role_id == str(role_id),
            RoleAssignmentModel.is_active == True,
        )
        result = await self._session.execute(stmt)
        # row[0] may be asyncpg UUID or string — convert via str() first
        return [UUID(str(row[0])) for row in result.all()]

    async def execute_action(
        self,
        instance_id: UUID,
        action_code: str,
        actor_id: UUID,
        actor_username: str,
        comments: str = "",
        ip_address: str = "",
    ) -> dict:
        """
        Execute a workflow action (approve, reject, refer back, etc.).

        1. Validates the actor has a pending approval task for this instance
        2. Executes state transition via state machine
        3. Completes the current approval task (marks COMPLETED with action taken)
        4. Cancels any other pending tasks for the same level (parallel approvals)
        5. Creates next-level approval tasks (if action is APPROVE and more levels exist)
        6. For REFER_BACK: creates a task for the initiator so they can resubmit
        7. Returns new state
        """
        from src.infrastructure.database.models.workflow.approval_matrix_models import (
            ApprovalTaskModel,
        )
        from src.infrastructure.database.models.workflow.workflow_models import (
            WorkflowInstanceModel,
        )
        from datetime import datetime, timezone

        # ── Step 1: Validate actor has a pending task for this instance ───────
        # (Skip validation for system-level actions like SUBMIT)
        actor_task = None
        if action_code.upper() not in ("SUBMIT",):
            task_stmt = select(ApprovalTaskModel).where(
                ApprovalTaskModel.instance_id == str(instance_id),
                ApprovalTaskModel.assignee_id == str(actor_id),
                ApprovalTaskModel.status == "PENDING",
            )
            task_result = await self._session.execute(task_stmt)
            actor_task = task_result.scalar_one_or_none()

            if actor_task is None:
                raise PermissionError(
                    "No pending approval task found for this user on this workflow instance."
                )

        # ── Step 2: Execute state transition ──────────────────────────────────
        transition_result = await self._state_machine.execute_transition(
            instance_id=instance_id,
            action_code=action_code,
            actor_id=actor_id,
            actor_username=actor_username,
            comments=comments,
            ip_address=ip_address,
        )

        # ── Step 3: Complete the actor's approval task ────────────────────────
        current_level = 1
        if actor_task is not None:
            actor_task.status = "COMPLETED"
            actor_task.action_taken = action_code.upper()
            actor_task.comments = comments
            current_level = actor_task.level

        # ── Step 4: Cancel all other PENDING tasks for the same instance & level
        # (handles parallel approval scenarios — once one person acts, others lose the task)
        # IMPORTANT: Skip this for SUBMIT — tasks were just created by start_workflow
        if action_code.upper() not in ("SUBMIT",):
            all_pending_stmt = select(ApprovalTaskModel).where(
                ApprovalTaskModel.instance_id == str(instance_id),
                ApprovalTaskModel.status == "PENDING",
                ApprovalTaskModel.level == current_level,
            )
            all_pending_result = await self._session.execute(all_pending_stmt)
            for task in all_pending_result.scalars().all():
                task.status = "CANCELLED"
                task.action_taken = f"CANCELLED_BY_{action_code.upper()}"

        # ── Step 5: Handle next steps based on action type ────────────────────
        if action_code.upper() in ("APPROVE", "FINAL_APPROVE"):
            # Check if this is the final approval (terminal state reached)
            if not transition_result.get("is_completed", False):
                # Not terminal — create tasks for the next approval level.
                # Determine the correct next level: look at the new state to
                # figure out which approval level should act next.
                # Strategy: find the highest level with existing tasks, then
                # create for the level after that. If no tasks created by
                # incrementing, try creating for the SAME level as current
                # (covers the case where the actor was at a lower matrix level
                # but the state machine advanced to a higher-level state).
                tasks_created = await self._create_next_level_tasks(
                    instance_id=instance_id,
                    current_level=current_level,
                )
                
                # If no tasks were created by incrementing, check if we need
                # tasks for the current_level (e.g., L1 approver moved state
                # to L2_PENDING, we need L2 tasks, not L3)
                if not tasks_created:
                    # Try to determine the correct level from the new state.
                    # Parse the status code for a level hint (e.g., "L2_PENDING" → level 2)
                    new_status_code = transition_result.get("current_status_code", "")
                    target_level = self._extract_level_from_status(new_status_code)
                    if target_level and target_level != current_level + 1:
                        await self._create_next_level_tasks(
                            instance_id=instance_id,
                            current_level=target_level - 1,  # Will create for target_level
                        )

        elif action_code.upper() == "REFER_BACK":
            # ── Step 6: Create task for the initiator ─────────────────────────
            instance_stmt = select(WorkflowInstanceModel).where(
                WorkflowInstanceModel.id == str(instance_id)
            )
            instance_result = await self._session.execute(instance_stmt)
            instance = instance_result.scalar_one_or_none()

            if instance:
                initiator_id = UUID(str(instance.initiated_by))
                await self._approval_matrix.create_approval_task(
                    instance_id=instance_id,
                    assignee_id=initiator_id,
                    level=0,  # Level 0 = initiator resubmission task
                )

        elif action_code.upper() == "REJECT":
            # Terminal state — cancel ALL remaining pending tasks on this instance
            all_instance_pending_stmt = select(ApprovalTaskModel).where(
                ApprovalTaskModel.instance_id == str(instance_id),
                ApprovalTaskModel.status == "PENDING",
            )
            all_instance_pending_result = await self._session.execute(all_instance_pending_stmt)
            for task in all_instance_pending_result.scalars().all():
                task.status = "CANCELLED"
                task.action_taken = "CANCELLED_BY_REJECT"

        await self._session.flush()

        logger.info(
            "Action executed: instance=%s action=%s new_status=%s level=%d",
            instance_id, action_code, transition_result["current_status_code"], current_level,
        )

        return transition_result

    async def _create_next_level_tasks(
        self,
        instance_id: UUID,
        current_level: int,
    ) -> bool:
        """
        Resolve and create approval tasks for the next level after the current
        level is completed.

        Reads the approval matrix assignments and creates tasks for the next
        sequential level (current_level + 1).
        
        Returns True if tasks were created, False otherwise.
        """
        from src.infrastructure.database.models.workflow.workflow_models import (
            WorkflowInstanceModel,
        )

        # Get instance to find entity_type for matrix lookup
        instance_stmt = select(WorkflowInstanceModel).where(
            WorkflowInstanceModel.id == str(instance_id)
        )
        instance_result = await self._session.execute(instance_stmt)
        instance = instance_result.scalar_one_or_none()
        if not instance:
            return False

        entity_data = instance.extra_data or {}
        approvers = await self._approval_matrix.resolve_approvers(
            instance.entity_type, entity_data,
            workflow_definition_id=str(instance.workflow_definition_id),
        )

        if not approvers:
            return False

        next_level = current_level + 1
        next_level_approvers = [a for a in approvers if a["level"] == next_level]

        if not next_level_approvers:
            logger.info(
                "No approvers found for level %d, instance %s.",
                next_level, instance_id,
            )
            return False

        tasks_created = False
        for assignment in next_level_approvers:
            if assignment["assignment_type"] == "USER" and assignment["user_id"]:
                await self._approval_matrix.create_approval_task(
                    instance_id=instance_id,
                    assignee_id=UUID(str(assignment["user_id"])),
                    level=next_level,
                )
                tasks_created = True
            elif assignment["assignment_type"] == "ROLE" and assignment["role_id"]:
                user_ids = await self._resolve_users_for_role(
                    UUID(str(assignment["role_id"]))
                )
                for uid in user_ids:
                    await self._approval_matrix.create_approval_task(
                        instance_id=instance_id,
                        assignee_id=uid,
                        level=next_level,
                    )
                    tasks_created = True

        return tasks_created

    @staticmethod
    def _extract_level_from_status(status_code: str) -> int | None:
        """
        Extract an approval level number from a status code like 'L2_PENDING'.
        Returns the level number or None if not parseable.
        """
        import re
        match = re.match(r'L(\d+)', status_code, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return None

    async def get_available_actions(self, instance_id: UUID) -> list[dict]:
        """Get actions available for the current state of a workflow instance."""
        return await self._state_machine.get_available_actions(instance_id)

    async def get_workflow_status(self, instance_id: UUID) -> dict:
        """Get current status of a workflow instance."""
        return await self._state_machine.get_current_state(instance_id)

    async def get_pending_tasks(self, user_id: UUID) -> list[dict]:
        """Get all pending approval tasks assigned to a user."""
        from src.infrastructure.database.models.workflow.approval_matrix_models import ApprovalTaskModel
        from src.infrastructure.database.models.workflow.workflow_models import WorkflowInstanceModel

        stmt = select(ApprovalTaskModel).where(
            ApprovalTaskModel.assignee_id == str(user_id),
            ApprovalTaskModel.status == "PENDING",
        )
        result = await self._session.execute(stmt)
        tasks = result.scalars().all()

        return [
            {
                "task_id": str(t.id),
                "instance_id": str(t.instance_id),
                "level": t.level,
                "status": t.status,
                "due_date": t.due_date.isoformat() if t.due_date else None,
            }
            for t in tasks
        ]

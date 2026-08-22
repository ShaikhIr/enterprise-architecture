"""
In-memory fakes for the workflow engine's repository ports.

The engine is deliberately written against ports rather than SQLAlchemy, so its
behaviour can be pinned down without a database. These fakes are the payoff: the
whole approval chain is exercised in-process, in milliseconds, with no fixtures to
tear down.

Two behaviours are copied from the real adapters because the engine depends on
them and a naive fake would hide bugs:

1. Reads return copies. A caller mutating a returned entity changes nothing until
   it calls `update`, exactly as with a detached ORM row. Sharing objects by
   reference would make `approval_level` appear to persist itself and mask a
   missing `update` call.
2. `list_tasks_for_instance` orders by (level, created_date), which is what the
   coordinator relies on when it reads back which matrix opened the chain.
"""

import copy
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from src.domain.entities.approval_matrix import (
    ApprovalAssignment,
    ApprovalMatrix,
    ApprovalRule,
    ApprovalTask,
)
from src.domain.entities.role import RoleAssignment
from src.domain.entities.workflow import (
    WorkflowDefinition,
    WorkflowHistoryEntry,
    WorkflowInstance,
    WorkflowStatus,
    WorkflowTransition,
)
from src.domain.enums.workflow_enums import (
    ApprovalTaskStatus,
    AssignmentType,
    WorkflowActionType,
)
from src.domain.repositories.approval_matrix_repository import IApprovalMatrixRepository
from src.domain.repositories.role_assignment_repository import IRoleAssignmentRepository
from src.domain.repositories.workflow_definition_repository import (
    IWorkflowDefinitionRepository,
)
from src.domain.repositories.workflow_instance_repository import (
    IWorkflowInstanceRepository,
)

if TYPE_CHECKING:
    from src.application.services.workflow.workflow_engine import WorkflowEngine


class FakeWorkflowDefinitionRepository(IWorkflowDefinitionRepository):
    """In-memory workflow configuration store."""

    def __init__(self) -> None:
        self.definitions: dict[UUID, WorkflowDefinition] = {}
        self.statuses: dict[UUID, WorkflowStatus] = {}
        self.transitions: dict[UUID, WorkflowTransition] = {}
        #: Settable so `delete_status` guards can be tested without instances.
        self.instances_in_status: dict[UUID, int] = {}

    # ─── Definitions ───

    async def get_by_id(self, entity_id: UUID) -> WorkflowDefinition | None:
        return copy.deepcopy(self.definitions.get(entity_id))

    async def get_by_code(self, code: str) -> WorkflowDefinition | None:
        for definition in self.definitions.values():
            if definition.code == code:
                return copy.deepcopy(definition)
        return None

    async def create(self, entity: WorkflowDefinition) -> WorkflowDefinition:
        self.definitions[entity.id] = copy.deepcopy(entity)
        return copy.deepcopy(entity)

    async def update(self, entity: WorkflowDefinition) -> WorkflowDefinition:
        self.definitions[entity.id] = copy.deepcopy(entity)
        return copy.deepcopy(entity)

    async def delete(self, entity_id: UUID) -> None:
        self.definitions.pop(entity_id, None)

    async def list_all(
        self,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        is_active: bool | None = None,
        entity_type: str | None = None,
    ) -> list[WorkflowDefinition]:
        rows = self._filtered(search, is_active, entity_type)
        return [copy.deepcopy(d) for d in rows[skip : skip + limit]]

    async def count(
        self,
        search: str | None = None,
        is_active: bool | None = None,
        entity_type: str | None = None,
    ) -> int:
        return len(self._filtered(search, is_active, entity_type))

    async def exists_by_code(self, code: str, exclude_id: UUID | None = None) -> bool:
        return any(
            d.code == code and d.id != exclude_id for d in self.definitions.values()
        )

    async def exists_by_name(self, name: str, exclude_id: UUID | None = None) -> bool:
        return any(
            d.name.lower() == name.lower() and d.id != exclude_id
            for d in self.definitions.values()
        )

    async def get_definitions_by_ids(
        self, definition_ids: list[UUID]
    ) -> list[WorkflowDefinition]:
        wanted = set(definition_ids)
        return [copy.deepcopy(d) for d in self.definitions.values() if d.id in wanted]

    def _filtered(
        self, search: str | None, is_active: bool | None, entity_type: str | None
    ) -> list[WorkflowDefinition]:
        rows = sorted(self.definitions.values(), key=lambda d: d.code)
        if search:
            needle = search.lower()
            rows = [
                d
                for d in rows
                if needle in d.code.lower()
                or needle in d.name.lower()
                or needle in d.entity_type.lower()
            ]
        if is_active is not None:
            rows = [d for d in rows if d.is_active is is_active]
        if entity_type:
            rows = [d for d in rows if d.entity_type == entity_type]
        return rows

    # ─── Statuses ───

    async def list_statuses(self, definition_id: UUID) -> list[WorkflowStatus]:
        rows = [
            s
            for s in self.statuses.values()
            if s.workflow_definition_id == definition_id
        ]
        rows.sort(key=lambda s: (s.sequence, s.code))
        return [copy.deepcopy(s) for s in rows]

    async def get_status(self, status_id: UUID) -> WorkflowStatus | None:
        return copy.deepcopy(self.statuses.get(status_id))

    async def get_statuses_by_ids(self, status_ids: list[UUID]) -> list[WorkflowStatus]:
        wanted = set(status_ids)
        return [copy.deepcopy(s) for s in self.statuses.values() if s.id in wanted]

    async def get_initial_status(self, definition_id: UUID) -> WorkflowStatus | None:
        for status in sorted(self.statuses.values(), key=lambda s: s.sequence):
            if status.workflow_definition_id == definition_id and status.is_initial:
                return copy.deepcopy(status)
        return None

    async def exists_status_code(
        self, definition_id: UUID, code: str, exclude_id: UUID | None = None
    ) -> bool:
        return any(
            s.workflow_definition_id == definition_id
            and s.code == code
            and s.id != exclude_id
            for s in self.statuses.values()
        )

    async def create_status(self, status: WorkflowStatus) -> WorkflowStatus:
        self.statuses[status.id] = copy.deepcopy(status)
        return copy.deepcopy(status)

    async def update_status(self, status: WorkflowStatus) -> WorkflowStatus:
        self.statuses[status.id] = copy.deepcopy(status)
        return copy.deepcopy(status)

    async def delete_status(self, status_id: UUID) -> None:
        self.statuses.pop(status_id, None)

    async def count_transitions_touching_status(self, status_id: UUID) -> int:
        return sum(
            1
            for t in self.transitions.values()
            if status_id in (t.from_status_id, t.to_status_id)
        )

    async def count_instances_in_status(self, status_id: UUID) -> int:
        return self.instances_in_status.get(status_id, 0)

    # ─── Transitions ───

    async def list_transitions(self, definition_id: UUID) -> list[WorkflowTransition]:
        rows = [
            t
            for t in self.transitions.values()
            if t.workflow_definition_id == definition_id
        ]
        rows.sort(key=lambda t: (t.priority, t.action_code))
        return [copy.deepcopy(t) for t in rows]

    async def list_transitions_from(
        self, definition_id: UUID, from_status_id: UUID
    ) -> list[WorkflowTransition]:
        rows = [
            t
            for t in self.transitions.values()
            if t.workflow_definition_id == definition_id
            and t.from_status_id == from_status_id
        ]
        rows.sort(key=lambda t: (t.priority, t.action_code))
        return [copy.deepcopy(t) for t in rows]

    async def get_transition(self, transition_id: UUID) -> WorkflowTransition | None:
        return copy.deepcopy(self.transitions.get(transition_id))

    async def find_transition(
        self, definition_id: UUID, from_status_id: UUID, action_code: str
    ) -> WorkflowTransition | None:
        candidates = [
            t
            for t in self.transitions.values()
            if t.workflow_definition_id == definition_id
            and t.from_status_id == from_status_id
            and t.action_code == action_code
        ]
        candidates.sort(key=lambda t: t.priority)
        return copy.deepcopy(candidates[0]) if candidates else None

    async def exists_transition(
        self, definition_id: UUID, from_status_id: UUID, action_code: str
    ) -> bool:
        return await self.find_transition(
            definition_id, from_status_id, action_code
        ) is not None

    async def create_transition(
        self, transition: WorkflowTransition
    ) -> WorkflowTransition:
        self.transitions[transition.id] = copy.deepcopy(transition)
        return copy.deepcopy(transition)

    async def delete_transition(self, transition_id: UUID) -> None:
        self.transitions.pop(transition_id, None)


class FakeWorkflowInstanceRepository(IWorkflowInstanceRepository):
    """In-memory workflow runtime store."""

    def __init__(self) -> None:
        self.instances: dict[UUID, WorkflowInstance] = {}
        self.history: list[WorkflowHistoryEntry] = []

    async def get_by_id(self, instance_id: UUID) -> WorkflowInstance | None:
        return copy.deepcopy(self.instances.get(instance_id))

    async def create(self, instance: WorkflowInstance) -> WorkflowInstance:
        self.instances[instance.id] = copy.deepcopy(instance)
        return copy.deepcopy(instance)

    async def update(self, instance: WorkflowInstance) -> WorkflowInstance:
        if instance.id not in self.instances:
            raise ValueError(f"WorkflowInstance with id {instance.id} not found")
        self.instances[instance.id] = copy.deepcopy(instance)
        return copy.deepcopy(instance)

    async def list_all(
        self,
        skip: int = 0,
        limit: int = 100,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        definition_id: UUID | None = None,
        status_id: UUID | None = None,
        initiated_by: UUID | None = None,
        is_completed: bool | None = None,
    ) -> list[WorkflowInstance]:
        rows = self._filtered(
            entity_type, entity_id, definition_id, status_id, initiated_by, is_completed
        )
        rows.sort(key=lambda i: i.started_at, reverse=True)
        return [copy.deepcopy(i) for i in rows[skip : skip + limit]]

    async def count(
        self,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        definition_id: UUID | None = None,
        status_id: UUID | None = None,
        initiated_by: UUID | None = None,
        is_completed: bool | None = None,
    ) -> int:
        return len(
            self._filtered(
                entity_type,
                entity_id,
                definition_id,
                status_id,
                initiated_by,
                is_completed,
            )
        )

    async def get_open_for_entity(
        self, entity_type: str, entity_id: UUID
    ) -> WorkflowInstance | None:
        open_rows = [
            i
            for i in self.instances.values()
            if i.entity_type == entity_type
            and i.entity_id == entity_id
            and i.completed_at is None
        ]
        open_rows.sort(key=lambda i: i.started_at, reverse=True)
        return copy.deepcopy(open_rows[0]) if open_rows else None

    async def add_history(self, entry: WorkflowHistoryEntry) -> WorkflowHistoryEntry:
        self.history.append(copy.deepcopy(entry))
        return copy.deepcopy(entry)

    async def list_history(self, instance_id: UUID) -> list[WorkflowHistoryEntry]:
        rows = [h for h in self.history if h.instance_id == instance_id]
        rows.sort(key=lambda h: h.created_at, reverse=True)
        return [copy.deepcopy(h) for h in rows]

    def _filtered(
        self,
        entity_type: str | None,
        entity_id: UUID | None,
        definition_id: UUID | None,
        status_id: UUID | None,
        initiated_by: UUID | None,
        is_completed: bool | None,
    ) -> list[WorkflowInstance]:
        rows = list(self.instances.values())
        if entity_type:
            rows = [i for i in rows if i.entity_type == entity_type]
        if entity_id is not None:
            rows = [i for i in rows if i.entity_id == entity_id]
        if definition_id is not None:
            rows = [i for i in rows if i.workflow_definition_id == definition_id]
        if status_id is not None:
            rows = [i for i in rows if i.current_status_id == status_id]
        if initiated_by is not None:
            rows = [i for i in rows if i.initiated_by == initiated_by]
        if is_completed is not None:
            rows = [i for i in rows if i.is_completed is is_completed]
        return rows


class FakeApprovalMatrixRepository(IApprovalMatrixRepository):
    """In-memory approval matrix and approval task store."""

    def __init__(self) -> None:
        self.matrices: dict[UUID, ApprovalMatrix] = {}
        self.tasks: dict[UUID, ApprovalTask] = {}

    # ─── Matrices ───

    async def get_by_id(self, entity_id: UUID) -> ApprovalMatrix | None:
        return copy.deepcopy(self.matrices.get(entity_id))

    async def get_by_code(self, code: str) -> ApprovalMatrix | None:
        for matrix in self.matrices.values():
            if matrix.code == code:
                return copy.deepcopy(matrix)
        return None

    async def create(self, entity: ApprovalMatrix) -> ApprovalMatrix:
        self.matrices[entity.id] = copy.deepcopy(entity)
        return copy.deepcopy(entity)

    async def update(self, entity: ApprovalMatrix) -> ApprovalMatrix:
        self.matrices[entity.id] = copy.deepcopy(entity)
        return copy.deepcopy(entity)

    async def delete(self, entity_id: UUID) -> None:
        self.matrices.pop(entity_id, None)

    async def list_all(
        self,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        is_active: bool | None = None,
        entity_type: str | None = None,
    ) -> list[ApprovalMatrix]:
        rows = sorted(self.matrices.values(), key=lambda m: (m.priority, m.code))
        if search:
            needle = search.lower()
            rows = [
                m
                for m in rows
                if needle in m.code.lower() or needle in m.name.lower()
            ]
        if is_active is not None:
            rows = [m for m in rows if m.is_active is is_active]
        if entity_type:
            rows = [m for m in rows if m.entity_type == entity_type]
        return [copy.deepcopy(m) for m in rows[skip : skip + limit]]

    async def count(
        self,
        search: str | None = None,
        is_active: bool | None = None,
        entity_type: str | None = None,
    ) -> int:
        rows = await self.list_all(
            skip=0,
            limit=10_000,
            search=search,
            is_active=is_active,
            entity_type=entity_type,
        )
        return len(rows)

    async def exists_by_code(self, code: str, exclude_id: UUID | None = None) -> bool:
        return any(
            m.code == code and m.id != exclude_id for m in self.matrices.values()
        )

    async def exists_by_name(self, name: str, exclude_id: UUID | None = None) -> bool:
        return any(
            m.name.lower() == name.lower() and m.id != exclude_id
            for m in self.matrices.values()
        )

    async def list_active_for_entity_type(
        self, entity_type: str
    ) -> list[ApprovalMatrix]:
        rows = [
            m
            for m in self.matrices.values()
            if m.entity_type == entity_type and m.is_active
        ]
        rows.sort(key=lambda m: (m.priority, m.code))
        return [copy.deepcopy(m) for m in rows]

    # ─── Tasks ───

    async def create_task(self, task: ApprovalTask) -> ApprovalTask:
        self.tasks[task.id] = copy.deepcopy(task)
        return copy.deepcopy(task)

    async def get_task(self, task_id: UUID) -> ApprovalTask | None:
        return copy.deepcopy(self.tasks.get(task_id))

    async def update_task(self, task: ApprovalTask) -> ApprovalTask:
        if task.id not in self.tasks:
            raise ValueError(f"ApprovalTask with id {task.id} not found")
        self.tasks[task.id] = copy.deepcopy(task)
        return copy.deepcopy(task)

    async def list_tasks_for_instance(self, instance_id: UUID) -> list[ApprovalTask]:
        rows = [t for t in self.tasks.values() if t.instance_id == instance_id]
        rows.sort(key=lambda t: (t.level, t.created_date))
        return [copy.deepcopy(t) for t in rows]

    async def list_pending_tasks_for_user(self, user_id: UUID) -> list[ApprovalTask]:
        rows = [
            t
            for t in self.tasks.values()
            if t.assignee_id == user_id and t.status == ApprovalTaskStatus.PENDING
        ]
        rows.sort(key=lambda t: t.created_date)
        return [copy.deepcopy(t) for t in rows]

    async def cancel_open_tasks_for_instance(self, instance_id: UUID) -> int:
        changed = 0
        for task in self.tasks.values():
            if task.instance_id == instance_id and task.is_open:
                task.status = ApprovalTaskStatus.CANCELLED
                changed += 1
        return changed

    # ─── Test helpers ───

    def open_tasks(self, instance_id: UUID) -> list[ApprovalTask]:
        """Pending tasks on an instance, ordered by level."""
        rows = [
            t for t in self.tasks.values() if t.instance_id == instance_id and t.is_open
        ]
        rows.sort(key=lambda t: (t.level, t.created_date))
        return rows

    def tasks_at(self, instance_id: UUID, level: int) -> list[ApprovalTask]:
        """Every task ever raised at one level, whatever its status."""
        return [
            t
            for t in self.tasks.values()
            if t.instance_id == instance_id and t.level == level
        ]


class FakeRoleAssignmentRepository(IRoleAssignmentRepository):
    """In-memory role membership, keyed role -> eligible user ids."""

    def __init__(self, members: dict[UUID, list[UUID]] | None = None) -> None:
        self.members: dict[UUID, list[UUID]] = members or {}

    async def list_active_user_ids_for_role(self, role_id: UUID) -> list[UUID]:
        return list(self.members.get(role_id, []))

    async def get_active(self, user_id: UUID, role_id: UUID) -> RoleAssignment | None:
        if user_id in self.members.get(role_id, []):
            return RoleAssignment(id=uuid4(), user_id=user_id, role_id=role_id)
        return None

    async def list_for_user(self, user_id: UUID) -> list[RoleAssignment]:
        return await self.list_active_for_user(user_id)

    async def list_active_for_user(self, user_id: UUID) -> list[RoleAssignment]:
        return [
            RoleAssignment(id=uuid4(), user_id=user_id, role_id=role_id)
            for role_id, users in self.members.items()
            if user_id in users
        ]

    async def deactivate_all_for_user(self, user_id: UUID, modified_by: str) -> int:
        removed = 0
        for users in self.members.values():
            if user_id in users:
                users.remove(user_id)
                removed += 1
        return removed

    async def create(self, assignment: RoleAssignment) -> RoleAssignment:
        self.members.setdefault(assignment.role_id, []).append(assignment.user_id)
        return assignment

    async def deactivate(self, assignment_id: UUID, modified_by: str) -> None:
        return None


# ─────────────────────────── Scenario builders ───────────────────────────


def build_matrix(
    *,
    code: str = "TASK_STANDARD",
    entity_type: str = "compliance_task",
    priority: int = 10,
    is_active: bool = True,
    rules: list[tuple[str, str, str, str]] | None = None,
    levels: list[tuple[int, AssignmentType, UUID]] | None = None,
) -> ApprovalMatrix:
    """
    Build an approval matrix aggregate.

    `rules` entries are (field, operator, value, data_type) and `levels` entries
    are (level, assignment_type, target_id) where the target is read as a role id
    for ROLE levels and a user id for USER levels.
    """
    from src.domain.enums.workflow_enums import RuleDataType, RuleOperator

    matrix_id = uuid4()
    return ApprovalMatrix(
        id=matrix_id,
        code=code,
        name=code.replace("_", " ").title(),
        entity_type=entity_type,
        priority=priority,
        is_active=is_active,
        rules=[
            ApprovalRule(
                id=uuid4(),
                matrix_id=matrix_id,
                field=field,
                operator=RuleOperator(operator),
                value=value,
                data_type=RuleDataType(data_type),
            )
            for field, operator, value, data_type in (rules or [])
        ],
        assignments=[
            ApprovalAssignment(
                id=uuid4(),
                matrix_id=matrix_id,
                level=level,
                assignment_type=assignment_type,
                role_id=target if assignment_type == AssignmentType.ROLE else None,
                user_id=target if assignment_type == AssignmentType.USER else None,
            )
            for level, assignment_type, target in (levels or [])
        ],
    )


class WorkflowScenario:
    """
    The seeded compliance approval workflow, in memory.

        DRAFT --SUBMIT--> L1_REVIEW --APPROVE--> L2_REVIEW --APPROVE--> APPROVED
                              |                     |
                              +--REJECT-->      REJECTED
                              +--REFER_BACK--> DRAFT / L1_REVIEW
        DRAFT --CANCEL--> CANCELLED

    Every transition carries the `action_type` the coordinator reads, which is the
    whole point of the column: `action_code` alone could not tell it what a move
    means.
    """

    ENTITY_TYPE = "compliance_task"

    def __init__(self) -> None:
        self.definitions = FakeWorkflowDefinitionRepository()
        self.instances = FakeWorkflowInstanceRepository()
        self.matrices = FakeApprovalMatrixRepository()

        self.manager_role_id = uuid4()
        self.admin_role_id = uuid4()
        self.manager_a = uuid4()
        self.manager_b = uuid4()
        self.admin = uuid4()
        self.maker = uuid4()
        self.roles = FakeRoleAssignmentRepository(
            {
                self.manager_role_id: [self.manager_a, self.manager_b],
                self.admin_role_id: [self.admin],
            }
        )

        self.definition = WorkflowDefinition(
            id=uuid4(),
            code="COMPLIANCE_TASK_APPROVAL",
            name="Compliance Task Approval",
            entity_type=self.ENTITY_TYPE,
        )
        self.definitions.definitions[self.definition.id] = self.definition

        self.status_ids: dict[str, UUID] = {}
        for code, is_initial, is_terminal, sequence in [
            ("DRAFT", True, False, 10),
            ("L1_REVIEW", False, False, 20),
            ("L2_REVIEW", False, False, 30),
            ("APPROVED", False, True, 40),
            ("REJECTED", False, True, 50),
            ("CANCELLED", False, True, 60),
        ]:
            status = WorkflowStatus(
                id=uuid4(),
                workflow_definition_id=self.definition.id,
                code=code,
                name=code.replace("_", " ").title(),
                is_initial=is_initial,
                is_terminal=is_terminal,
                sequence=sequence,
            )
            self.status_ids[code] = status.id
            self.definitions.statuses[status.id] = status

        for from_code, action_code, to_code, action_type, requires_comment in [
            ("DRAFT", "SUBMIT", "L1_REVIEW", WorkflowActionType.SUBMIT, False),
            ("DRAFT", "CANCEL", "CANCELLED", WorkflowActionType.CANCEL, True),
            ("L1_REVIEW", "APPROVE", "L2_REVIEW", WorkflowActionType.APPROVE, False),
            ("L1_REVIEW", "REFER_BACK", "DRAFT", WorkflowActionType.REFER_BACK, True),
            ("L1_REVIEW", "REJECT", "REJECTED", WorkflowActionType.REJECT, True),
            ("L2_REVIEW", "APPROVE", "APPROVED", WorkflowActionType.APPROVE, False),
            (
                "L2_REVIEW",
                "REFER_BACK",
                "L1_REVIEW",
                WorkflowActionType.REFER_BACK,
                True,
            ),
            ("L2_REVIEW", "REJECT", "REJECTED", WorkflowActionType.REJECT, True),
        ]:
            transition = WorkflowTransition(
                id=uuid4(),
                workflow_definition_id=self.definition.id,
                from_status_id=self.status_ids[from_code],
                to_status_id=self.status_ids[to_code],
                action_code=action_code,
                action_type=action_type,
                requires_comment=requires_comment,
            )
            self.definitions.transitions[transition.id] = transition

    def add_two_level_matrix(self) -> ApprovalMatrix:
        """Level 1 to the manager pool, level 2 to the admin pool."""
        matrix = build_matrix(
            code="TASK_TWO_LEVEL",
            entity_type=self.ENTITY_TYPE,
            levels=[
                (1, AssignmentType.ROLE, self.manager_role_id),
                (2, AssignmentType.ROLE, self.admin_role_id),
            ],
        )
        self.matrices.matrices[matrix.id] = matrix
        return matrix

    def new_instance(
        self,
        *,
        status_code: str = "DRAFT",
        extra_data: dict[str, object] | None = None,
        approval_level: int = 0,
    ) -> WorkflowInstance:
        """Persist an instance sitting in one state."""
        instance = WorkflowInstance(
            id=uuid4(),
            workflow_definition_id=self.definition.id,
            entity_type=self.ENTITY_TYPE,
            entity_id=uuid4(),
            current_status_id=self.status_ids[status_code],
            initiated_by=self.maker,
            extra_data=dict(extra_data or {}),
            approval_level=approval_level,
            started_at=datetime.now(UTC),
        )
        self.instances.instances[instance.id] = copy.deepcopy(instance)
        return instance

    def engine(self) -> "WorkflowEngine":
        """A WorkflowEngine wired to this scenario's fakes."""
        from src.application.services.workflow.workflow_engine import WorkflowEngine

        return WorkflowEngine(
            definition_repo=self.definitions,
            instance_repo=self.instances,
            matrix_repo=self.matrices,
            role_assignment_repo=self.roles,
        )

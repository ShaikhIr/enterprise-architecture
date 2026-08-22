"""
Seed script for a sample compliance approval workflow.
Run via: python -m scripts.seed_workflow

Creates one workflow definition with a maker-checker-plus-second-level state
machine, and two approval matrices for the same entity type so the priority
tie-break is visible in the UI:

    DRAFT --SUBMIT--> L1_REVIEW --APPROVE--> L2_REVIEW --APPROVE--> APPROVED
                          |                      |
                          +--REJECT-->       REJECTED
                          +--REFER_BACK--> DRAFT / L1_REVIEW
    DRAFT --CANCEL--> CANCELLED

Idempotent: re-running skips anything already present, so it is safe to run after
a partial failure or against an environment that has been seeded before.

Requires `python -m scripts.seed_rbac` to have run first, because the approval
levels reference the ADMIN and MANAGER roles by code. Missing roles are reported
and skipped rather than aborting the seed.
"""

import asyncio
import sys
from pathlib import Path
from uuid import UUID, uuid4

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select

from src.infrastructure.database.models.approval_matrix_model import (
    ApprovalAssignmentModel,
    ApprovalMatrixModel,
    ApprovalRuleModel,
)
from src.infrastructure.database.models.role_model import RoleModel
from src.infrastructure.database.models.workflow_model import (
    WorkflowDefinitionModel,
    WorkflowStatusModel,
    WorkflowTransitionModel,
)
from src.infrastructure.database.unit_of_work import UnitOfWork

ACTOR = "seed_script"
ENTITY_TYPE = "compliance_task"
WORKFLOW_CODE = "COMPLIANCE_TASK_APPROVAL"

# (code, name, is_initial, is_terminal, sequence)
STATES = [
    ("DRAFT", "Draft", True, False, 10),
    ("L1_REVIEW", "Level 1 Review", False, False, 20),
    ("L2_REVIEW", "Level 2 Review", False, False, 30),
    ("APPROVED", "Approved", False, True, 40),
    ("REJECTED", "Rejected", False, True, 50),
    ("CANCELLED", "Cancelled", False, True, 60),
]

# (from_code, action_code, to_code, action_type, requires_comment, priority)
#
# `action_type` is what drives the approval chain, and it is separate from
# `action_code` on purpose: the code is a label for the UI, the type is the
# meaning. Here they happen to coincide, but a workflow could just as well name
# its approve action SIGN_OFF and still declare it an APPROVE.
TRANSITIONS = [
    ("DRAFT", "SUBMIT", "L1_REVIEW", "SUBMIT", False, 10),
    ("DRAFT", "CANCEL", "CANCELLED", "CANCEL", True, 20),
    ("L1_REVIEW", "APPROVE", "L2_REVIEW", "APPROVE", False, 10),
    ("L1_REVIEW", "REFER_BACK", "DRAFT", "REFER_BACK", True, 20),
    ("L1_REVIEW", "REJECT", "REJECTED", "REJECT", True, 30),
    ("L2_REVIEW", "APPROVE", "APPROVED", "APPROVE", False, 10),
    ("L2_REVIEW", "REFER_BACK", "L1_REVIEW", "REFER_BACK", True, 20),
    ("L2_REVIEW", "REJECT", "REJECTED", "REJECT", True, 30),
]

# Lower priority is evaluated first, so the specific matrix must sort before the
# catch-all — otherwise the catch-all would swallow every record.
# (code, name, priority, rules, assignments)
_Rule = tuple[str, str, str, str, str]  # field, operator, value, data_type, group
_Assignment = tuple[int, str]  # level, role_code
_Matrix = tuple[str, str, int, list[_Rule], list[_Assignment]]

MATRICES: list[_Matrix] = [
    (
        "COMPLIANCE_TASK_CRITICAL",
        "Critical compliance tasks — two levels",
        10,
        [("risk_level", "EQ", "CRITICAL", "STRING", "default")],
        [(1, "MANAGER"), (2, "ADMIN")],
    ),
    (
        "COMPLIANCE_TASK_STANDARD",
        "All other compliance tasks — single level",
        100,
        [],
        [(1, "MANAGER")],
    ),
]


async def seed() -> None:
    """Seed the sample workflow definition and approval matrices."""
    async with UnitOfWork() as uow:
        session = uow.session

        # ─── 1. Definition ───
        existing = await session.execute(
            select(WorkflowDefinitionModel).where(
                WorkflowDefinitionModel.code == WORKFLOW_CODE
            )
        )
        definition = existing.scalar_one_or_none()

        if definition:
            print(f"  [skip] Workflow '{WORKFLOW_CODE}' already exists")
        else:
            definition = WorkflowDefinitionModel(
                id=uuid4(),
                code=WORKFLOW_CODE,
                name="Compliance Task Approval",
                description=(
                    "Two-level maker-checker approval for compliance tasks, with "
                    "refer-back at both levels."
                ),
                entity_type=ENTITY_TYPE,
                version=1,
                is_active=True,
                created_by=ACTOR,
                modified_by=ACTOR,
            )
            session.add(definition)
            await session.flush()
            print(f"  [new]  Workflow '{WORKFLOW_CODE}' created")

        definition_id = definition.id

        # ─── 2. States ───
        state_ids: dict[str, UUID] = {}
        for code, name, is_initial, is_terminal, sequence in STATES:
            found = await session.execute(
                select(WorkflowStatusModel).where(
                    WorkflowStatusModel.workflow_definition_id == definition_id,
                    WorkflowStatusModel.code == code,
                )
            )
            state = found.scalar_one_or_none()
            if state:
                state_ids[code] = state.id
                print(f"  [skip] State '{code}' already exists")
                continue

            state = WorkflowStatusModel(
                id=uuid4(),
                workflow_definition_id=definition_id,
                code=code,
                name=name,
                is_initial=is_initial,
                is_terminal=is_terminal,
                sequence=sequence,
                created_by=ACTOR,
                modified_by=ACTOR,
            )
            session.add(state)
            state_ids[code] = state.id
            print(f"  [new]  State '{code}' created")

        await session.flush()

        # ─── 3. Transitions ───
        for (
            from_code,
            action_code,
            to_code,
            action_type,
            requires_comment,
            priority,
        ) in TRANSITIONS:
            from_id = state_ids[from_code]
            to_id = state_ids[to_code]

            # Its own variable rather than reusing `found`: mypy pins a variable to
            # the type of its first assignment, so reusing one name across queries
            # for different models makes every later row look like the first model.
            found_transition = await session.execute(
                select(WorkflowTransitionModel).where(
                    WorkflowTransitionModel.workflow_definition_id == definition_id,
                    WorkflowTransitionModel.from_status_id == from_id,
                    WorkflowTransitionModel.action_code == action_code,
                )
            )
            existing_transition = found_transition.scalar_one_or_none()
            if existing_transition:
                # Adopt the declared semantics on re-run, so an environment seeded
                # before action_type existed picks it up instead of staying CUSTOM.
                if existing_transition.action_type != action_type:
                    existing_transition.action_type = action_type
                    existing_transition.modified_by = ACTOR
                    print(
                        f"  [fix]  Transition {from_code} --{action_code}--> "
                        f"action_type set to {action_type}"
                    )
                else:
                    print(f"  [skip] Transition {from_code} --{action_code}--> exists")
                continue

            session.add(
                WorkflowTransitionModel(
                    id=uuid4(),
                    workflow_definition_id=definition_id,
                    from_status_id=from_id,
                    to_status_id=to_id,
                    action_code=action_code,
                    action_type=action_type,
                    guard_expression=None,
                    requires_comment=requires_comment,
                    auto_execute=False,
                    priority=priority,
                    created_by=ACTOR,
                    modified_by=ACTOR,
                )
            )
            print(
                f"  [new]  Transition {from_code} --{action_code}--> {to_code} "
                f"({action_type})"
            )

        await uow.commit()
        print("\nOK Workflow definition seed complete.")

    # ─── 4. Approval matrices ───
    async with UnitOfWork() as uow:
        session = uow.session

        roles = await session.execute(select(RoleModel))
        role_ids = {role.code: role.id for role in roles.scalars().all()}

        for code, name, priority, rules, assignments in MATRICES:
            found_matrix = await session.execute(
                select(ApprovalMatrixModel).where(ApprovalMatrixModel.code == code)
            )
            if found_matrix.scalar_one_or_none():
                print(f"  [skip] Approval matrix '{code}' already exists")
                continue

            matrix = ApprovalMatrixModel(
                id=uuid4(),
                code=code,
                name=name,
                entity_type=ENTITY_TYPE,
                priority=priority,
                is_active=True,
                created_by=ACTOR,
                modified_by=ACTOR,
            )
            session.add(matrix)
            await session.flush()
            print(f"  [new]  Approval matrix '{code}' created")

            for field, operator, value, data_type, logical_group in rules:
                session.add(
                    ApprovalRuleModel(
                        id=uuid4(),
                        matrix_id=matrix.id,
                        field=field,
                        operator=operator,
                        value=value,
                        data_type=data_type,
                        logical_group=logical_group,
                        created_by=ACTOR,
                        modified_by=ACTOR,
                    )
                )
                print(f"  [new]  Rule {field} {operator} {value}")

            for level, role_code in assignments:
                role_id = role_ids.get(role_code)
                if role_id is None:
                    print(
                        f"  [warn] Role '{role_code}' not found - skipping level "
                        f"{level}. Run scripts.seed_rbac first."
                    )
                    continue
                session.add(
                    ApprovalAssignmentModel(
                        id=uuid4(),
                        matrix_id=matrix.id,
                        assignment_type="ROLE",
                        user_id=None,
                        role_id=role_id,
                        level=level,
                        created_by=ACTOR,
                        modified_by=ACTOR,
                    )
                )
                print(f"  [new]  Level {level} -> role {role_code}")

        await uow.commit()
        print("\nOK Approval matrix seed complete.")


if __name__ == "__main__":
    print("Seeding sample compliance workflow...")
    asyncio.run(seed())

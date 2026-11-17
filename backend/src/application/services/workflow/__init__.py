"""
Workflow engine internals.

Split by responsibility so each piece is testable on its own:

- `RuleEvaluator`           — pure predicate logic, no I/O at all
- `StateMachineService`     — validates and executes one transition
- `ApprovalMatrixResolver`  — picks the matching matrix and its approvers
- `ApprovalTaskCoordinator` — the join: turns transitions into approval tasks
- `WorkflowEngine`          — the façade the rest of the application calls
"""

from src.application.services.workflow.approval_matrix_resolver import (
    ApprovalMatrixResolver,
)
from src.application.services.workflow.approval_task_coordinator import (
    ApprovalTaskCoordinator,
)
from src.application.services.workflow.rule_evaluator import RuleEvaluator
from src.application.services.workflow.state_machine_service import StateMachineService
from src.application.services.workflow.workflow_engine import WorkflowEngine

__all__ = [
    "ApprovalMatrixResolver",
    "ApprovalTaskCoordinator",
    "RuleEvaluator",
    "StateMachineService",
    "WorkflowEngine",
]

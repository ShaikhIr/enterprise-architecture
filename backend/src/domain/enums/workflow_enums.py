"""
Workflow engine enumerations.

These are the closed vocabularies the workflow tables persist as short strings.
They live in the domain layer so services and the rule evaluator can validate
against them without importing the ORM.
"""

from enum import StrEnum


class WorkflowActionType(StrEnum):
    """
    What a transition means for the approval chain.

    `action_code` on a transition is free text chosen by whoever designs the
    workflow, so the engine cannot infer intent from it — "SIGN_OFF" and "APPROVE"
    are indistinguishable to code. This enum is the designer's explicit
    declaration, and it is the only thing the approval coordinator reads:

    - SUBMIT      opens the first approval level
    - APPROVE     settles the current level and opens the next one
    - REJECT      settles the current level and abandons the chain
    - CANCEL      abandons the chain
    - REFER_BACK  abandons the chain so it restarts from level 1 on resubmission
    - CLOSE       no effect on the chain
    - ESCALATE    no effect on the chain (raises the task, not the level)
    - CUSTOM      no effect on the chain; the default for plain state moves
    """

    SUBMIT = "SUBMIT"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    REFER_BACK = "REFER_BACK"
    CANCEL = "CANCEL"
    CLOSE = "CLOSE"
    ESCALATE = "ESCALATE"
    CUSTOM = "CUSTOM"


class StepType(StrEnum):
    """What a workflow step asks of its assignee."""

    APPROVAL = "APPROVAL"
    REVIEW = "REVIEW"
    NOTIFICATION = "NOTIFICATION"
    AUTO = "AUTO"


class AssignmentType(StrEnum):
    """How an approver is chosen for a step or approval level."""

    ROLE = "ROLE"
    USER = "USER"
    MATRIX = "MATRIX"
    EXPRESSION = "EXPRESSION"


class ApprovalTaskStatus(StrEnum):
    """Lifecycle of a single approval task."""

    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    ESCALATED = "ESCALATED"


class StateType(StrEnum):
    """Position of a status within its workflow."""

    INITIAL = "INITIAL"
    NORMAL = "NORMAL"
    TERMINAL = "TERMINAL"


class RuleOperator(StrEnum):
    """Comparison operators supported by the approval rule evaluator."""

    EQ = "EQ"
    NEQ = "NEQ"
    GT = "GT"
    GTE = "GTE"
    LT = "LT"
    LTE = "LTE"
    IN = "IN"
    NOT_IN = "NOT_IN"
    CONTAINS = "CONTAINS"
    STARTS_WITH = "STARTS_WITH"


class RuleDataType(StrEnum):
    """How a rule's stored string value is cast before comparison."""

    STRING = "STRING"
    NUMBER = "NUMBER"
    BOOLEAN = "BOOLEAN"
    LIST = "LIST"

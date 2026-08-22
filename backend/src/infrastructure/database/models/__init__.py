"""
SQLAlchemy ORM Models.

All models must be imported here so that SQLAlchemy's Base.metadata
can resolve foreign key relationships between tables at startup.
"""

from src.infrastructure.database.models.approval_matrix_model import (  # noqa: F401
    ApprovalAssignmentModel,
    ApprovalMatrixModel,
    ApprovalRuleModel,
    ApprovalTaskModel,
)
from src.infrastructure.database.models.audit_log_model import AuditLogModel  # noqa: F401
from src.infrastructure.database.models.base_model import Base, BaseModel  # noqa: F401
from src.infrastructure.database.models.category_of_law_model import (
    CategoryOfLawModel,  # noqa: F401
)

# ─── Master data (import parents before children for FK resolution) ───
from src.infrastructure.database.models.country_model import CountryModel  # noqa: F401
from src.infrastructure.database.models.legislation_model import LegislationModel  # noqa: F401
from src.infrastructure.database.models.role_model import (  # noqa: F401
    PermissionModel,
    RoleAssignmentModel,
    RoleModel,
    RolePermissionModel,
)
from src.infrastructure.database.models.rule_model import RuleModel  # noqa: F401
from src.infrastructure.database.models.state_model import StateModel  # noqa: F401
from src.infrastructure.database.models.task_type_model import TaskTypeModel  # noqa: F401
from src.infrastructure.database.models.tenant_model import TenantModel  # noqa: F401
from src.infrastructure.database.models.user_details_model import UserDetailsModel  # noqa: F401
from src.infrastructure.database.models.user_model import UserModel  # noqa: F401

# ─── Workflow engine ───
from src.infrastructure.database.models.workflow_model import (  # noqa: F401
    WorkflowDefinitionModel,
    WorkflowHistoryModel,
    WorkflowInstanceModel,
    WorkflowStatusModel,
    WorkflowTransitionModel,
)

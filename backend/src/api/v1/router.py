"""
API v1 Router - aggregates all v1 endpoint routers.
"""

from fastapi import APIRouter

from src.api.v1.endpoints.approval_matrix_controller import router as approval_matrix_router
from src.api.v1.endpoints.auth_controller import router as auth_router
from src.api.v1.endpoints.category_of_law_controller import router as category_of_law_router
from src.api.v1.endpoints.country_controller import router as country_router
from src.api.v1.endpoints.employee_ad_controller import router as employee_ad_router
from src.api.v1.endpoints.employee_import_controller import router as employee_import_router
from src.api.v1.endpoints.health_controller import router as health_router
from src.api.v1.endpoints.legislation_controller import router as legislation_router
from src.api.v1.endpoints.rbac_controller import router as rbac_router
from src.api.v1.endpoints.rule_controller import router as rule_router
from src.api.v1.endpoints.state_controller import router as state_router
from src.api.v1.endpoints.task_type_controller import router as task_type_router
from src.api.v1.endpoints.user_controller import router as user_router
from src.api.v1.endpoints.workflow_controller import router as workflow_router
from src.api.v1.endpoints.workflow_instance_controller import (
    router as workflow_instance_router,
)

api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(auth_router)
api_v1_router.include_router(user_router)
api_v1_router.include_router(rbac_router)
api_v1_router.include_router(employee_import_router)
api_v1_router.include_router(health_router)
api_v1_router.include_router(employee_ad_router)

# ─── Master data ───
api_v1_router.include_router(country_router)
api_v1_router.include_router(state_router)
api_v1_router.include_router(category_of_law_router)
api_v1_router.include_router(legislation_router)
api_v1_router.include_router(rule_router)
api_v1_router.include_router(task_type_router)

# ─── Workflow engine ───
# Approval matrices are registered before the runtime router so the literal
# /workflow/approval-matrices path is matched ahead of any /workflow/{...} route.
api_v1_router.include_router(approval_matrix_router)
api_v1_router.include_router(workflow_router)
api_v1_router.include_router(workflow_instance_router)

"""
API v1 Router - aggregates all v1 endpoint routers.
"""

from fastapi import APIRouter

from src.api.v1.endpoints.auth_controller import router as auth_router
from src.api.v1.endpoints.employee_ad_controller import router as employee_ad_router
from src.api.v1.endpoints.employee_import_controller import router as employee_import_router
from src.api.v1.endpoints.health_controller import router as health_router
from src.api.v1.endpoints.rbac_controller import router as rbac_router
from src.api.v1.endpoints.user_controller import router as user_router
from src.api.v1.endpoints.workflow.workflow_controller import router as workflow_router
from src.api.v1.endpoints.commission_claim.controller import router as claims_router
from src.api.v1.endpoints.masters.entity_controller import router as entity_router
from src.api.v1.endpoints.masters.vendor_controller import router as vendor_router
from src.api.v1.endpoints.masters.customer_controller import router as customer_router
from src.api.v1.endpoints.masters.product_master_controller import (
    router as product_master_router,
)
from src.api.v1.endpoints.masters.agreement_controller import router as agreement_router
from src.api.v1.endpoints.masters.mapping_controller import router as mapping_router
from src.api.v1.endpoints.masters.invoice_controller import router as invoice_router
from src.api.v1.endpoints.masters.claim_validation_controller import (
    router as claim_validation_router,
)
from src.api.v1.endpoints.masters.bulk_upload_controller import (
    router as bulk_upload_router,
)

api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(auth_router)
api_v1_router.include_router(user_router)
api_v1_router.include_router(rbac_router)
api_v1_router.include_router(employee_import_router)
api_v1_router.include_router(health_router)
api_v1_router.include_router(employee_ad_router)
api_v1_router.include_router(workflow_router)
api_v1_router.include_router(claims_router)
api_v1_router.include_router(entity_router)
api_v1_router.include_router(vendor_router)
api_v1_router.include_router(customer_router)
api_v1_router.include_router(product_master_router)
api_v1_router.include_router(agreement_router)
api_v1_router.include_router(mapping_router)
api_v1_router.include_router(invoice_router)
api_v1_router.include_router(claim_validation_router)
api_v1_router.include_router(bulk_upload_router)

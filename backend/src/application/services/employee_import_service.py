"""
Employee (Darwin AD) import.

Fetches employee profiles from Darwin by id and upserts each into `users` +
`user_details`. Depends only on `IEmployeeImportWriter` and `IPasswordHasher` — no
SQLAlchemy session, no ORM models — so this stays testable with fakes and keeps the
application layer's ban on infrastructure imports.

One employee failing (a bad id, a too-long field) must not fail the others in the same
request — that per-record isolation is the writer's job (see
`EmployeeImportWriterImpl.upsert_employee`); this service only decides what to write.
"""

from dataclasses import dataclass, field
from typing import Any

from src.application.ports.employee_import_writer import IEmployeeImportWriter
from src.domain.services.password_hasher import IPasswordHasher

__all__ = ["EmployeeImportResult", "EmployeeImportService"]


@dataclass
class EmployeeImportResult:
    """Summary of one import call, plus a per-employee breakdown."""

    total: int = 0
    created: int = 0
    updated: int = 0
    failed: int = 0
    results: list[dict[str, str]] = field(default_factory=list)


class EmployeeImportService:
    """Orchestrates one `import_employees` call."""

    def __init__(
        self,
        writer: IEmployeeImportWriter,
        password_hasher: IPasswordHasher,
    ) -> None:
        self._writer = writer
        self._hasher = password_hasher

    async def import_employees(
        self, darwin_response: dict[str, Any] | list[Any], actor: str
    ) -> EmployeeImportResult:
        """
        Upsert every employee record Darwin returned.

        `darwin_response` is Darwin's raw JSON — a dict normally carrying
        `employeeData`, but tolerated as a bare list or as any dict whose first
        list-valued key holds the records, matching the shape Darwin has been
        observed to return.
        """
        employee_data_list = self._extract_employee_list(darwin_response)

        result = EmployeeImportResult()
        for emp_data in employee_data_list:
            emp_id = self._extract_employee_id(emp_data)
            if not emp_id:
                result.failed += 1
                result.results.append(
                    {
                        "employee_id": "unknown",
                        "status": "failed",
                        "message": "No EmployeeId in Darwin response",
                    }
                )
                continue

            outcome = await self._writer.upsert_employee(
                employee_id=emp_id,
                details_fields=self._extract_details_fields(emp_data),
                new_user_password_hash=self._hasher.hash(emp_id),
                actor=actor,
            )
            result.total += 1
            if outcome.status == "created":
                result.created += 1
            elif outcome.status == "updated":
                result.updated += 1
            else:
                result.failed += 1
            result.results.append(
                {
                    "employee_id": outcome.employee_id,
                    "status": outcome.status,
                    "message": outcome.message,
                }
            )

        result.total = len(result.results)
        return result

    # ─── Darwin response shape handling ───

    @staticmethod
    def _extract_employee_list(
        darwin_response: dict[str, Any] | list[Any],
    ) -> list[dict[str, Any]]:
        if isinstance(darwin_response, list):
            return darwin_response

        employee_data_list: list[dict[str, Any]] = darwin_response.get("employeeData", [])
        if employee_data_list:
            return employee_data_list

        # Darwin's key naming has been observed to vary; fall back to the first
        # list-valued key in the response.
        for value in darwin_response.values():
            if isinstance(value, list) and len(value) > 0:
                return value
        return []

    @staticmethod
    def _extract_employee_id(emp_data: dict[str, Any]) -> str:
        return str(
            emp_data.get(
                "employee_id", emp_data.get("EmployeeId", emp_data.get("employeeId", ""))
            )
        ).strip()

    @staticmethod
    def _extract_details_fields(emp_data: dict[str, Any]) -> dict[str, Any]:
        """Normalize Darwin's snake_case employee fields into user_details columns."""

        def get(key: str) -> str:
            val = emp_data.get(key, "")
            return str(val).strip() if val is not None else ""

        first = get("first_name")
        middle = get("middle_name")
        last = get("last_name")
        full_name = " ".join(part for part in [first, middle, last] if part)

        return {
            "employee_id": get("employee_id"),
            "employee_name": full_name,
            "first_name": first,
            "middle_name": middle,
            "last_name": last,
            "email": get("company_email_id"),
            "designation_title": get("designation_title"),
            "department": get("department"),
            "business_unit": get("business_unit"),
            "group_company": get("group_company"),
            "location": get("office_location"),
            "region": get("office_state"),
            "zone": get("office_city"),
            "grade": get("job_level"),
            "office_mobile_no": get("office_mobile_no"),
            "personal_mobile_no": get("personal_mobile_no"),
            "date_of_joining": get("date_of_joining") or get("date_of_birth"),
            "reporting_manager": get("direct_manager_name"),
            "direct_manager_employee_id": get("direct_manager_employee_id"),
            "direct_manager_name": get("direct_manager_name"),
            "direct_manager_email": get("direct_manager_email"),
            "sap_user_id": get("cost_center_id"),
            "division_id": get("division"),
            "territory_id": get("territory_code_(sales_hq_code)"),
        }

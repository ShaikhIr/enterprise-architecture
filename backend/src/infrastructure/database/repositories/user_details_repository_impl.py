"""
User details repository implementation (Adapter).
Implements IUserDetailsRepository using SQLAlchemy async.
"""


from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.user_details import UserDetails
from src.domain.repositories.user_details_repository import IUserDetailsRepository
from src.infrastructure.database.models.user_details_model import UserDetailsModel


class UserDetailsRepositoryImpl(IUserDetailsRepository):
    """Concrete implementation of user details persistence using SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_user_id(self, user_id: int) -> UserDetails | None:
        stmt = select(UserDetailsModel).where(UserDetailsModel.user_id == user_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_many_by_user_ids(
        self, user_ids: list[int]
    ) -> dict[int, UserDetails]:
        if not user_ids:
            return {}
        stmt = select(UserDetailsModel).where(UserDetailsModel.user_id.in_(user_ids))
        result = await self._session.execute(stmt)
        return {m.user_id: self._to_entity(m) for m in result.scalars().all()}

    async def create(self, details: UserDetails) -> UserDetails:
        model = UserDetailsModel(
            user_id=details.user_id,
            employee_id=details.employee_id,
            employee_name=details.employee_name,
            first_name=details.first_name,
            middle_name=details.middle_name,
            last_name=details.last_name,
            email=details.email,
            designation_title=details.designation_title,
            department=details.department,
            business_unit=details.business_unit,
            group_company=details.group_company,
            location=details.location,
            region=details.region,
            zone=details.zone,
            grade=details.grade,
            office_mobile_no=details.office_mobile_no,
            personal_mobile_no=details.personal_mobile_no,
            date_of_joining=details.date_of_joining,
            reporting_manager=details.reporting_manager,
            direct_manager_employee_id=details.direct_manager_employee_id,
            direct_manager_name=details.direct_manager_name,
            direct_manager_email=details.direct_manager_email,
            sap_user_id=details.sap_user_id,
            division_id=details.division_id,
            territory_id=details.territory_id,
            created_by=details.created_by,
            modified_by=details.modified_by,
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_entity(model)

    async def update(self, details: UserDetails) -> UserDetails:
        stmt = select(UserDetailsModel).where(UserDetailsModel.id == details.id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            raise ValueError(f"UserDetails with id {details.id} not found")

        model.employee_id = details.employee_id
        model.employee_name = details.employee_name
        model.first_name = details.first_name
        model.middle_name = details.middle_name
        model.last_name = details.last_name
        model.email = details.email
        model.designation_title = details.designation_title
        model.department = details.department
        model.business_unit = details.business_unit
        model.group_company = details.group_company
        model.location = details.location
        model.region = details.region
        model.zone = details.zone
        model.grade = details.grade
        model.office_mobile_no = details.office_mobile_no
        model.personal_mobile_no = details.personal_mobile_no
        model.date_of_joining = details.date_of_joining
        model.reporting_manager = details.reporting_manager
        model.direct_manager_employee_id = details.direct_manager_employee_id
        model.direct_manager_name = details.direct_manager_name
        model.direct_manager_email = details.direct_manager_email
        model.sap_user_id = details.sap_user_id
        model.division_id = details.division_id
        model.territory_id = details.territory_id
        model.modified_by = details.modified_by
        model.modified_date = details.modified_date

        await self._session.flush()
        return self._to_entity(model)

    @staticmethod
    def _to_entity(model: UserDetailsModel) -> UserDetails:
        """Map ORM model to domain entity."""
        return UserDetails(
            id=model.id,
            user_id=model.user_id,
            employee_id=model.employee_id,
            employee_name=model.employee_name,
            first_name=model.first_name,
            middle_name=model.middle_name,
            last_name=model.last_name,
            email=model.email,
            designation_title=model.designation_title,
            department=model.department,
            business_unit=model.business_unit,
            group_company=model.group_company,
            location=model.location,
            region=model.region,
            zone=model.zone,
            grade=model.grade,
            office_mobile_no=model.office_mobile_no,
            personal_mobile_no=model.personal_mobile_no,
            date_of_joining=model.date_of_joining,
            reporting_manager=model.reporting_manager,
            direct_manager_employee_id=model.direct_manager_employee_id,
            direct_manager_name=model.direct_manager_name,
            direct_manager_email=model.direct_manager_email,
            sap_user_id=model.sap_user_id,
            division_id=model.division_id,
            territory_id=model.territory_id,
            created_by=model.created_by,
            created_date=model.created_date,
            modified_by=model.modified_by,
            modified_date=model.modified_date,
        )

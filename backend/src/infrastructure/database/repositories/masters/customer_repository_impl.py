"""
Customer repository implementation (Adapter).
Implements ``ICustomerRepository`` using SQLAlchemy async.
"""

from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.masters.customer import CustomerEntity
from src.domain.enums.masters import CustomerStatus
from src.domain.repositories.masters.customer_repository import ICustomerRepository
from src.infrastructure.database.models.masters.customer_model import CustomerModel

# Reference tables that own a ``customer_id`` FK. These constants remain for
# backward compatibility with the mapping delete guard.
_MAPPING_TABLE = "vendor_customer_mappings"
_MAPPING_CUSTOMER_COLUMN = "customer_id"
_MAPPING_STATUS_COLUMN = "status"
_MAPPING_ACTIVE_STATUS = "Active"


class CustomerRepositoryImpl(ICustomerRepository):
    """Concrete implementation of customer persistence using SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, customer_id: UUID) -> CustomerEntity | None:
        stmt = select(CustomerModel).where(CustomerModel.id == customer_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_by_customer_code(
        self, customer_code: str
    ) -> CustomerEntity | None:
        stmt = select(CustomerModel).where(
            CustomerModel.customer_code == customer_code
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def create(self, customer: CustomerEntity) -> CustomerEntity:
        model = CustomerModel(
            id=customer.id,
            customer_code=customer.customer_code,
            customer_name=customer.customer_name,
            address=customer.address,
            gstn_number=customer.gstn_number,
            contact_person=customer.contact_person,
            contact_number=customer.contact_number,
            contact_email=customer.contact_email,
            status=customer.status.value,
            created_by=customer.created_by,
            modified_by=customer.modified_by,
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_entity(model)

    async def update(self, customer: CustomerEntity) -> CustomerEntity:
        stmt = select(CustomerModel).where(CustomerModel.id == customer.id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            raise ValueError(f"Customer with id {customer.id} not found")

        model.customer_code = customer.customer_code
        model.customer_name = customer.customer_name
        model.address = customer.address
        model.gstn_number = customer.gstn_number
        model.contact_person = customer.contact_person
        model.contact_number = customer.contact_number
        model.contact_email = customer.contact_email
        model.status = customer.status.value
        model.modified_by = customer.modified_by
        model.modified_date = customer.modified_date

        await self._session.flush()
        return self._to_entity(model)

    async def delete(self, customer_id: UUID) -> None:
        stmt = select(CustomerModel).where(CustomerModel.id == customer_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model:
            await self._session.delete(model)
            await self._session.flush()

    async def list_customers(
        self,
        skip: int = 0,
        limit: int = 20,
        customer_code: str | None = None,
        customer_name: str | None = None,
    ) -> list[CustomerEntity]:
        stmt = select(CustomerModel)
        if customer_code:
            stmt = stmt.where(
                CustomerModel.customer_code.ilike(f"%{customer_code}%")
            )
        if customer_name:
            stmt = stmt.where(
                CustomerModel.customer_name.ilike(f"%{customer_name}%")
            )
        stmt = stmt.order_by(CustomerModel.customer_code).offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [self._to_entity(m) for m in models]

    async def count(
        self,
        customer_code: str | None = None,
        customer_name: str | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(CustomerModel)
        if customer_code:
            stmt = stmt.where(
                CustomerModel.customer_code.ilike(f"%{customer_code}%")
            )
        if customer_name:
            stmt = stmt.where(
                CustomerModel.customer_name.ilike(f"%{customer_name}%")
            )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def exists_by_customer_code(self, customer_code: str) -> bool:
        stmt = select(CustomerModel.id).where(
            CustomerModel.customer_code == customer_code
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def is_referenced_by_active_mapping(self, customer_id: UUID) -> bool:
        """
        Return True if an active Vendor-Customer Mapping references the customer.

        The mapping table is created by a concurrent task; if it does not yet
        exist this returns False (no references possible), so the delete guard
        degrades safely until the table is present.
        """
        if not await self._table_exists(_MAPPING_TABLE):
            return False

        query = text(
            f"SELECT 1 FROM {_MAPPING_TABLE} "
            f"WHERE {_MAPPING_CUSTOMER_COLUMN} = :customer_id "
            f"AND {_MAPPING_STATUS_COLUMN} = :active_status "
            f"LIMIT 1"
        )
        result = await self._session.execute(
            query,
            {
                "customer_id": str(customer_id),
                "active_status": _MAPPING_ACTIVE_STATUS,
            },
        )
        return result.first() is not None

    async def is_referenced_by_invoice_header(self, customer_id: UUID) -> bool:
        """
        Invoice headers no longer reference customers directly (customer_id
        was removed). Always returns False so the delete guard passes.
        """
        return False

    async def _table_exists(self, table_name: str) -> bool:
        """Check whether a table exists in the current database schema."""
        query = text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name = :table_name LIMIT 1"
        )
        result = await self._session.execute(query, {"table_name": table_name})
        return result.first() is not None

    @staticmethod
    def _to_entity(model: CustomerModel) -> CustomerEntity:
        """Map ORM model to domain entity."""
        return CustomerEntity(
            id=model.id,
            customer_code=model.customer_code,
            customer_name=model.customer_name,
            address=model.address,
            gstn_number=model.gstn_number,
            contact_person=model.contact_person,
            contact_number=model.contact_number,
            contact_email=model.contact_email,
            status=CustomerStatus(model.status),
            created_by=model.created_by,
            created_date=model.created_date,
            modified_by=model.modified_by,
            modified_date=model.modified_date,
        )

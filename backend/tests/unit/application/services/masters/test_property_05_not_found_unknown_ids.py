# Feature: lacm-masters, Property 5: Not-found for unknown identifiers (cross-master).
"""Property-based test for not-found behaviour on unknown identifiers.

Property 5: Not-found for unknown identifiers.

**Validates: Requirements 1.7, 6.10, 7.1, 8.10, 9.6, 10.8, 11.11, 13.6, 14.9, 17.4**

*For any* UUID not present in a master's store, a read, update, delete,
deactivate, or renew operation against that master raises a
``MasterNotFoundError`` and modifies no record. This single cross-master test
exercises every applicable master per the design's traceability table:
Entity, Vendor, Customer, Product Master, Product Detail, Agreement, Mapping,
and Invoice.

Each generated example builds a fresh service/repository set whose stores are
**empty**, so every generated UUID is necessarily unknown. The repositories are
lightweight in-memory fakes (duck-typed against the repository ports, not
mocks) that record every write (create/update/delete). After each operation we
assert that the expected not-found error was raised and that the fake recorded
no write — proving the rejected operation modified no record. The async
services are driven with ``asyncio.run`` because each Hypothesis example is
independent.
"""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.application.exceptions.application_exceptions import MasterNotFoundError
from src.application.services.masters.agreement_service import (
    AgreementRenewalInput,
    AgreementService,
    AgreementUpdateInput,
)
from src.application.services.masters.customer_service import (
    CustomerService,
    CustomerUpdateInput,
)
from src.application.services.masters.entity_service import (
    EntityService,
    EntityUpdateInput,
)
from src.application.services.masters.invoice_service import (
    InvoiceService,
    InvoiceUpdateInput,
    SapPaymentInput,
)
from src.application.services.masters.mapping_service import (
    MappingService,
    MappingUpdateInput,
)
from src.application.services.masters.product_service import (
    ProductDetailUpdateInput,
    ProductMasterUpdateInput,
    ProductService,
)
from src.application.services.masters.vendor_service import (
    VendorService,
    VendorUpdateInput,
)
from src.domain.entities.user import User


# ─── In-memory recording fakes (duck-typed against the repository ports) ───
#
# Every fake starts empty, so any UUID is "unknown". Each write method appends
# to ``writes`` so the test can assert a rejected operation modified no record.


class _RecordingFake:
    """Base fake that records every mutating call for write-free assertions."""

    def __init__(self) -> None:
        self.writes: list[str] = []


class FakeEntityRepository(_RecordingFake):
    async def get_by_id(self, entity_id: UUID):
        return None

    async def create(self, entity):  # pragma: no cover - must not be reached
        self.writes.append("create")
        return entity

    async def update(self, entity):  # pragma: no cover - must not be reached
        self.writes.append("update")
        return entity

    async def exists_by_name(self, name, exclude_id=None):
        return False

    async def exists_by_company_code(self, code, exclude_id=None):
        return False


class FakeUserRepository(_RecordingFake):
    async def get_by_id(self, user_id: UUID):
        return None

    async def update(self, user):  # pragma: no cover - must not be reached
        self.writes.append("update")
        return user


class FakeVendorRepository(_RecordingFake):
    async def get_by_id(self, vendor_id: UUID):
        return None

    async def update(self, vendor):  # pragma: no cover - must not be reached
        self.writes.append("update")
        return vendor

    async def get_by_code(self, code):
        return None

    async def get_by_email(self, email):
        return None

    async def exists_by_code(self, code):
        return False

    async def exists_by_email(self, email):
        return False


class FakeCustomerRepository(_RecordingFake):
    async def get_by_id(self, customer_id: UUID):
        return None

    async def update(self, customer):  # pragma: no cover - must not be reached
        self.writes.append("update")
        return customer

    async def delete(self, customer_id: UUID):  # pragma: no cover
        self.writes.append("delete")

    async def is_referenced_by_active_mapping(self, customer_id: UUID):
        return False

    async def is_referenced_by_invoice_header(self, customer_id: UUID):
        return False


class FakeProductRepository(_RecordingFake):
    async def get_master_by_id(self, master_id: UUID):
        return None

    async def get_detail_by_id(self, detail_id: UUID):
        return None

    async def update_master(self, master):  # pragma: no cover
        self.writes.append("update_master")
        return master

    async def update_detail(self, detail):  # pragma: no cover
        self.writes.append("update_detail")
        return detail

    async def delete_master(self, master_id: UUID):  # pragma: no cover
        self.writes.append("delete_master")

    async def delete_detail(self, detail_id: UUID):  # pragma: no cover
        self.writes.append("delete_detail")

    async def has_details(self, master_id: UUID):
        return False

    async def get_product_name_for_detail(self, detail_id: UUID):
        return None


class FakeAgreementRepository(_RecordingFake):
    async def get_by_id(self, agreement_id: UUID):
        return None

    async def update(self, agreement):  # pragma: no cover
        self.writes.append("update")
        return agreement

    async def create(self, agreement):  # pragma: no cover
        self.writes.append("create")
        return agreement

    async def delete(self, agreement_id: UUID):  # pragma: no cover
        self.writes.append("delete")


class FakeMappingRepository(_RecordingFake):
    async def get_by_id(self, mapping_id: UUID):
        return None

    async def update(self, mapping):  # pragma: no cover
        self.writes.append("update")
        return mapping

    async def delete(self, mapping_id: UUID):  # pragma: no cover
        self.writes.append("delete")


class FakeInvoiceRepository(_RecordingFake):
    async def get_by_id(self, invoice_id: UUID):
        return None

    async def get_by_invoice_number(self, invoice_number: str):
        return None

    async def exists_by_id(self, invoice_id: UUID):
        return False

    async def update(self, header):  # pragma: no cover
        self.writes.append("update")
        return header

    async def delete(self, invoice_id: UUID):  # pragma: no cover
        self.writes.append("delete")


def _actor() -> User:
    return User(id=uuid4(), username="admin", is_active=True)


async def _exercise_unknown_id(unknown_id: UUID) -> None:
    """Run every applicable not-found operation against empty stores.

    Asserts each operation raises ``MasterNotFoundError`` and that no fake
    repository recorded a write (the rejected operation modified no record).
    """
    actor = _actor()

    # ─── Entity (Req 1.7): read + update ───
    entity_repo = FakeEntityRepository()
    entity_service = EntityService(session=None, entity_repo=entity_repo)  # type: ignore[arg-type]
    with pytest.raises(MasterNotFoundError):
        await entity_service.get_entity(unknown_id)
    with pytest.raises(MasterNotFoundError):
        await entity_service.update_entity(unknown_id, EntityUpdateInput(), actor)
    assert entity_repo.writes == []

    # ─── Vendor (Req 6.10 read/update, 7.1 deactivate) ───
    vendor_repo = FakeVendorRepository()
    user_repo = FakeUserRepository()
    vendor_service = VendorService(
        session=None,  # type: ignore[arg-type]
        vendor_repo=vendor_repo,  # type: ignore[arg-type]
        user_repo=user_repo,  # type: ignore[arg-type]
    )
    with pytest.raises(MasterNotFoundError):
        await vendor_service.get_vendor(unknown_id)
    with pytest.raises(MasterNotFoundError):
        await vendor_service.update_vendor(unknown_id, VendorUpdateInput(), actor)
    with pytest.raises(MasterNotFoundError):
        await vendor_service.deactivate_vendor(unknown_id, actor)
    assert vendor_repo.writes == []
    assert user_repo.writes == []

    # ─── Customer (Req 8.10): read + update + delete ───
    customer_repo = FakeCustomerRepository()
    customer_service = CustomerService(session=None, customer_repo=customer_repo)  # type: ignore[arg-type]
    with pytest.raises(MasterNotFoundError):
        await customer_service.get_customer(unknown_id)
    with pytest.raises(MasterNotFoundError):
        await customer_service.update_customer(
            unknown_id, CustomerUpdateInput(), actor
        )
    with pytest.raises(MasterNotFoundError):
        await customer_service.delete_customer(unknown_id, actor)
    assert customer_repo.writes == []

    # ─── Product Master (Req 9.6) + Product Detail (Req 10.8) ───
    product_repo = FakeProductRepository()
    product_service = ProductService(session=None, product_repo=product_repo)  # type: ignore[arg-type]
    with pytest.raises(MasterNotFoundError):
        await product_service.get_master(unknown_id)
    with pytest.raises(MasterNotFoundError):
        await product_service.update_master(
            unknown_id, ProductMasterUpdateInput(), actor
        )
    with pytest.raises(MasterNotFoundError):
        await product_service.delete_master(unknown_id, actor)
    with pytest.raises(MasterNotFoundError):
        await product_service.get_detail(unknown_id)
    with pytest.raises(MasterNotFoundError):
        await product_service.update_detail(
            unknown_id, ProductDetailUpdateInput(), actor
        )
    with pytest.raises(MasterNotFoundError):
        await product_service.delete_detail(unknown_id, actor)
    with pytest.raises(MasterNotFoundError):
        await product_service.get_product_name(unknown_id)
    assert product_repo.writes == []

    # ─── Agreement (Req 11.11 read/update/delete, 13.6 renew) ───
    agreement_repo = FakeAgreementRepository()
    agreement_service = AgreementService(
        session=None,  # type: ignore[arg-type]
        agreement_repo=agreement_repo,  # type: ignore[arg-type]
        vendor_repo=FakeVendorRepository(),  # type: ignore[arg-type]
        product_repo=FakeProductRepository(),  # type: ignore[arg-type]
    )
    with pytest.raises(MasterNotFoundError):
        await agreement_service.get_agreement(unknown_id)
    with pytest.raises(MasterNotFoundError):
        await agreement_service.update_agreement(
            unknown_id, AgreementUpdateInput(), actor
        )
    with pytest.raises(MasterNotFoundError):
        await agreement_service.delete_agreement(unknown_id, actor)
    with pytest.raises(MasterNotFoundError):
        await agreement_service.renew_agreement(
            unknown_id,
            AgreementRenewalInput(from_date=None, to_date=None),
            actor,
        )
    assert agreement_repo.writes == []

    # ─── Mapping (Req 14.9): read + update + delete ───
    mapping_repo = FakeMappingRepository()
    mapping_service = MappingService(
        session=None,  # type: ignore[arg-type]
        mapping_repo=mapping_repo,  # type: ignore[arg-type]
        vendor_repo=FakeVendorRepository(),  # type: ignore[arg-type]
        customer_repo=FakeCustomerRepository(),  # type: ignore[arg-type]
    )
    with pytest.raises(MasterNotFoundError):
        await mapping_service.get_mapping(unknown_id)
    with pytest.raises(MasterNotFoundError):
        await mapping_service.update_mapping(
            unknown_id, MappingUpdateInput(), actor
        )
    with pytest.raises(MasterNotFoundError):
        await mapping_service.delete_mapping(unknown_id, actor)
    assert mapping_repo.writes == []

    # ─── Invoice (Req 17.4): read + update + delete + SAP payment + settle ───
    invoice_repo = FakeInvoiceRepository()
    invoice_service = InvoiceService(
        session=None,  # type: ignore[arg-type]
        invoice_repo=invoice_repo,  # type: ignore[arg-type]
        vendor_repo=FakeVendorRepository(),  # type: ignore[arg-type]
        customer_repo=FakeCustomerRepository(),  # type: ignore[arg-type]
        product_repo=FakeProductRepository(),  # type: ignore[arg-type]
        agreement_repo=FakeAgreementRepository(),  # type: ignore[arg-type]
    )
    with pytest.raises(MasterNotFoundError):
        await invoice_service.get_invoice(unknown_id)
    with pytest.raises(MasterNotFoundError):
        await invoice_service.update_invoice(
            unknown_id, InvoiceUpdateInput(due_date=date(2024, 1, 1)), actor
        )
    with pytest.raises(MasterNotFoundError):
        await invoice_service.delete_invoice(unknown_id, actor)
    with pytest.raises(MasterNotFoundError):
        await invoice_service.record_sap_payment(
            SapPaymentInput(
                invoice_id=unknown_id,
                payment_clearing_date=date(2024, 1, 1),
                sap_clearing_document_no="SAP-1",
            ),
            actor,
        )
    with pytest.raises(MasterNotFoundError):
        await invoice_service.mark_settled(unknown_id, actor)
    assert invoice_repo.writes == []


@settings(max_examples=20)
@given(unknown_id=st.uuids())
def test_unknown_identifier_yields_not_found_across_masters(
    unknown_id: UUID,
) -> None:
    """Any unknown UUID yields not-found and no write across every master.

    Exercises Entity, Vendor, Customer, Product Master, Product Detail,
    Agreement, Mapping, and Invoice (Req 1.7, 6.10, 7.1, 8.10, 9.6, 10.8,
    11.11, 13.6, 14.9, 17.4).
    """
    asyncio.run(_exercise_unknown_id(unknown_id))

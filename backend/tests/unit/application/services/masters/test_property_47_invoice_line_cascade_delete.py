# Feature: lacm-masters, Property 47: Deleting an invoice header removes its lines.
"""Property-based test for Invoice Header → Invoice Line cascade delete.

Property 47: Deleting an invoice header removes its lines.

**Validates: Requirements 16.9**

For any collection of persisted Invoices (each header owning one or more lines),
deleting one header removes that header *and every one of its lines*, while every
other header and all of its lines remain intact. This models the production
``ON DELETE CASCADE`` foreign key that ``InvoiceService.delete_invoice`` relies
on to clear the lines belonging to a deleted header.

The service is exercised end-to-end through a real in-memory stand-in (not a
mock): a dict-backed Invoice repository that stores headers and lines in
*separate* maps and, on ``delete(header_id)``, removes the header together with
all lines whose ``invoice_header_id`` matches — faithfully reproducing the
cascade so the test observes the cascade rather than a coincidence of lines
living on the header object. A fresh repository is built per generated example
so no state leaks between examples; the async service is driven with
``asyncio.run``.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal
from datetime import date
from uuid import UUID, uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from src.application.services.masters.invoice_service import (
    InvoiceCreateInput,
    InvoiceLineInput,
    InvoiceService,
)
from src.domain.entities.masters.invoice import (
    InvoiceHeaderEntity,
    InvoiceLineEntity,
)
from src.domain.entities.user import User
from src.domain.enums.masters import InvoiceStatus


# ─── In-memory repositories (real implementations, not mocks) ───


class _InMemoryInvoiceRepository:
    """Dict-backed Invoice store modelling ``ON DELETE CASCADE``.

    Headers and lines live in separate maps so deletion of a header must
    *actively* remove the matching lines (mirroring the DB cascade) for the
    lines to disappear — making the cascade observable rather than implicit.
    """

    def __init__(self) -> None:
        self._headers: dict[UUID, InvoiceHeaderEntity] = {}
        self._lines: dict[UUID, InvoiceLineEntity] = {}

    async def create(
        self, header: InvoiceHeaderEntity, lines: list[InvoiceLineEntity]
    ) -> InvoiceHeaderEntity:
        header.lines = list(lines)
        self._headers[header.id] = header
        for line in lines:
            self._lines[line.id] = line
        return header

    async def get_by_id(self, header_id: UUID) -> InvoiceHeaderEntity | None:
        return self._headers.get(header_id)

    async def exists_by_id(self, header_id: UUID) -> bool:
        return header_id in self._headers

    async def exists_by_invoice_number(
        self, invoice_number: str, exclude_id: UUID | None = None
    ) -> bool:
        return any(
            h.invoice_number == invoice_number and h.id != exclude_id
            for h in self._headers.values()
        )

    async def get_lines_by_ids(
        self, line_ids: list[UUID]
    ) -> list[InvoiceLineEntity]:
        wanted = set(line_ids)
        return [
            line for lid, line in self._lines.items() if lid in wanted
        ]

    async def delete(self, header_id: UUID) -> None:
        # ON DELETE CASCADE: removing the header removes all of its lines.
        self._headers.pop(header_id, None)
        orphaned = [
            lid
            for lid, line in self._lines.items()
            if line.invoice_header_id == header_id
        ]
        for lid in orphaned:
            self._lines.pop(lid, None)

    async def count(self) -> int:
        return len(self._headers)


class _InMemoryVendorRepository:
    def __init__(self) -> None:
        self.existing: set[UUID] = set()

    async def get_by_id(self, vendor_id: UUID):
        return object() if vendor_id in self.existing else None


class _InMemoryCustomerRepository:
    def __init__(self) -> None:
        self.existing: set[UUID] = set()

    async def get_by_id(self, customer_id: UUID):
        return object() if customer_id in self.existing else None


class _InMemoryProductRepository:
    def __init__(self) -> None:
        self.existing: set[UUID] = set()

    async def get_detail_by_id(self, detail_id: UUID):
        return object() if detail_id in self.existing else None


class _NoAgreementRepository:
    """No applicable agreements — Due Date resolution is irrelevant here."""

    async def find_overlapping_active(self, *args, **kwargs):
        return []


# ─── World built per generated example ───


def _build_service() -> tuple[
    InvoiceService, _InMemoryInvoiceRepository, UUID, UUID, UUID
]:
    """Build a service whose repos know one vendor/customer/product detail."""
    invoice_repo = _InMemoryInvoiceRepository()
    vendor_repo = _InMemoryVendorRepository()
    customer_repo = _InMemoryCustomerRepository()
    product_repo = _InMemoryProductRepository()

    known_vendor = uuid4()
    known_customer = uuid4()
    known_product = uuid4()
    vendor_repo.existing.add(known_vendor)
    customer_repo.existing.add(known_customer)
    product_repo.existing.add(known_product)

    service = InvoiceService(
        session=None,  # type: ignore[arg-type]
        invoice_repo=invoice_repo,  # type: ignore[arg-type]
        vendor_repo=vendor_repo,  # type: ignore[arg-type]
        customer_repo=customer_repo,  # type: ignore[arg-type]
        product_repo=product_repo,  # type: ignore[arg-type]
        agreement_repo=_NoAgreementRepository(),  # type: ignore[arg-type]
    )
    return service, invoice_repo, known_vendor, known_customer, known_product


# ─── Generators ───


@dataclass(frozen=True)
class _Scenario:
    """A batch of invoices (by their line counts) plus which one to delete."""

    line_counts: tuple[int, ...]
    delete_index: int


@st.composite
def _scenarios(draw: st.DrawFn) -> _Scenario:
    line_counts = tuple(
        draw(st.lists(st.integers(min_value=1, max_value=4), min_size=1, max_size=6))
    )
    delete_index = draw(st.integers(min_value=0, max_value=len(line_counts) - 1))
    return _Scenario(line_counts=line_counts, delete_index=delete_index)


@settings(max_examples=20, deadline=None)
@given(scenario=_scenarios())
def test_deleting_invoice_header_removes_its_lines(scenario: _Scenario) -> None:
    """Deleting a header removes its lines; sibling headers + lines untouched."""
    actor = User(id=uuid4(), username="admin", is_active=True)

    async def run():
        service, repo, vendor, customer, product = _build_service()

        # Persist every invoice, tracking each header's line ids.
        header_ids: list[UUID] = []
        line_ids_by_header: dict[UUID, list[UUID]] = {}
        for i, n_lines in enumerate(scenario.line_counts):
            created = await service.create_invoice(
                InvoiceCreateInput(
                    invoice_number=f"INV-{i}-{uuid4()}",
                    invoice_date=date(2024, 1, 10),
                    vendor_id=vendor,
                    customer_id=customer,
                    bill_amount_excl_gst=Decimal("100.00"),
                    lines=[
                        InvoiceLineInput(product_master_id=product)
                        for _ in range(n_lines)
                    ],
                ),
                actor,
            )
            header_ids.append(created.id)
            line_ids_by_header[created.id] = [ln.id for ln in created.lines]

        target = header_ids[scenario.delete_index]
        target_line_ids = line_ids_by_header[target]
        survivor_ids = [h for h in header_ids if h != target]
        survivor_line_ids = [
            lid for h in survivor_ids for lid in line_ids_by_header[h]
        ]
        count_before = await repo.count()

        await service.delete_invoice(target, actor)

        target_header = await repo.get_by_id(target)
        remaining_target_lines = await repo.get_lines_by_ids(target_line_ids)
        surviving_headers = [
            await repo.get_by_id(h) for h in survivor_ids
        ]
        surviving_lines = await repo.get_lines_by_ids(survivor_line_ids)
        count_after = await repo.count()

        return (
            target_header,
            remaining_target_lines,
            surviving_headers,
            surviving_lines,
            survivor_line_ids,
            count_before,
            count_after,
        )

    (
        target_header,
        remaining_target_lines,
        surviving_headers,
        surviving_lines,
        survivor_line_ids,
        count_before,
        count_after,
    ) = asyncio.run(run())

    # The deleted header is gone and every one of its lines was removed.
    assert target_header is None
    assert remaining_target_lines == []

    # Exactly one header was removed.
    assert count_after == count_before - 1

    # Every sibling header and all of its lines remain intact.
    assert all(h is not None for h in surviving_headers)
    assert {ln.id for ln in surviving_lines} == set(survivor_line_ids)

"""
In-memory fakes for the six master-data repository ports.

Mirrors `workflow_fakes.py`'s approach: the application services are written
against repository interfaces, never SQLAlchemy, so their business rules —
uniqueness checks, dependent-record delete guards, partial-update field
handling, jurisdiction validation — can be pinned down without a database.

Reads return deep copies, matching a detached ORM row: a caller mutating a
returned entity changes nothing until it calls `update`. Sharing objects by
reference would let a missing `update` call slip through unnoticed, the same
reasoning `workflow_fakes.py` documents for the workflow engine's fakes.

`has_dependents` is a settable in-memory set on each fake rather than derived
from cross-repository joins (the real adapters query sibling tables directly);
tests opt a row into "has dependents" explicitly, which keeps the fake honest
about what it is deciding versus what a test is asserting.

Ids are database-assigned bigints now, so an entity arrives at `create` with the
sentinel id 0. Each fake calls `_next_fake_id()` to stamp a distinct id, exactly
as the real database autoincrement would, so a test that creates several rows
gets distinct keys instead of colliding at 0.
"""

import copy

from src.domain.entities.category_of_law import CategoryOfLaw
from src.domain.entities.country import Country
from src.domain.entities.legislation import Legislation
from src.domain.entities.rule import Rule
from src.domain.entities.state import State
from src.domain.entities.task_type import TaskType
from src.domain.repositories.category_of_law_repository import ICategoryOfLawRepository
from src.domain.repositories.country_repository import ICountryRepository
from src.domain.repositories.legislation_repository import ILegislationRepository
from src.domain.repositories.rule_repository import IRuleRepository
from src.domain.repositories.state_repository import IStateRepository
from src.domain.repositories.task_type_repository import ITaskTypeRepository

_fake_id_seq = 0


def _next_fake_id() -> int:
    """A distinct non-zero int id, standing in for a DB-assigned bigint."""
    global _fake_id_seq
    _fake_id_seq += 1
    return _fake_id_seq


class FakeCountryRepository(ICountryRepository):
    """In-memory stand-in for `ICountryRepository`."""

    def __init__(self) -> None:
        self.rows: dict[int, Country] = {}
        #: Country ids that should report as referenced by a state/legislation/rule.
        self.dependents: set[int] = set()

    async def get_by_id(self, entity_id: int) -> Country | None:
        return copy.deepcopy(self.rows.get(entity_id))

    async def get_by_code(self, code: str) -> Country | None:
        for row in self.rows.values():
            if row.code == code:
                return copy.deepcopy(row)
        return None

    async def create(self, entity: Country) -> Country:
        if entity.id == 0:
            entity.id = _next_fake_id()
        self.rows[entity.id] = copy.deepcopy(entity)
        return copy.deepcopy(entity)

    async def update(self, entity: Country) -> Country:
        if entity.id not in self.rows:
            raise ValueError(f"Country with id {entity.id} not found")
        self.rows[entity.id] = copy.deepcopy(entity)
        return copy.deepcopy(entity)

    async def delete(self, entity_id: int) -> None:
        self.rows.pop(entity_id, None)

    async def list_all(
        self,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        is_active: bool | None = None,
    ) -> list[Country]:
        rows = self._filtered(search, is_active)
        return [copy.deepcopy(r) for r in rows[skip : skip + limit]]

    async def count(self, search: str | None = None, is_active: bool | None = None) -> int:
        return len(self._filtered(search, is_active))

    async def exists_by_code(self, code: str, exclude_id: int | None = None) -> bool:
        return any(r.code == code and r.id != exclude_id for r in self.rows.values())

    async def exists_by_name(self, name: str, exclude_id: int | None = None) -> bool:
        return any(
            r.name.lower() == name.lower() and r.id != exclude_id
            for r in self.rows.values()
        )

    async def has_dependents(self, country_id: int) -> bool:
        return country_id in self.dependents

    def _filtered(self, search: str | None, is_active: bool | None) -> list[Country]:
        rows = sorted(self.rows.values(), key=lambda r: r.name)
        if search:
            needle = search.lower()
            rows = [r for r in rows if needle in r.code.lower() or needle in r.name.lower()]
        if is_active is not None:
            rows = [r for r in rows if r.is_active is is_active]
        return rows


class FakeStateRepository(IStateRepository):
    """In-memory stand-in for `IStateRepository`."""

    def __init__(self) -> None:
        self.rows: dict[int, State] = {}
        self.dependents: set[int] = set()

    async def get_by_id(self, entity_id: int) -> State | None:
        return copy.deepcopy(self.rows.get(entity_id))

    async def get_by_code(self, code: str) -> State | None:
        for row in self.rows.values():
            if row.code == code:
                return copy.deepcopy(row)
        return None

    async def create(self, entity: State) -> State:
        if entity.id == 0:
            entity.id = _next_fake_id()
        self.rows[entity.id] = copy.deepcopy(entity)
        return copy.deepcopy(entity)

    async def update(self, entity: State) -> State:
        if entity.id not in self.rows:
            raise ValueError(f"State with id {entity.id} not found")
        self.rows[entity.id] = copy.deepcopy(entity)
        return copy.deepcopy(entity)

    async def delete(self, entity_id: int) -> None:
        self.rows.pop(entity_id, None)

    async def list_all(
        self,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        is_active: bool | None = None,
        country_id: int | None = None,
    ) -> list[State]:
        rows = self._filtered(search, is_active, country_id)
        return [copy.deepcopy(r) for r in rows[skip : skip + limit]]

    async def count(
        self,
        search: str | None = None,
        is_active: bool | None = None,
        country_id: int | None = None,
    ) -> int:
        return len(self._filtered(search, is_active, country_id))

    async def exists_by_code(self, code: str, exclude_id: int | None = None) -> bool:
        return any(r.code == code and r.id != exclude_id for r in self.rows.values())

    async def exists_by_name(
        self, name: str, country_id: int, exclude_id: int | None = None
    ) -> bool:
        return any(
            r.name.lower() == name.lower() and r.country_id == country_id and r.id != exclude_id
            for r in self.rows.values()
        )

    async def has_dependents(self, state_id: int) -> bool:
        return state_id in self.dependents

    def _filtered(
        self, search: str | None, is_active: bool | None, country_id: int | None
    ) -> list[State]:
        rows = sorted(self.rows.values(), key=lambda r: r.name)
        if search:
            needle = search.lower()
            rows = [r for r in rows if needle in r.code.lower() or needle in r.name.lower()]
        if is_active is not None:
            rows = [r for r in rows if r.is_active is is_active]
        if country_id is not None:
            rows = [r for r in rows if r.country_id == country_id]
        return rows


class FakeCategoryOfLawRepository(ICategoryOfLawRepository):
    """In-memory stand-in for `ICategoryOfLawRepository`."""

    def __init__(self) -> None:
        self.rows: dict[int, CategoryOfLaw] = {}
        self.dependents: set[int] = set()

    async def get_by_id(self, entity_id: int) -> CategoryOfLaw | None:
        return copy.deepcopy(self.rows.get(entity_id))

    async def get_by_code(self, code: str) -> CategoryOfLaw | None:
        for row in self.rows.values():
            if row.code == code:
                return copy.deepcopy(row)
        return None

    async def create(self, entity: CategoryOfLaw) -> CategoryOfLaw:
        if entity.id == 0:
            entity.id = _next_fake_id()
        self.rows[entity.id] = copy.deepcopy(entity)
        return copy.deepcopy(entity)

    async def update(self, entity: CategoryOfLaw) -> CategoryOfLaw:
        if entity.id not in self.rows:
            raise ValueError(f"CategoryOfLaw with id {entity.id} not found")
        self.rows[entity.id] = copy.deepcopy(entity)
        return copy.deepcopy(entity)

    async def delete(self, entity_id: int) -> None:
        self.rows.pop(entity_id, None)

    async def list_all(
        self,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        is_active: bool | None = None,
        state_id: int | None = None,
    ) -> list[CategoryOfLaw]:
        rows = self._filtered(search, is_active, state_id)
        return [copy.deepcopy(r) for r in rows[skip : skip + limit]]

    async def count(
        self,
        search: str | None = None,
        is_active: bool | None = None,
        state_id: int | None = None,
    ) -> int:
        return len(self._filtered(search, is_active, state_id))

    async def exists_by_code(self, code: str, exclude_id: int | None = None) -> bool:
        return any(r.code == code and r.id != exclude_id for r in self.rows.values())

    async def exists_by_name(
        self, name: str, state_id: int | None, exclude_id: int | None = None
    ) -> bool:
        return any(
            r.name.lower() == name.lower() and r.state_id == state_id and r.id != exclude_id
            for r in self.rows.values()
        )

    async def has_dependents(self, category_of_law_id: int) -> bool:
        return category_of_law_id in self.dependents

    def _filtered(
        self, search: str | None, is_active: bool | None, state_id: int | None
    ) -> list[CategoryOfLaw]:
        rows = sorted(self.rows.values(), key=lambda r: r.name)
        if search:
            needle = search.lower()
            rows = [r for r in rows if needle in r.code.lower() or needle in r.name.lower()]
        if is_active is not None:
            rows = [r for r in rows if r.is_active is is_active]
        if state_id is not None:
            rows = [r for r in rows if r.state_id == state_id]
        return rows


class FakeLegislationRepository(ILegislationRepository):
    """In-memory stand-in for `ILegislationRepository`."""

    def __init__(self) -> None:
        self.rows: dict[int, Legislation] = {}
        self.dependents: set[int] = set()

    async def get_by_id(self, entity_id: int) -> Legislation | None:
        return copy.deepcopy(self.rows.get(entity_id))

    async def get_by_code(self, code: str) -> Legislation | None:
        for row in self.rows.values():
            if row.code == code:
                return copy.deepcopy(row)
        return None

    async def create(self, entity: Legislation) -> Legislation:
        if entity.id == 0:
            entity.id = _next_fake_id()
        self.rows[entity.id] = copy.deepcopy(entity)
        return copy.deepcopy(entity)

    async def update(self, entity: Legislation) -> Legislation:
        if entity.id not in self.rows:
            raise ValueError(f"Legislation with id {entity.id} not found")
        self.rows[entity.id] = copy.deepcopy(entity)
        return copy.deepcopy(entity)

    async def delete(self, entity_id: int) -> None:
        self.rows.pop(entity_id, None)

    async def list_all(
        self,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        is_active: bool | None = None,
        country_id: int | None = None,
        state_id: int | None = None,
        category_of_law_id: int | None = None,
    ) -> list[Legislation]:
        rows = self._filtered(search, is_active, country_id, state_id, category_of_law_id)
        return [copy.deepcopy(r) for r in rows[skip : skip + limit]]

    async def count(
        self,
        search: str | None = None,
        is_active: bool | None = None,
        country_id: int | None = None,
        state_id: int | None = None,
        category_of_law_id: int | None = None,
    ) -> int:
        return len(self._filtered(search, is_active, country_id, state_id, category_of_law_id))

    async def exists_by_code(self, code: str, exclude_id: int | None = None) -> bool:
        return any(r.code == code and r.id != exclude_id for r in self.rows.values())

    async def has_dependents(self, legislation_id: int) -> bool:
        return legislation_id in self.dependents

    def _filtered(
        self,
        search: str | None,
        is_active: bool | None,
        country_id: int | None,
        state_id: int | None,
        category_of_law_id: int | None,
    ) -> list[Legislation]:
        rows = sorted(self.rows.values(), key=lambda r: r.name)
        if search:
            needle = search.lower()
            rows = [r for r in rows if needle in r.code.lower() or needle in r.name.lower()]
        if is_active is not None:
            rows = [r for r in rows if r.is_active is is_active]
        if country_id is not None:
            rows = [r for r in rows if r.country_id == country_id]
        if state_id is not None:
            rows = [r for r in rows if r.state_id == state_id]
        if category_of_law_id is not None:
            rows = [r for r in rows if r.category_of_law_id == category_of_law_id]
        return rows


class FakeRuleRepository(IRuleRepository):
    """In-memory stand-in for `IRuleRepository`."""

    def __init__(self) -> None:
        self.rows: dict[int, Rule] = {}

    async def get_by_id(self, entity_id: int) -> Rule | None:
        return copy.deepcopy(self.rows.get(entity_id))

    async def get_by_code(self, code: str) -> Rule | None:
        for row in self.rows.values():
            if row.code == code:
                return copy.deepcopy(row)
        return None

    async def create(self, entity: Rule) -> Rule:
        if entity.id == 0:
            entity.id = _next_fake_id()
        self.rows[entity.id] = copy.deepcopy(entity)
        return copy.deepcopy(entity)

    async def update(self, entity: Rule) -> Rule:
        if entity.id not in self.rows:
            raise ValueError(f"Rule with id {entity.id} not found")
        self.rows[entity.id] = copy.deepcopy(entity)
        return copy.deepcopy(entity)

    async def delete(self, entity_id: int) -> None:
        self.rows.pop(entity_id, None)

    async def list_all(
        self,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        is_active: bool | None = None,
        country_id: int | None = None,
        state_id: int | None = None,
        legislation_id: int | None = None,
    ) -> list[Rule]:
        rows = self._filtered(search, is_active, country_id, state_id, legislation_id)
        return [copy.deepcopy(r) for r in rows[skip : skip + limit]]

    async def count(
        self,
        search: str | None = None,
        is_active: bool | None = None,
        country_id: int | None = None,
        state_id: int | None = None,
        legislation_id: int | None = None,
    ) -> int:
        return len(self._filtered(search, is_active, country_id, state_id, legislation_id))

    async def exists_by_code(self, code: str, exclude_id: int | None = None) -> bool:
        return any(r.code == code and r.id != exclude_id for r in self.rows.values())

    def _filtered(
        self,
        search: str | None,
        is_active: bool | None,
        country_id: int | None,
        state_id: int | None,
        legislation_id: int | None,
    ) -> list[Rule]:
        rows = sorted(self.rows.values(), key=lambda r: r.name)
        if search:
            needle = search.lower()
            rows = [r for r in rows if needle in r.code.lower() or needle in r.name.lower()]
        if is_active is not None:
            rows = [r for r in rows if r.is_active is is_active]
        if country_id is not None:
            rows = [r for r in rows if r.country_id == country_id]
        if state_id is not None:
            rows = [r for r in rows if r.state_id == state_id]
        if legislation_id is not None:
            rows = [r for r in rows if r.legislation_id == legislation_id]
        return rows


class FakeTaskTypeRepository(ITaskTypeRepository):
    """In-memory stand-in for `ITaskTypeRepository`."""

    def __init__(self) -> None:
        self.rows: dict[int, TaskType] = {}

    async def get_by_id(self, entity_id: int) -> TaskType | None:
        return copy.deepcopy(self.rows.get(entity_id))

    async def get_by_code(self, code: str) -> TaskType | None:
        for row in self.rows.values():
            if row.code == code:
                return copy.deepcopy(row)
        return None

    async def create(self, entity: TaskType) -> TaskType:
        if entity.id == 0:
            entity.id = _next_fake_id()
        self.rows[entity.id] = copy.deepcopy(entity)
        return copy.deepcopy(entity)

    async def update(self, entity: TaskType) -> TaskType:
        if entity.id not in self.rows:
            raise ValueError(f"TaskType with id {entity.id} not found")
        self.rows[entity.id] = copy.deepcopy(entity)
        return copy.deepcopy(entity)

    async def delete(self, entity_id: int) -> None:
        self.rows.pop(entity_id, None)

    async def list_all(
        self,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        is_active: bool | None = None,
    ) -> list[TaskType]:
        rows = self._filtered(search, is_active)
        return [copy.deepcopy(r) for r in rows[skip : skip + limit]]

    async def count(self, search: str | None = None, is_active: bool | None = None) -> int:
        return len(self._filtered(search, is_active))

    async def exists_by_code(self, code: str, exclude_id: int | None = None) -> bool:
        return any(r.code == code and r.id != exclude_id for r in self.rows.values())

    async def exists_by_name(self, name: str, exclude_id: int | None = None) -> bool:
        return any(
            r.name.lower() == name.lower() and r.id != exclude_id
            for r in self.rows.values()
        )

    def _filtered(self, search: str | None, is_active: bool | None) -> list[TaskType]:
        rows = sorted(self.rows.values(), key=lambda r: r.name)
        if search:
            needle = search.lower()
            rows = [r for r in rows if needle in r.code.lower() or needle in r.name.lower()]
        if is_active is not None:
            rows = [r for r in rows if r.is_active is is_active]
        return rows

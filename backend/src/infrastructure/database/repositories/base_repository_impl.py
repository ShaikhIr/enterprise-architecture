"""
Base repository implementation with common CRUD operations.

Holds only the mechanics that are byte-identical for every code-keyed master:
session ownership, primary-key lookup, business-code lookup, existence checks
and delete.

Deliberately does NOT generalise mapping or writes. `_to_entity`, `create`,
`update`, `list_all`/`count` and the query filters stay in each concrete
repository, so opening `country_repository_impl.py` still shows you exactly
which columns a Country has. An earlier draft drove those from `_fields`
tuples plus getattr/setattr loops; it was shorter but you could no longer read
an entity's shape from its own repository, so it was dropped.

Repositories flush but never commit — the request-scoped session owns the
transaction boundary (see `get_db_session`).
"""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.base_entity import BaseEntity
from src.infrastructure.database.models.base_model import BaseModel

TEntity = TypeVar("TEntity", bound=BaseEntity)
TModel = TypeVar("TModel", bound=BaseModel)


class SqlAlchemyRepository(ABC, Generic[TEntity, TModel]):
    """
    Shared async SQLAlchemy mechanics for a single code-keyed aggregate.

    Subclasses declare two class attributes and one mapper:

        _model       = CountryModel
        _code_column = CountryModel.code

        @staticmethod
        def _to_entity(model: CountryModel) -> Country: ...
    """

    #: ORM model this repository persists.
    _model: type[TModel]

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ─── Hooks implemented by each concrete repository ───

    @staticmethod
    @abstractmethod
    def _to_entity(model: TModel) -> TEntity:
        """Map an ORM model to its domain entity."""
        ...

    @staticmethod
    @abstractmethod
    def _code_equals(code: str) -> ColumnElement[bool]:
        """
        Predicate matching the unique business code, e.g.::

            return CountryModel.code == code

        Built by the subclass rather than from a shared column attribute: mypy
        resolves ``==`` on a declared attribute type to ``object.__eq__`` and
        loses the SQL expression, whereas a comparison written against the
        concrete model is typed correctly.
        """
        ...

    # ─── Reads ───

    async def get_by_id(self, entity_id: int) -> TEntity | None:
        """Retrieve a single record by primary key."""
        model = await self._get_model(entity_id)
        return self._to_entity(model) if model else None

    async def get_by_code(self, code: str) -> TEntity | None:
        """Retrieve a single record by its unique business code."""
        stmt = select(self._model).where(self._code_equals(code))
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def exists_by_code(self, code: str, exclude_id: int | None = None) -> bool:
        """Check whether a business code is taken, optionally ignoring one row."""
        stmt = select(self._model.id).where(self._code_equals(code))
        if exclude_id is not None:
            stmt = stmt.where(self._model.id != exclude_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    # ─── Writes ───

    async def delete(self, entity_id: int) -> None:
        """Delete a record by primary key. Silent when already gone."""
        model = await self._get_model(entity_id)
        if model:
            await self._session.delete(model)
            await self._session.flush()

    # ─── Internals for subclasses ───

    async def _get_model(self, entity_id: int) -> TModel | None:
        """Load a row by primary key, or None."""
        stmt = select(self._model).where(self._model.id == entity_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def _require_model(self, entity_id: int) -> TModel:
        """
        Load a row by primary key for update.

        Raises:
            ValueError: If the row no longer exists.
        """
        model = await self._get_model(entity_id)
        if model is None:
            raise ValueError(f"{self._model.__name__} with id {entity_id} not found")
        return model

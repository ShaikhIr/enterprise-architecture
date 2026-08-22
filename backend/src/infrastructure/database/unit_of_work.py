"""
Unit of Work pattern - manages transaction boundaries.

Deliberately thin. It does NOT aggregate repositories: services take the
specific ports they need, and grouping every repository behind one object would
hide those dependencies. What this owns is the *transaction boundary*, which was
the one thing the codebase had no shared answer for.

Two ways to use it:

1. Owning the session — for scripts, Celery tasks, and anything outside a
   request, where `get_db_session` does not apply::

       async with UnitOfWork() as uow:
           repo = uow.repository(CountryRepositoryImpl)
           await repo.create(country)
           await uow.commit()          # explicit; nothing is committed for you

2. Attached to an existing session — for request handlers that need savepoints
   but must leave the commit to `get_db_session`::

       uow = UnitOfWork.from_session(session)
       for row in rows:
           try:
               async with uow.savepoint():
                   ...write row...
           except IntegrityError:
               errors.append(row)      # this row only is rolled back

Savepoints are the reason this exists: without them, a failed write leaves the
session unusable, so a loop that catches per-row errors and continues cannot
work — every later row fails too.
"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from types import TracebackType
from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.infrastructure.database.session import async_session_factory

TRepository = TypeVar("TRepository")


class UnitOfWork:
    """Owns a transaction boundary and hands out savepoints within it."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] = async_session_factory,
    ) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self._owns_session = True

    # ─── Construction ───

    @classmethod
    def from_session(cls, session: AsyncSession) -> "UnitOfWork":
        """
        Wrap a session owned by someone else (typically `get_db_session`).

        The caller keeps responsibility for commit and close; this instance only
        provides savepoints and repository construction.
        """
        uow = cls()
        uow._session = session
        uow._owns_session = False
        return uow

    # ─── Context management ───

    async def __aenter__(self) -> "UnitOfWork":
        if self._session is None:
            self._session = self._session_factory()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if not self._owns_session or self._session is None:
            return
        try:
            # Nothing is committed implicitly: an un-committed block rolls back,
            # so forgetting `await uow.commit()` cannot silently persist writes.
            if exc_type is not None:
                await self._session.rollback()
        finally:
            await self._session.close()
            self._session = None

    # ─── Access ───

    @property
    def session(self) -> AsyncSession:
        """The active session. Raises if used outside `async with`."""
        if self._session is None:
            raise RuntimeError(
                "UnitOfWork has no active session — use `async with UnitOfWork()` "
                "or construct it with UnitOfWork.from_session(session)."
            )
        return self._session

    def repository(
        self, repository_cls: Callable[[AsyncSession], TRepository]
    ) -> TRepository:
        """Build a repository bound to this transaction's session."""
        return repository_cls(self.session)

    # ─── Transaction control ───

    async def commit(self) -> None:
        """Make this transaction's work permanent."""
        await self.session.commit()

    async def rollback(self) -> None:
        """Discard everything done in this transaction."""
        await self.session.rollback()

    async def flush(self) -> None:
        """Send pending changes to the database without committing."""
        await self.session.flush()

    @asynccontextmanager
    async def savepoint(self) -> AsyncIterator[None]:
        """
        Run a block inside a SAVEPOINT.

        On success the savepoint is released; on failure only that block is
        rolled back and the surrounding transaction stays usable, so the caller
        can catch the error and carry on with the next item. The exception is
        re-raised for the caller to handle.
        """
        async with self.session.begin_nested():
            yield

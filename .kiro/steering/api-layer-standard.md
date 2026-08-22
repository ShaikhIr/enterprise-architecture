---
inclusion: always
---

# API Layer Standard — Mandatory Flow

Every API endpoint MUST follow this 4-layer architecture. No exceptions.

This file is loaded on every request (`inclusion: always`) — it is not something to
recall from memory of an earlier session, it is live context right now. Mechanically
enforced by `backend/tests/unit/test_architecture.py`, which fails `make check` (not
just review) on a layering violation.

## Flow

```
Controller → Service → Repository Interface → Repository Implementation
```

## Layer Responsibilities

### 1. Controller (Thin — API Layer)

**Location:** `src/api/v1/endpoints/<module>/`

```python
@router.get("/items")
async def list_items(
    skip: int = Query(default=0),
    service: ItemService = Depends(_get_item_service),
):
    return await service.list_items(skip=skip)
```

**Rules:**
- Parse HTTP (query params, path params, request body)
- Validate via Pydantic schemas (automatic)
- Map business errors to HTTP status codes (`ValueError → 404/409`)
- Delegate ALL logic to the Service layer
- NEVER import ORM models or SQLAlchemy — this includes `AsyncSession` itself. A route
  function or its private helper functions taking `session: AsyncSession = Depends(get_db_session)`
  is a violation even if the session is only used to build a `PermissionManager` or
  `AuditService` inline — those already have (or must get) a `Depends()` factory of their
  own in `dependencies.py` (e.g. `get_permission_resolver`) that returns a domain-layer
  port. Depend on the port, not the session.
- NEVER write SQL or business rules
- NEVER construct a repository or infrastructure adapter directly (`UserRepositoryImpl(session)`,
  `PermissionManager(session)`, `AuditService(session)`) inside a route body. Take it as a
  parameter, injected via a `Depends()` factory in `dependencies.py`.
- Max 5-10 lines per endpoint

---

### 2. Service (Business Logic — Application Layer)

**Location:** `src/application/services/<service_name>.py`

```python
class ItemService:
    def __init__(self, item_repo: IItemRepository) -> None:
        self._repo = item_repo

    async def create_item(self, request: CreateItemRequest, actor: User) -> ItemResponse:
        if await self._repo.exists_by_code(request.code):
            raise ValueError(f"Item '{request.code}' already exists")
        item = Item(id=uuid4(), ...)
        created = await self._repo.create(item)
        return self._to_response(created)
```

**Rules:**
- Contains ALL business logic and orchestration
- Calls repository methods for data access — that is the ONLY route to the database
- Takes repository/port interfaces in its constructor, never `AsyncSession`. There is no
  "complex aggregation query" exception — if a repository method doesn't exist yet for the
  query the service needs, add the method to the repository interface and implementation,
  then call it. A service that imports `sqlalchemy` or `AsyncSession` fails
  `test_application_does_not_import_infrastructure_or_orm` in `test_architecture.py`.
- If an endpoint genuinely needs bulk/multi-statement writes with per-row failure isolation
  (large imports, batch upserts), the pattern is a dedicated port + adapter — see
  `IEmployeeImportWriter` (`src/application/ports/employee_import_writer.py`) and its
  `EmployeeImportWriterImpl` implementation — not a session parameter on the service.
- Raises `ValueError` for business rule violations
- Returns Pydantic response DTOs (not ORM models)
- No HTTP concepts (no Request, no HTTPException)
- Concrete class (no interface needed — only one implementation)

---

### Domain entities inherit `BaseEntity`; ORM models inherit `BaseModel`

Every persisted domain entity is a `@dataclass` inheriting
`src.domain.entities.base_entity.BaseEntity`, which supplies `id`, `created_by`,
`created_date`, `modified_by`, `modified_date`, and `mark_modified()`. Every SQLAlchemy
ORM model inheriting `src.infrastructure.database.models.base_model.BaseModel` gets the
matching audit columns for free via `AuditMixin`, auto-populated on insert/update.

```python
@dataclass(kw_only=True)
class Item(BaseEntity):
    code: str = field(default="")
    name: str = field(default="")

class ItemModel(BaseModel):
    __tablename__ = "items"
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
```

Exceptions, and only these: pure value objects / filter or DTO dataclasses that are never
persisted and have no identity of their own skip `BaseEntity` because they aren't entities
(e.g. a `*ListParams` filter object passed into a repository's list query). `AuditLog`
deliberately does not inherit `BaseEntity` — it is append-only and `BaseEntity`'s
`modified_by`/`modified_date` would imply a mutability that must not exist for an audit row.
Do not invent further exceptions without the same kind of justification.

### Repository interfaces inherit `IRepository[TEntity]` where the shape fits

For any aggregate keyed by a unique business `code` (master/reference data — Country, State,
CategoryOfLaw, Legislation, Rule, TaskType, ...), the interface extends the generic port in
`src/domain/repositories/base_repository.py`:

```python
class IItemRepository(IRepository[Item]):
    """Only add methods beyond the generic CRUD contract here."""
```

And the implementation extends `SqlAlchemyRepository[TEntity, TModel]` in
`src/infrastructure/database/repositories/base_repository_impl.py`, which already provides
`get_by_id`, `get_by_code`, `exists_by_code`, `delete`, and the `_get_model`/`_require_model`
helpers — implement only `_model`, `_to_entity`, `_code_equals`, and any bespoke queries.

Aggregates that are not code-keyed masters (`User`, `RoleAssignment`, `Permission`,
`AuditLog`, ...) may define a standalone `ABC` instead — that is the existing, correct
pattern, not a shortcut. Do not force a non-master aggregate to extend `IRepository[TEntity]`
just for consistency; match the shape that already exists for that kind of repository.

---

### 3. Repository Interface (Port — Domain Layer)

**Location:** `src/domain/repositories/<entity>_repository.py`

**Naming convention:** `I<Entity>Repository`

```python
from abc import ABC, abstractmethod

class IItemRepository(ABC):
    @abstractmethod
    async def get_by_id(self, item_id: UUID) -> Item | None: ...

    @abstractmethod
    async def create(self, item: Item) -> Item: ...

    @abstractmethod
    async def list_all(self, skip: int = 0, limit: int = 100) -> list[Item]: ...
```

**Rules:**
- Uses ABC with `@abstractmethod`
- Lives in `domain/` — no framework imports
- Methods accept/return domain entities only (NOT ORM models)
- Naming: `I` prefix + entity name + `Repository`
- Defines WHAT, not HOW

---

### 4. Repository Implementation (Adapter — Infrastructure Layer)

**Location:** `src/infrastructure/database/repositories/<entity>_repository_impl.py`

```python
class ItemRepositoryImpl(IItemRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, item_id: UUID) -> Item | None:
        stmt = select(ItemModel).where(ItemModel.id == item_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None
```

**Rules:**
- Implements the interface from domain layer
- Contains SQLAlchemy queries
- Maps ORM models ↔ domain entities
- No business logic — pure data access

---

## Dependency Injection (FastAPI)

```python
# In controller file
def _get_item_service(
    item_repo: IItemRepository = Depends(get_item_repository),
) -> ItemService:
    return ItemService(item_repo=item_repo)
```

`get_item_repository` (in `src/api/v1/dependencies.py`) is the one place that takes
`session: AsyncSession = Depends(get_db_session)` and turns it into a repository. Everything
above that — the service, the controller — depends on the repository interface, never on the
session. The same pattern applies to cross-cutting adapters: `get_permission_resolver`
already wraps `PermissionManager(session)` this way: depend on `IPermissionResolver`, not on
building a `PermissionManager` inline.

---

## File Naming Convention

| Layer | File Pattern | Class Pattern |
|-------|-------------|---------------|
| Controller | `src/api/v1/endpoints/<module>/controller.py` | Functions (routes) |
| Schemas | `src/api/v1/endpoints/<module>/schemas.py` | Pydantic models |
| Service | `src/application/services/<name>_service.py` | `<Name>Service` |
| Interface | `src/domain/repositories/<entity>_repository.py` | `I<Entity>Repository` |
| Implementation | `src/infrastructure/database/repositories/<entity>_repository_impl.py` | `<Entity>RepositoryImpl` |
| ORM Model | `src/infrastructure/database/models/<module>/<entity>_model.py` | `<Entity>Model` |
| Domain Entity | `src/domain/entities/<module>/<entity>.py` | `<Entity>` (dataclass) |

---

## What NEVER belongs in each layer

| Layer | NEVER contains |
|-------|---------------|
| Controller | SQL, business rules, ORM models, direct session queries |
| Service | HTTP concepts, Request/Response objects, HTTPException |
| Repository Interface | SQLAlchemy, framework imports, implementation details |
| Repository Impl | Business logic, HTTP concepts, validation rules |

---

## Error Handling Flow

```
Repository → raises nothing (returns None if not found)
Service    → raises ValueError("User not found")
Controller → catches ValueError → raises HTTPException(404, detail=str(e))
```

---

## Checklist for New Endpoints

Before creating any new API endpoint, verify:

- [ ] Controller is thin (< 10 lines, delegates to service)
- [ ] Service contains all business logic
- [ ] Repository interface defined in `domain/repositories/`
- [ ] Repository implementation in `infrastructure/database/repositories/`
- [ ] Interface uses `I` prefix naming (`IUserRepository`)
- [ ] Service raises `ValueError` for business errors (not HTTPException)
- [ ] Controller maps errors to HTTP status codes
- [ ] No ORM models imported in controller
- [ ] No SQLAlchemy imported in controller (including `AsyncSession` as a parameter type)
- [ ] No repository/adapter constructed inline in the controller (`XRepositoryImpl(session)`,
      `PermissionManager(session)`, `AuditService(session)`) — injected via `Depends()` instead
- [ ] Service constructor takes repository/port interfaces only, never `AsyncSession`
- [ ] New domain entity inherits `BaseEntity`; new ORM model inherits `BaseModel`
- [ ] New code-keyed master repository extends `IRepository[TEntity]` /
      `SqlAlchemyRepository[TEntity, TModel]` rather than redeclaring CRUD from scratch
- [ ] Dependency injection via `Depends()` factory function

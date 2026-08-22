---
inclusion: always
---

# Testing Standard — Mandatory Coverage

Every new backend service, repository implementation, and workflow/domain component ships
with a unit and/or integration test in the same change. Every new frontend hook, form, and
page with logic ships with a Testing Library test in the same change. This is not optional
follow-up work — a PR that adds a class or a component without its test is incomplete, the
same way an endpoint without its service layer would be.

This file exists because the codebase went from having full backend/frontend coverage for
the six masters and core auth/RBAC/workflow paths to having zero test debt in one pass. The
patterns below are exactly what was used to close that gap — copy them, don't reinvent them.

---

## Backend

### Unit tests: services against fake repositories, not a database

**Location:** `backend/tests/unit/application/test_<name>_service.py`

A service's constructor takes repository *interfaces* (per `api-layer-standard.md`), so its
unit test gives it hand-written in-memory fakes, not a mock library and not a real database.
`unittest.mock.AsyncMock` is not the convention here — every existing repository fake in this
codebase (`workflow_fakes.py`, `master_fakes.py`) is a small hand-written class implementing
the same `I<Entity>Repository` interface with a `dict` for storage.

```python
# tests/unit/application/master_fakes.py (existing masters live here; add new ones alongside)
class FakeCountryRepository(ICountryRepository):
    def __init__(self) -> None:
        self.rows: dict[UUID, Country] = {}
        # Settable by a test to control has_dependents() without a real FK.
        self.dependents: set[UUID] = set()

    async def get_by_id(self, entity_id: UUID) -> Country | None:
        return copy.deepcopy(self.rows.get(entity_id))  # deep copy: caller mutation must not leak back

    async def create(self, entity: Country) -> Country:
        self.rows[entity.id] = copy.deepcopy(entity)
        return copy.deepcopy(entity)

    async def has_dependents(self, entity_id: UUID) -> bool:
        return entity_id in self.dependents
```

```python
# tests/unit/application/test_country_service.py
@pytest.fixture
def repo() -> FakeCountryRepository:
    return FakeCountryRepository()

@pytest.fixture
def service(repo: FakeCountryRepository) -> CountryService:
    return CountryService(repo)

class TestCreate:
    async def test_duplicate_code_is_rejected(self, service: CountryService, actor: User) -> None:
        await service.create_country(CountryCreate(code="IN", name="India"), actor)

        with pytest.raises(DuplicateEntityError):
            await service.create_country(CountryCreate(code="IN", name="Other"), actor)
```

**What a new master/service's unit tests must cover:**
- Every business rule the service enforces beyond basic CRUD — parent-existence checks,
  code/name uniqueness (and its scope: global vs. per-parent), jurisdiction/hierarchy
  validation, delete-guard via `has_dependents`.
- Every branch of a partial `update_*` method, one test per field that changes independently.
  When a service re-validates a downstream field after an upstream one changes (see
  `LegislationService.update_legislation`'s `elif request.country_id is not None:` branch
  re-checking state-in-country), write the test for the *unusual order* explicitly — this
  exact class of bug (`StateService.update_state` missing the equivalent re-check when only
  `country_id` changes) was caught by exactly one such test and fixed as a result.
- Class-grouped `Test<Action>` names (`TestCreate`, `TestUpdate`, `TestDelete`), no shared
  mutable state between tests — each test builds its own fresh fake repo via the `repo`
  fixture.

Domain services with no persistence (`state_machine_service.py`, `workflow_engine.py`) follow
the same shape: fakes for their dependencies (`workflow_fakes.py`'s `WorkflowScenario`), one
test per transition/branch, not one giant end-to-end test.

### Integration tests: repository implementations against a real database

**Location:** `backend/tests/integration/database/test_<entity>_repository_impl.py`

Repository implementations are SQL, and SQL filter/join/uniqueness behavior cannot be
meaningfully faked — these use the real `db_session` fixture (a Postgres transaction rolled
back after each test), not an in-memory substitute.

```python
class TestNameUniquenessIsScopedToCountry:
    async def test_same_name_in_different_countries_does_not_collide(
        self, db_session: AsyncSession
    ) -> None:
        repo = StateRepositoryImpl(db_session)
        country_a = await _make_country(db_session)
        country_b = await _make_country(db_session)
        await repo.create(_state(country_a.id, name="Central"))

        assert await repo.exists_by_name("Central", country_a.id) is True
        assert await repo.exists_by_name("Central", country_b.id) is False
```

**What a new repository impl's tests must cover:**
- `create`/`get_by_id`/`update`/`delete`, `exists_by_code`, `exists_by_name` (including the
  scoping — global vs. parent-scoped — and the `exclude_id` behavior used during updates).
- `list_all` with each supported filter combination (search, `is_active`, every parent-id
  filter) plus pagination and ordering; `count` mirroring the same filters.
- `has_dependents` against each entity type that actually references this one via FK.
- Entity ↔ ORM model mapping round-trips correctly for every field, including nullable
  parent-id columns (a `NULL` state_id must round-trip as `None`, not `''`).

Anything that isn't behind a repository port and instead does raw ORM work directly against
`AsyncSession` (`permission_manager.py` is the existing example, taking `AsyncSession`
because it has no interface to fake) is still an integration test in
`tests/integration/database/`, not a unit test — the same reasoning as above applies: no
interface exists to fake, so the real database is the only option that tests anything real.

### Directory convention — do not mirror `src/`

Tests are flat files grouped **one level deep by layer**, matching what already exists:
`tests/unit/domain/`, `tests/unit/application/`, `tests/unit/infrastructure/`,
`tests/integration/`, `tests/integration/database/`, `tests/integration/api/`. A new service
test is a sibling file in `tests/unit/application/`, not a new subdirectory that mirrors
`src/application/services/workflow/`.

### Checklist — new backend service/repository/endpoint

- [ ] Service has a fake repository in the relevant `*_fakes.py` (or a new one, matching the
      existing hand-written, deep-copy, `dict`-backed pattern)
- [ ] Service has `tests/unit/application/test_<name>_service.py` covering every business
      rule, every independent branch of partial updates, and the delete-guard
- [ ] Repository implementation has `tests/integration/database/test_<entity>_repository_impl.py`
      covering CRUD, uniqueness scoping, filters/pagination, `has_dependents`, and
      entity↔model round-trips for nullable fields
- [ ] New API endpoints touching auth/session state get an integration test in
      `tests/integration/test_auth_api.py` or `tests/integration/api/` using
      `app.dependency_overrides`, not `unittest.mock.patch` (patching a module attribute
      after FastAPI has already resolved `Depends(...)` at route-declaration time has no
      effect on the registered route)
- [ ] `pytest -q` (full suite), `ruff check src scripts tests`, `mypy src tests scripts`,
      `alembic check` all pass before considering the change done

---

## Frontend

### Test infrastructure already exists — do not recreate it

`jsdom`, `@testing-library/jest-dom`, `@testing-library/user-event`, `msw`,
`@vitest/coverage-v8` are installed and pinned exact in `frontend/package.json`. Reuse:

- `frontend/tests/setup.ts` — jest-dom matchers, RTL auto-cleanup, PrimeReact polyfills
- `frontend/tests/test-utils.tsx` — `renderWithProviders`, `createTestStore`,
  `createTestQueryClient`, plus the PrimeReact dropdown helpers below
- `frontend/tests/mocks/server.ts` — the shared MSW server and its default handlers for
  self-loading RBAC endpoints

Do not install a different testing library, do not write a second render helper, and do not
hand-roll a `QueryClientProvider`/`Provider` wrapper inline in a test file.

### Where tests live

**Location:** `frontend/tests/unit/<area>/<Name>.test.tsx` (`shared/`, `rbac/`, `auth/`,
`masters/`, ...). Tests are **not** colocated with `src/` — `tsconfig.test.json` and
`vite.config.ts`'s `test.include` both expect `tests/**/*.{test,spec}.{ts,tsx}`.

### `renderWithProviders`

Mirrors the real provider stack from `App.tsx` (Redux `Provider` → `QueryClientProvider` →
`PrimeReactProvider` → `MemoryRouter`). Use it for anything that renders a component; use the
bare `createTestStore`/`createTestQueryClient` plus `renderHook` for hook-only tests.

```tsx
renderWithProviders(<CountryForm visible country={null} onHide={vi.fn()} onSubmit={onSubmit} />, {
  preloadedState: { rbac: { ...defaultRbacState, apiResourceActions: { countries: ['CREATE'] }, isApiLoaded: true } },
});
```

`preloadedState` is typed `TestPreloadedState` (exported from `test-utils.tsx`) — **not**
`PreloadedState<RootState>` imported from `@reduxjs/toolkit`, which Redux Toolkit 2.x no
longer exports.

### Mocking the network: MSW, not `vi.mock('axios')`

Every API-touching test uses `server.use(http.get(...), ...)` from `tests/mocks/server.ts`,
mocking at the HTTP layer so the real `apiClient` interceptors (token attach, 401 refresh
retry) still run. Default handlers for `/auth/refresh` and the three RBAC
`my-permissions/*` endpoints already exist precisely so that a test focused on something
else doesn't have to stub them — override with `server.use()` only when the test actually
cares about that endpoint's response.

### Testing PrimeReact Dropdown/Dialog — read this before writing a new one

Three non-obvious fixes make PrimeReact overlays testable under jsdom at all; they live in
`tests/setup.ts` and `tests/test-utils.tsx` already and must not be reverted:

1. **`cssTransition: false`** is passed to `PrimeReactProvider` in `test-utils.tsx`. Without
   it, `react-transition-group`'s enter/leave animation never completes under jsdom (no real
   animation-frame timing), and an opened panel stays invisible to every query.
2. **`HTMLElement.prototype.offsetParent`** is stubbed in `tests/setup.ts` to return
   `parentNode`. jsdom has no layout engine and always reports `offsetParent` as `null`,
   which sends PrimeReact's `DomHandler.absolutePosition()` down the branch that measures a
   panel by briefly flipping it to `display: block` and back to `display: none` — leaving it
   hidden. This is the fix for a Dropdown/MultiSelect/Calendar panel silently staying
   `display: none` after a click that "worked."
3. **Never click a Dropdown's accessible `<input>` directly.** `getByLabelText('Owning
   country')` finds PrimeReact's hidden a11y input, which has `pointer-events: none` — the
   click throws. Use the two helpers exported from `test-utils.tsx` instead:

```tsx
// Opens the dropdown via its real trigger element, then clicks the option by accessible name.
await selectDropdownOption(user, 'Owning country', 'India (IN)');

// Reads the *closed* dropdown's displayed label — not screen.getByText(label), which also
// matches PrimeReact's hidden native <select><option> fallback and throws on ambiguity.
expect(getDropdownLabel('Owning country')).toBe('India (IN)');

// Scopes to the zod error specifically — a required Dropdown's own placeholder often reads
// identically to its validation message ("Select a country" appears in both).
expect(getValidationError('Select a country')).toBeInTheDocument();
```

An empty-string sentinel value (the `COUNTRY_WIDE`/`CENTRAL` pattern used by
CategoryOfLaw/Legislation/Rule's optional parent pickers) renders as a *blank* closed label
regardless of which option maps to it — do not assert the closed label for that case; assert
the option exists in the open panel, and that the sentinel round-trips through submit
(`state_id: null`) instead.

### Fixture IDs must satisfy the schema's own validation

Every master form's zod schema validates required parent ids with `z.string().uuid()`. A
fixture id like `'country-1'` is not a UUID — the form will fail silent client-side
validation and `onSubmit` will never fire, which reads exactly like a broken test until you
notice the `p-invalid` class still on the field. Use real UUID-shaped strings
(`'11111111-1111-1111-1111-111111111111'`) for any parent-id fixture.

### Checklist — new master (frontend)

- [ ] `<Entity>Api.ts` — one line calling `createMasterApi`; no dedicated test needed (the
      factory itself is tested once, generically, in `tests/unit/masters/createMasterApi.test.ts`)
- [ ] `use<Entity>.ts` hooks — a `tests/unit/masters/use<Entities>.test.tsx` covering: the
      list endpoint's filter params reach the request, and a create/update/delete invalidates
      exactly its declared dependent query keys (no more, no fewer)
- [ ] `<Entity>Form.tsx` — a `tests/unit/masters/<Entity>Form.test.tsx` covering: every zod
      validation rule, create-vs-edit header and field reset, submit-time normalisation
      (trim/case, empty-string→`null` mapping), and any cascading dropdown (`useWatch` +
      a child lookup keyed on the parent's current value)
- [ ] `<Entity>sPage.tsx` — for the first master introducing a new page-level pattern, a full
      `tests/unit/masters/<Entities>Page.test.tsx` (render, permission-gated New button,
      permission-gated Actions column, create end-to-end, delete end-to-end, delete-conflict
      end-to-end). For a master that reuses `MasterCrudPage` with nothing new, this is optional
      — the generic shell is already covered by `MasterCrudPage.test.tsx`

### Checklist — new hook/component (non-master)

- [ ] Any component with conditional rendering, a permission gate, or an async data
      dependency gets its own `tests/unit/<area>/<Name>.test.tsx`
- [ ] A Redux slice's thunks get one test per outcome (fulfilled + rejected) against a real
      reducer via `configureStore`, mocking only the network (MSW), not the thunk itself
- [ ] A slice whose `initialState` hydrates from `sessionCache` at module-import time needs a
      `<Slice>.hydration.test.ts` using `vi.resetModules()` + dynamic `import()` to exercise
      both the cold-start and cache-warm shapes — a static top-level import only ever sees one
- [ ] `npm run build`, `npm run type-check`, `npm run lint`, `npm test` all pass before
      considering the change done

### Version discipline

`vitest`/`@vitest/coverage-v8` must stay on a version whose own `vite` dependency range
includes the project's actual `vite` version (check `npm view vitest@<version> dependencies`
before bumping either). A mismatch does not fail loudly — npm silently installs a second,
nested `vite` copy for vitest's resolution, and `vite.config.ts`'s `test` block then fails
type-checking with `'test' does not exist in type 'UserConfigExport'` because the two
`vite` packages have structurally incompatible `Plugin`/`UserConfig` types.

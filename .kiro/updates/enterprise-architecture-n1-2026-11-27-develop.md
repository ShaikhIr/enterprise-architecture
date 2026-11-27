## N-1 Update Report: enterprise-architecture (2026-11-27)

**Mode:** report · **Granularity:** minor · **Scope:** backend, frontend, platform ·
**Branch:** develop @ 87861d85 (origin ShaikhIr/enterprise-architecture; the working tree is on `updated-enterprise-base` and was not touched) ·
**Baseline gates:** not run: report mode on develop, working tree is on another branch

**How the data was gathered**
- **C (current version) comes from develop's committed files, not from an installed environment.** Backend: the `==` pins in `backend/pyproject.toml`. Frontend: the resolved versions in develop's `frontend/package-lock.json` (read with `git show 87861d85:<path>`). No `npm ls`, `pip list` or `npm audit` was run.
- **Latest stable (N) and target (T):** PyPI JSON (`https://pypi.org/pypi/<pkg>/json`, queried with the system Python 3.12.10 because `backend\.venv` does not exist) and the npm registry packuments (queried with Node, not `npm view`). Stable means a plain `x.y.z` version, not yanked (PyPI) and not marked deprecated (npm).
- **Advisories were checked per package from the registries, not through `npm audit`.** Python: the `vulnerabilities` field of `pypi.org/pypi/<pkg>/<version>/json` for C, T and N. npm: the registry's bulk advisory endpoint, queried per package and version, with the vulnerable ranges evaluated with npm's bundled `semver`. **Only direct dependencies were checked.** Transitive packages in the lockfile (for example `launch-editor`, which Vite pulls in) and unpinned Python transitives (Starlette and others) were not queried. "No advisory found" is not "safe".
- Platform support dates: `endoflife.date`. GitHub Actions versions: the GitHub releases API (first 100 releases per action).
- 0.x packages: every minor change is treated as a major crossing and needs your approval, as the policy says.

---

### Summary

develop is behind N-1 almost everywhere: of 69 dependencies (24 backend, 38 frontend, 7 platform items), 5 are at N-1 and 5 are only a patch behind. **Six direct dependencies carry known advisories** (PyJWT, OpenTelemetry API, pytest, axios, zod, Vite), and `eslint` is on a line the maintainers have deprecated, so the verdict is ACTION REQUIRED. Do first: axios 1.20.0 (the N-1 target, fixes 12 advisories), then PyJWT 2.15.0, which is above T and needs your approval.

| Status | Backend | Frontend | Platform |
|--------|---------|----------|----------|
| ✅ At N-1 | 0 | 5 | 0 |
| 🔄 Patch behind | 1 | 4 | 0 |
| ⬆️ Line behind | 20 | 21 | 7 |
| ⏫ Ahead of N-1 | 0 | 4 | 0 |
| 🔴 Vulnerable | 3 | 3 | 0 |
| ⛔ Blocked | 0 | 1 | 0 |

---

### 1. Security advisories

Method: per-package registry lookups (see above), not `npm audit`. Direct dependencies only.

| Severity | Package | Advisory | Affects | Fixed in | Recommendation |
|----------|---------|----------|---------|----------|----------------|
| 🔴 CRITICAL | PyJWT | 31 PyPI entries (about 16 distinct issues, the rest are GHSA/PYSEC duplicates) affect C=2.9.0. They include a verifier algorithm allow-list bypass (PYSEC-2026-176 / GHSA-jq35-7prp-9v3f), `crit` header not validated (GHSA-752w-5fwx-jx9f), JWKS client DoS and redirect issues (GHSA-fhv5-28vv-h8m8, GHSA-9v7f-9g4p-ffgj) | C 2.9.0 **and T 2.14.0** | 2.12.0 to 2.15.0 depending on the issue. **Two remain open at T:** GHSA-42vr-xj54-vc7v (`PyJWKClient.get_signing_key_from_jwt`) and GHSA-x33g-cr3x-6449 (inconsistent OKP private JWK accepted), both fixed in 2.15.0 | Smallest fixing version is **2.15.0** (N is 2.15.1). That is above T, so it needs your approval. Moving off 2.9.0 is urgent whichever version you pick. I did not inspect application code for use of the affected APIs. |
| 🔴 CRITICAL | opentelemetry-api (`observability` extra) | GHSA-xcq7-p3pf-p88h (ReDoS in `TraceState.from_header`, fixed 1.45.1) and GHSA-mf5v-w3w3-f6cg (ReDoS in `TraceContextTextMapPropagator.extract`, fixed 1.45.2) | C 1.27.0 **and T 1.44.0** | 1.45.1 / 1.45.2 | Smallest version fixing both is **1.45.2** (which is N). Above T, needs approval. `opentelemetry-sdk` and `opentelemetry-instrumentation-fastapi` must move with it (section 5). |
| 🔴 CRITICAL | pytest (`dev`) | GHSA-6w46-j5rx-g56g / PYSEC-2026-1845 (CVE-2025-71176): predictable `/tmp/pytest-of-{user}` directory on UNIX, local users only | C 8.3.3. T 9.1.1 is clean | 9.0.3 | T fixes it, but 8.x to 9.x is a major crossing and needs approval. Exposure is limited to shared UNIX hosts, so I rate it lower than the two above. |
| 🔴 CRITICAL | axios | 12 advisories, 7 high and 5 moderate. They include prototype-pollution gadgets (GHSA-m8m8-qj5v-23w3, GHSA-x97p-jq2g-jp4f, GHSA-vh66-26gq-q6x8, GHSA-9fr6-4gfg-395g), a fetch-adapter redirect SSRF (GHSA-r4gj-5m52-g5wh), ReDoS (GHSA-c29m-xwm3-cm6r, GHSA-mghh-pgcx-3jjj), HTTP/2 adapter issues (GHSA-3pq3-5fj3-cg6v, GHSA-542g-h47m-68v8), NO_PROXY bypass (GHSA-44g4-m2mj-wpvx) and header injection (GHSA-j8rh-479h-cp32, GHSA-4hqw-qxg8-jxx2) | C 1.18.0. T 1.20.0 is clean | 1.20.0 | **Update to 1.20.0 (= T).** It is a minor step within major 1, so no major approval is needed. |
| 🔴 CRITICAL | zod | GHSA-mrhx-c7xc-m3w5 (high): memory exhaustion validating oversized constrained collections | Every 3.x release, including C 3.25.76, **and T 4.5.4** (`<4.6.6`) | 4.6.6 | Smallest fix is **4.6.6** (N-line, N is 4.6.7). Above T, a major crossing, and probably a code change. Needs approval. Move `@hookform/resolvers` with it (section 5). |
| 🔴 CRITICAL | vite (dev server) | GHSA-587h-7wmj-h5pm (high), GHSA-r825-w8mm-5pxw, GHSA-698v-4r3x-3vcv, GHSA-rq7h-c2jc-7f22 (moderate) and GHSA-9jrq-w75r-8gcw (low). All are in the dev server or its `launch-editor` dependency, so the production bundle is not affected | C 6.4.3. T 8.3.8 is clean | **6.4.5.** 6.4.4 is itself affected by GHSA-8g5g-mxqh-grgj | Smallest fix is **6.4.5** (6.4.6 is the newest 6.x and also clean). It is a patch in C's own line, not in the N-1 line, so it needs your approval. It keeps vitest 4.1.11 and plugin-react 4.7.0 valid. The T route (8.3.8) is a two-major jump. |
| 🟠 MAJOR (deprecation) | eslint | npm marks every 9.39.x release deprecated ("no longer supported"), including C 9.39.4 and 9.39.5 | C | n/a | See sections 3 and 5: the move to 10.x is blocked. |

No advisory found in the registries for the other direct dependencies at C, T or N.

---

### 2. Backend dependencies (backend/pyproject.toml)

Declared `==` pins; C is the pin. Extras are marked: (bg) `background`, (obs) `observability`, (dev) `dev`. Not exercised by tests (the code never imports them): celery, the three opentelemetry packages. A green gate would say little about these.

| Package | Declared | Current (C) | Latest stable (N) | N-1 target (T) | Status | Notes |
|---------|----------|-------------|-------------------|----------------|--------|-------|
| fastapi | ==0.115.0 | 0.115.0 | 0.165.0 | 0.164.0 | ⬆️ Line behind | 0.x: major crossing, approval. T needs `starlette>=1.6.0`, `pydantic>=2.9.0`, `opentelemetry-api>=1.44.0` (new), Python >=3.11 |
| uvicorn[standard] | ==0.30.6 | 0.30.6 | 0.54.0 | 0.53.0 | ⬆️ Line behind | 0.x: approval |
| pydantic | ==2.9.2 | 2.9.2 | 2.14.4 | 2.13.5 | ⬆️ Line behind | Minor step. `pydantic.mypy` plugin vs mypy 2.x not verified |
| pydantic-settings | ==2.5.2 | 2.5.2 | 2.16.3 | 2.15.0 | ⬆️ Line behind | Minor step. Needs `pydantic>=2.7` |
| sqlalchemy[asyncio] | ==2.0.35 | 2.0.35 | 2.1.9 | 2.0.58 | 🔄 Patch behind | 2.1 is N's line, so stay in 2.0 |
| asyncpg | ==0.29.0 | 0.29.0 | 0.32.0 | 0.31.0 | ⬆️ Line behind | 0.x: approval |
| alembic | ==1.13.2 | 1.13.2 | 1.20.1 | 1.19.2 | ⬆️ Line behind | Minor step. Needs `SQLAlchemy>=1.4.23` |
| PyJWT | ==2.9.0 | 2.9.0 | 2.15.1 | 2.14.0 | 🔴 Vulnerable | T is also affected. Smallest fix 2.15.0 (section 1) |
| bcrypt | ==4.2.0 | 4.2.0 | 5.0.0 | 4.3.0 | ⬆️ Line behind | Minor step |
| structlog | ==24.4.0 | 24.4.0 | 26.1.0 | 25.5.0 | ⬆️ Line behind | Calver. Confirm whether you treat 24 to 25 as a major |
| httpx (runtime and dev) | ==0.27.2 | 0.27.2 | 0.29.0 | 0.28.1 | ⬆️ Line behind | 0.x: approval. Pinned in two places, keep them equal |
| boto3 | ==1.35.36 | 1.35.36 | 1.44.12 | 1.43.127 | ⬆️ Line behind | Minor step. Lockstep with boto3-stubs |
| redis | ==5.1.1 | 5.1.1 | 8.2.0 | 8.1.0 | ⬆️ Line behind | Major crossing (5 to 8), approval. Login throttle uses a Lua script, so the real Redis behaviour matters |
| celery[redis] (bg) | ==5.4.0 | 5.4.0 | 5.7.0 | 5.6.3 | ⬆️ Line behind | Minor step. Not exercised by tests. Its `redis` extra comes through `kombu[redis]`, whose range I did not fetch |
| opentelemetry-api (obs) | ==1.27.0 | 1.27.0 | 1.45.2 | 1.44.0 | 🔴 Vulnerable | T also affected. Smallest fix 1.45.2. Not exercised by tests |
| opentelemetry-sdk (obs) | ==1.27.0 | 1.27.0 | 1.45.2 | 1.44.0 | ⬆️ Line behind | No advisory of its own, but 1.44.0 pins `opentelemetry-api==1.44.0`, so it follows the API |
| opentelemetry-instrumentation-fastapi (obs) | ==0.48b0 | 0.48b0 | 0.66b2 | 0.65b0 | ⬆️ Line behind 🔵 | This package only ships `b` (beta) versions, so the "no pre-release" rule would leave no target. I used the `b` series as its release scheme. Needs your decision. 0.65b0 pairs with SDK 1.44.0 |
| pytest (dev) | ==8.3.3 | 8.3.3 | 9.2.0 | 9.1.1 | 🔴 Vulnerable | C affected, T clean. Major crossing |
| pytest-asyncio (dev) | ==0.24.0 | 0.24.0 | 1.5.0 | 1.4.1 | ⬆️ Line behind | Major crossing. T needs `pytest>=8.4,<10`. Project sets `asyncio_mode="auto"` and a session-loop fixture, so behaviour may change |
| pytest-cov (dev) | ==5.0.0 | 5.0.0 | 7.1.0 | 7.0.0 | ⬆️ Line behind | Major crossing. T needs `coverage>=7.10.6`. Project uses `concurrency = ["thread","greenlet"]` |
| ruff (dev) | ==0.6.9 | 0.6.9 | 0.17.6 | 0.16.10 | ⬆️ Line behind | 0.x, ten lines: approval. New lint and format defaults will likely flag existing code |
| mypy (dev) | ==1.11.2 | 1.11.2 | 2.4.1 | 2.3.1 | ⬆️ Line behind | Major crossing. Strict-mode results will shift |
| pre-commit (dev) | ==3.8.0 | 3.8.0 | 4.7.0 | 4.6.2 | ⬆️ Line behind | Major crossing |
| boto3-stubs[s3] (dev) | ==1.35.36 | 1.35.36 | 1.44.12 | 1.43.127 | ⬆️ Line behind | Lockstep with boto3 (same T) |

Not evaluated: `setuptools>=68.0` in `[build-system]` is an unpinned range that floats to the latest release. 🔵 INFO. Python `requires-python = ">=3.12"`: every T above declares support for Python 3.12.

---

### 3. Frontend dependencies (frontend/package.json)

C is the version resolved in develop's `package-lock.json`. Runtime dependencies use `^`; the rest are exact or as shown.

| Package | Declared range | Locked (C) | Latest stable (N) | N-1 target (T) | Status | Notes |
|---------|----------------|------------|-------------------|----------------|--------|-------|
| @hookform/resolvers | ^3.9.0 | 3.10.0 | 7.0.9 | 6.0.2 | ⬆️ Line behind | Major crossing. T's zod peer is `^3.25.0 \|\| ^4.0.0` |
| @reduxjs/toolkit | ^2.5.0 | 2.12.0 | 2.15.0 | 2.14.0 | ⬆️ Line behind | Minor step. 🔵 range drift |
| @tanstack/react-query | ^5.62.0 | 5.101.0 | 5.108.4 | 5.107.2 | ⬆️ Line behind | Minor step. 🔵 range drift |
| axios | ^1.7.9 | 1.18.0 | 1.21.1 | 1.20.0 | 🔴 Vulnerable | 12 advisories. T is clean. 🔵 range drift (a fresh resolve floats to 1.21.1) |
| primeflex | ^3.3.1 | 3.3.1 | 4.0.0 | 3.3.1 | ✅ At N-1 | |
| primeicons | ^7.0.0 | 7.0.0 | 8.0.2 | 7.0.0 | ✅ At N-1 | |
| primereact | ^10.8.0 | 10.9.8 | 11.2.3 | 11.1.0 | ⬆️ Line behind | Major crossing (10 to 11). T peer is `react>=19`. Theme and markup may change |
| react | ^19.1.0 | 19.2.7 | 19.3.1 | 19.2.9 | 🔄 Patch behind | 🔵 range drift |
| react-dom | ^19.1.0 | 19.2.7 | 19.3.1 | 19.2.9 | 🔄 Patch behind | Move with react (peer `react@^19.2.9`). 🔵 range drift |
| react-hook-form | ^7.54.0 | 7.79.0 | 7.92.0 | 7.91.0 | ⬆️ Line behind | Minor step. 🔵 range drift |
| react-redux | ^9.2.0 | 9.3.0 | 9.3.1 | 9.2.0 | ⏫ Ahead | C is in N's line. Report only. 🔵 range drift |
| react-router-dom | ^7.1.0 | 7.17.0 | 7.18.7 | 7.17.0 | ✅ At N-1 | 🔵 range drift |
| zod | ^3.24.0 | 3.25.76 | 4.6.7 | 4.5.4 | 🔴 Vulnerable | T is also affected. Smallest fix 4.6.6 |
| @commitlint/cli | 19.6.0 | 19.6.0 | 21.2.4 | 21.1.0 | ⬆️ Line behind | Major crossing. T needs Node >=22.12 |
| @commitlint/config-conventional | 19.6.0 | 19.6.0 | 21.2.4 | 21.1.0 | ⬆️ Line behind | Move with `@commitlint/cli` |
| @eslint/js | 9.17.0 | 9.17.0 | 10.0.1 | 9.39.5 | ⬆️ Line behind | T is in the 9.x line while eslint's T is 10.x: conflict (section 5). C is already out of step with eslint 9.39.4 |
| @testing-library/jest-dom | 6.9.1 | 6.9.1 | 8.0.0 | 7.0.1 | ⬆️ Line behind | Major crossing. T needs Node >=22 and `@testing-library/dom >=10 <11` |
| @testing-library/react | ^16.1.0 | 16.3.2 | 16.3.3 | 16.2.0 | ⏫ Ahead | Report only. 🔵 range drift |
| @testing-library/user-event | 14.6.5 | 14.6.5 | 14.6.13 | 14.5.2 | ⏫ Ahead | Report only |
| @types/node | ^24.13.3 | 24.13.3 | 26.6.11 | 26.5.1 | ⬆️ Line behind | Major crossing. CI runs Node 22, so 26 typings do not match the runtime. Decision needed |
| @types/react | ^19.1.0 | 19.2.17 | 19.3.3 | 19.2.18 | 🔄 Patch behind | 🔵 range drift |
| @types/react-dom | ^19.1.0 | 19.2.3 | 19.3.0 | 19.2.7 | 🔄 Patch behind | 🔵 range drift |
| @vitejs/plugin-react | ^4.3.0 | 4.7.0 | 6.3.0 | 6.2.1 | ⬆️ Line behind | Major crossing. T needs `vite@^8`; C supports up to `^7` |
| @vitest/coverage-v8 | 4.1.11 | 4.1.11 | 5.1.2 | 5.0.5 | ⬆️ Line behind | Major crossing. Pins `vitest` to the same version |
| eslint | ^9.16.0 | 9.39.4 | 10.15.0 | 10.14.0 | ⛔ Blocked 🟠 | C is deprecated. Move to 10.x is blocked by plugin peers (section 5) |
| eslint-import-resolver-typescript | 3.7.0 | 3.7.0 | 4.4.5 | 4.3.5 | ⬆️ Line behind | Major crossing |
| eslint-plugin-import | 2.31.0 | 2.31.0 | 2.32.0 | 2.31.0 | ✅ At N-1 | Peer `eslint` tops out at `^9` in both 2.31.0 and 2.32.0 |
| eslint-plugin-react-hooks | 5.1.0 | 5.1.0 | 7.1.1 | 7.0.1 | ⬆️ Line behind | Major crossing. T peer tops out at eslint `^9`. Only N (7.1.1) accepts eslint 10 |
| globals | 15.14.0 | 15.14.0 | 17.14.0 | 17.13.0 | ⬆️ Line behind | Major crossing |
| husky | 9.1.7 | 9.1.7 | 9.1.7 | 9.0.11 | ⏫ Ahead | C equals N. Report only |
| jsdom | 29.1.1 | 29.1.1 | 31.0.1 | 30.1.3 | ⬆️ Line behind | Major crossing. T needs Node `^22.22.2 \|\| ^24.15.0 \|\| >=26` |
| lint-staged | 15.2.10 | 15.2.10 | 17.6.2 | 17.5.1 | ⬆️ Line behind | Major crossing (two). T needs Node >=22.22.1 |
| msw | 2.15.0 | 2.15.0 | 3.0.8 | 2.15.0 | ✅ At N-1 | |
| prettier | 3.4.2 | 3.4.2 | 3.10.1 | 3.9.10 | ⬆️ Line behind | Minor step. Formatting output may change |
| typescript | ~5.7.0 | 5.7.3 | 7.0.2 | 6.0.3 | ⬆️ Line behind | Major crossing. T satisfies typescript-eslint 8.73.0 (`<6.1.0`) |
| typescript-eslint | 8.18.0 | 8.18.0 | 8.74.0 | 8.73.0 | ⬆️ Line behind | Minor step. C only allows TypeScript `<5.8` |
| vite | ^6.0.0 | 6.4.3 | 8.4.0 | 8.3.8 | 🔴 Vulnerable | Five dev-server advisories at C. T is two majors ahead. Single `vite` copy in the lockfile (no nested entry found) |
| vitest | 4.1.11 | 4.1.11 | 5.1.2 | 5.0.5 | ⬆️ Line behind | Major crossing. T peer `vite ^6.4 \|\| ^7 \|\| ^8`, Node `^22.12` |

**🔵 Range drift:** the `^` ranges for @reduxjs/toolkit, @tanstack/react-query, axios, react, react-dom, react-hook-form, react-redux, react-router-dom, @testing-library/react, @types/react and @types/react-dom allow a fresh, lockfile-less install to float up to N. `npm ci` is not affected. I suggest `~` for these. I did not change anything.

---

### 4. Platform pins *(report only)*

| Item | Where pinned | Current | Latest stable (N) | N-1 | Support ends | Status |
|------|--------------|---------|-------------------|-----|--------------|--------|
| Python | `requires-python >=3.12`; `backend-ci.yml` `python-version: "3.12"` | 3.12 (latest 3.12.16) | 3.15 (3.15.2) | 3.14 (3.14.10) | 3.12: 2028-10-31, security fixes only since 2025-04-02 | ⬆️ Line behind |
| Node.js | `frontend-ci.yml` `node-version: "22"` | 22 (latest 22.23.5) | 26 (26.13.1) | 24 (24.22.3). Line 25 reached end of life on 2026-06-01, so it is skipped | **2027-04-30, about five months away** | ⬆️ Line behind |
| PostgreSQL | `backend-ci.yml` service `postgres:16-alpine` | 16 (16.16) | 19 (19.0, released 2026-11-19) | 18 (18.7) | 2028-11-09 | ⬆️ Line behind |
| actions/checkout | both workflows, `@v4` | v4 (4.4.0) | v7 (7.0.1) | v6 (6.1.0) | n/a | ⬆️ Line behind |
| actions/setup-python | `backend-ci.yml`, `@v5` | v5 (5.6.0) | v7 (7.1.0) | v6 (6.3.0) | n/a | ⬆️ Line behind |
| actions/setup-node | `frontend-ci.yml`, `@v4` | v4 (4.4.0) | v7 (7.1.0) | v6 (6.5.0) | n/a | ⬆️ Line behind |
| actions/upload-artifact | `backend-ci.yml`, `@v4` | v4 (4.6.2) | v7 (7.0.2) | v6 (6.0.0) | n/a | ⬆️ Line behind |
| Docker base images, Helm, Kubernetes | `backend/deployment/**` | none pinned | n/a | n/a | n/a | `Dockerfile`, `Dockerfile.dev` and both compose files are one-line comment stubs, and a search of the Helm and Kubernetes files found no image references |

Sources: [endoflife.date](https://endoflife.date) for Python, Node.js and PostgreSQL; the GitHub releases API for the four actions. No platform pin is end of life today. Node 22 is the closest to it.

---

### 5. Compatibility groups and blockers

- **FastAPI / Pydantic / OpenTelemetry.** fastapi 0.164.0 requires `starlette>=1.6.0`, `pydantic>=2.9.0` and `opentelemetry-api>=1.44.0`. The last one conflicts with the `observability` extra's `opentelemetry-api==1.27.0`, so fastapi and the three OpenTelemetry packages must move in one batch. Coherent sets: api and sdk 1.44.0 with instrumentation 0.65b0 (matches T, but api 1.44.0 is vulnerable), or api and sdk 1.45.2 with instrumentation 0.66b2 (each pins `semantic-conventions==0.66b2`; fixes the advisories and needs approval). pydantic 2.13.5 and pydantic-settings 2.15.0 (`pydantic>=2.7`) are compatible with fastapi 0.164.0. Starlette is not pinned by the project, so its current version is unknown. This is a reproducibility gap, not a finding about develop's code.
- **SQLAlchemy / asyncpg / Alembic.** alembic 1.19.2 needs `SQLAlchemy>=1.4.23`, which 2.0.58 satisfies. SQLAlchemy and asyncpg declare no constraint on each other, so only the gates can confirm 2.0.58 with asyncpg 0.31.0.
- **pytest group.** pytest-asyncio 1.4.1 requires `pytest>=8.4,<10`, so pytest 8.3.3 and pytest-asyncio 1.4.1 cannot coexist. Move pytest 9.1.1, pytest-asyncio 1.4.1 and pytest-cov 7.0.0 together. The project's `asyncio_mode = "auto"` and session-loop fixture are the likely failure points. If gates fail after that, it would be a ⛔ BLOCKED item needing a test-code change.
- **Ruff / mypy.** mypy 2.3.1 needs Python >=3.10 (fine). Whether pydantic's `pydantic.mypy` plugin at 2.13.5 works with mypy 2.x is not declared in package metadata. Not verified.
- **boto3 / boto3-stubs.** Both have the same T, 1.43.127. Compatible. botocore `<1.44.0,>=1.43.127`.
- **celery / redis.** celery 5.6.3 gets its Redis client range through `kombu[redis]`. I did not fetch it, so redis 8.1.0 with celery is unverified. `celery` is not exercised by tests.
- **React group.** react and react-dom 19.2.9 (react-dom peer `react@^19.2.9`), @types/react 19.2.18, @types/react-dom 19.2.7 (peer `@types/react@^19.2.0`) are consistent. @testing-library/react 16.3.2, react-redux 9.3.0, @reduxjs/toolkit 2.14.0, @tanstack/react-query 5.107.2, react-hook-form 7.91.0 and primereact 11.1.0 (`react>=19`) all accept React 19.2.9.
- **Forms (zod, @hookform/resolvers, react-hook-form).** The resolvers T 6.0.2 accepts zod `^3.25.0 || ^4.0.0` and react-hook-form `^7.55.0`. The only zod fix is 4.6.6, so zod and the resolvers package have to move together. I did not check whether resolvers 3.10.0 works with zod 4, so assume the resolvers move first. Both are major crossings and likely need form-code changes: that would make the batch ⛔ BLOCKED in apply mode.
- **Vite group (version discipline).** There is one `vite` copy in develop's lockfile. Two coherent options:
  - *Patch route:* vite 6.4.5 or 6.4.6 with vitest 4.1.11 (peer `vite ^6 || ^7 || ^8`) and plugin-react 4.7.0 (peer up to `^7`). No other change.
  - *T route:* vite 8.3.8, @vitejs/plugin-react 6.2.1 (peer `vite ^8`, so it cannot be left at 4.7.0), vitest 5.0.5 and @vitest/coverage-v8 5.0.5 (pinned to each other; vitest peer vite `^6.4 || ^7 || ^8`). Node `^20.19 || >=22.12` for vite 8, which Node 22 in CI satisfies. Run `npm ls vite` afterwards and require one copy. jsdom 30.1.3 needs Node `^22.22.2`: CI's `"22"` resolves to the latest 22.x, but a developer on an older 22.x would not satisfy the engine.
- **ESLint group: ⛔ BLOCKED.** eslint's T is 10.14.0 but `@eslint/js` T is 9.39.5, which conflicts (`@eslint/js@10` needs `eslint@^10`). More importantly, no released `eslint-plugin-import` (2.31.0 or 2.32.0) lists eslint 10 as a peer, and `eslint-plugin-react-hooks` only does from 7.1.1 (N, above T). Installing eslint 10 therefore breaks peer resolution, and the policy forbids `--legacy-peer-deps`. Meanwhile every 9.39.x release, including C, is deprecated. This needs your decision. typescript-eslint 8.73.0 accepts eslint 8.57, 9 and 10 and TypeScript `<6.1.0`, so it works with TypeScript 6.0.3 but C 8.18.0 (`typescript <5.8`) does not, so those two move together. The current lock already has `@eslint/js 9.17.0` beside `eslint 9.39.4`, a mismatch that exists on develop today.
- **Node-engine floors at T.** @commitlint 21.1.0 (>=22.12.0), jest-dom 7.0.1 (>=22), lint-staged 17.5.1 (>=22.22.1), jsdom 30.1.3 (`^22.22.2`), vitest 5.0.5 (`^22.12`). All satisfied by `node-version: "22"` in CI. They would reject Node 20 on a contributor's machine.

---

### 6. Changes applied

None. Report mode: the only file written is this report.

---

### 7. Gate results

| Side | Gate | Before | After |
|------|------|--------|-------|
| Backend | ruff / mypy / alembic check / pytest | not run: report mode on develop, working tree is on another branch | not run |
| Frontend | type-check / lint / test / build | not run: report mode on develop, working tree is on another branch | not run |

Every compatibility statement above comes from registry metadata. None of it was verified by running tests.

---

### 8. Decisions needed

1. **PyJWT 2.15.0** (above T 2.14.0, which still has two open advisories). Approve?
2. **OpenTelemetry api/sdk 1.45.2 with instrumentation 0.66b2** (above T), and **how to treat the beta-only `opentelemetry-instrumentation-fastapi`** (no stable release exists, so the "no pre-release" rule has no answer).
3. **zod 4.6.6 plus a newer @hookform/resolvers** (above T, two majors, likely form-code changes).
4. **Vite:** 6.4.5 or 6.4.6 as a security patch (below T, outside the N-1 line), or the full jump to 8.3.8 with plugin-react 6.2.1, vitest 5.0.5 and coverage-v8 5.0.5.
5. **pytest 9.x group** (pytest, pytest-asyncio, pytest-cov): major crossing, fixes the pytest advisory.
6. **0.x crossings:** fastapi (0.115 to 0.164), uvicorn (0.30 to 0.53), asyncpg (0.29 to 0.31), httpx (0.27 to 0.28), ruff (0.6 to 0.16). Approve one group at a time, as the policy says.
7. **Other major crossings:** redis (5 to 8), primereact (10 to 11), TypeScript (5.7 to 6.0), jsdom, lint-staged, @commitlint, globals, mypy, pre-commit, @types/node, jest-dom, and structlog (calver).
8. **ESLint:** no allowed target exists today (9.x deprecated, 10.x blocked by plugin peers). Options are to stay on deprecated 9.39.x, or wait for an `eslint-plugin-import` release that supports eslint 10.
9. **⏫ Ahead of N-1, kept unless you say otherwise:** react-redux 9.3.0, @testing-library/react 16.3.2, @testing-library/user-event 14.6.5, husky 9.1.7. I will not downgrade without a request.
10. **Range drift:** switch the eleven `^` ranges listed in section 3 to `~`?
11. **@types/node:** align with the Node 22 runtime instead of moving to 26.x typings?
12. **Platform:** Node 22 reaches end of life on 2027-04-30; Python 3.12, PostgreSQL 16 and the four GitHub Actions are 2 to 3 lines behind N-1 (not end of life). Whether and when to move is your call.
13. **Coverage gap:** run `npm audit` and a Python audit on a develop checkout to cover transitive dependencies, which this report did not query.

---

### Verdict

**ACTION REQUIRED ❌**

**Do first:**
- axios 1.18.0 to 1.20.0 (= T, clears 12 advisories, no major crossing).
- PyJWT 2.9.0 to 2.15.0 (needs approval, above T).
- Vite 6.4.3 to 6.4.5 or 6.4.6 (needs approval, patch in the current line).

**Next:**
- sqlalchemy 2.0.35 to 2.0.58; react and react-dom 19.2.9; @types/react 19.2.18; @types/react-dom 19.2.7 (patch updates).
- Minor steps: pydantic 2.13.5, pydantic-settings 2.15.0, alembic 1.19.2, bcrypt 4.3.0, boto3 and boto3-stubs 1.43.127, celery 5.6.3, @reduxjs/toolkit 2.14.0, @tanstack/react-query 5.107.2, react-hook-form 7.91.0, prettier 3.9.10, typescript-eslint 8.73.0 (together with a TypeScript decision).

**Needs your decision:**
- Everything in section 8: the open advisories above T (PyJWT, OpenTelemetry, zod), the fastapi and OpenTelemetry batch, the pytest group, the Vite and ESLint groups, major crossings, ahead-of-policy packages, range drift and platform upgrades.

"""
Architecture tests.

These assert the dependency rules the layout is built on, so a violation fails
the build instead of being spotted in review (or not at all). Pure static
analysis of import lines — no database, no app startup.
"""

from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"

# Encoding damage is what these guard against: a UTF-8 file read as Windows
# ANSI and re-saved becomes double-encoded, which round-trips back cleanly.
CP1252_REVERSE: dict[str, int] = {}
for _b in range(0x80, 0xA0):
    try:
        CP1252_REVERSE[bytes([_b]).decode("cp1252")] = _b
    except UnicodeDecodeError:
        CP1252_REVERSE[chr(_b)] = _b


def _import_lines(path: Path) -> list[tuple[int, str]]:
    """Every import statement in a file, as (line number, text)."""
    text = path.read_bytes().decode("utf-8-sig")
    return [
        (i, line.strip())
        for i, line in enumerate(text.splitlines(), 1)
        if line.strip().startswith(("import ", "from "))
    ]


def _python_files(*relative: str) -> list[Path]:
    return sorted(p for rel in relative for p in (SRC / rel).rglob("*.py"))


class TestLayerBoundaries:
    """
    Dependencies point inwards: domain <- application <- api/infrastructure.

    Controllers may wire concrete adapters, which is why the api layer is not
    covered by these rules.
    """

    def test_domain_does_not_import_outer_layers(self) -> None:
        offenders = [
            f"{path.relative_to(SRC)}:{lineno}  {line}"
            for path in _python_files("domain")
            for lineno, line in _import_lines(path)
            if "src.infrastructure" in line
            or "src.application" in line
            or "src.api" in line
            or "sqlalchemy" in line
            or "fastapi" in line
        ]
        assert not offenders, "domain must not depend on outer layers:\n" + "\n".join(
            offenders
        )

    def test_application_does_not_import_infrastructure_or_orm(self) -> None:
        """
        Services depend on domain ports, not on SQLAlchemy or ORM models.

        No exemptions: the only one this rule ever carried was `darwinbox_service`,
        which wrapped an external HTTP client directly. That feature has been
        removed, so the rule now applies to the whole application layer.
        """
        offenders = [
            f"{path.relative_to(SRC)}:{lineno}  {line}"
            for path in _python_files("application")
            for lineno, line in _import_lines(path)
            if "src.infrastructure" in line or "sqlalchemy" in line
        ]
        assert not offenders, (
            "application layer must not import infrastructure or the ORM:\n"
            + "\n".join(offenders)
        )


class TestControllerBoundaries:
    """
    Controllers wire adapters together; they do not talk to the database themselves.

    A controller (or its private helper functions) taking `AsyncSession` as a parameter
    is the same violation whether it then runs a query directly or only uses the
    session to build a repository/adapter inline (`XRepositoryImpl(session)`,
    `PermissionManager(session)`, `AuditService(session)`) instead of receiving that
    adapter through a `Depends()` factory. Either way, the controller now knows about
    persistence machinery it should not — see `.kiro/steering/api-layer-standard.md`.

    This is what closed the gap that let `employee_import_controller.py` run raw
    `select()`/`session.add()`/`session.flush()` directly in a route body, and what let
    other controllers construct `PermissionManager(session)` inline instead of
    depending on the `IPermissionResolver` port already available via
    `get_permission_resolver`.
    """

    def test_no_session_parameter_in_endpoints(self) -> None:
        offenders = [
            f"{path.relative_to(SRC)}:{lineno}  {line}"
            for path in _python_files("api/v1/endpoints")
            for lineno, line in _import_lines(path)
            if "sqlalchemy" in line
        ]
        assert not offenders, (
            "controllers must not import sqlalchemy or AsyncSession — depend on a "
            "repository/port from dependencies.py instead:\n" + "\n".join(offenders)
        )


class TestTransactionBoundaries:
    """
    Only the session module and the UnitOfWork may commit.

    Everything else either runs inside a request (where `get_db_session` commits
    once at the end) or goes through `UnitOfWork.commit()`. Repositories flush;
    they never commit. This is the rule that was previously broken by
    `rbac_service`, which committed seven times internally and so made each
    method its own transaction.
    """

    ALLOWED = {"session.py", "unit_of_work.py"}

    def test_only_session_and_unit_of_work_commit(self) -> None:
        offenders: list[str] = []
        for path in sorted(SRC.rglob("*.py")):
            if path.name in self.ALLOWED:
                continue
            text = path.read_bytes().decode("utf-8-sig")
            for lineno, line in enumerate(text.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if "session.commit()" in stripped or "_session.commit()" in stripped:
                    offenders.append(f"{path.relative_to(SRC)}:{lineno}  {stripped}")
        assert not offenders, (
            "only session.py and unit_of_work.py may commit; use UnitOfWork.commit() "
            "or let get_db_session commit at the end of the request:\n"
            + "\n".join(offenders)
        )


class TestSourceEncoding:
    """Guards against the double-encoding that mangled a file in this codebase."""

    @staticmethod
    def _to_ansi(text: str) -> bytes:
        out = bytearray()
        for ch in text:
            if ch in CP1252_REVERSE:
                out.append(CP1252_REVERSE[ch])
            elif ord(ch) < 0x100:
                out.append(ord(ch))
            else:
                raise UnicodeEncodeError("cp1252", ch, 0, 1, "not representable")
        return bytes(out)

    def test_no_double_encoded_lines(self) -> None:
        offenders: list[str] = []
        for path in sorted(SRC.rglob("*.py")):
            text = path.read_bytes().decode("utf-8-sig")
            for lineno, line in enumerate(text.splitlines(), 1):
                if line.isascii():
                    continue
                try:
                    if self._to_ansi(line).decode("utf-8") != line:
                        offenders.append(f"{path.relative_to(SRC)}:{lineno}")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    continue  # genuinely-encoded text cannot be reversed
        assert not offenders, (
            "these lines look double-encoded (UTF-8 read as cp1252, re-saved):\n"
            + "\n".join(offenders)
        )

    def test_sources_have_no_byte_order_mark(self) -> None:
        """
        Python assumes UTF-8, so a BOM adds nothing and causes real trouble: it
        broke an AST codemod during this work, and mixed encodings are what let a
        file become double-encoded in the first place. Keep the tree uniform.
        """
        offenders = [
            str(path.relative_to(SRC))
            for path in sorted(SRC.rglob("*.py"))
            if path.read_bytes().startswith(b"\xef\xbb\xbf")
        ]
        assert not offenders, (
            f"{len(offenders)} file(s) start with a UTF-8 BOM; save as UTF-8 "
            "without one:\n" + "\n".join(offenders)
        )

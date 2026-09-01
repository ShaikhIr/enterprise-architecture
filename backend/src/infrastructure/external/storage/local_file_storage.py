"""
Local-disk adapter for the file storage port.

The default backend, used when `STORAGE_BACKEND=local`: files are written beneath
`UPLOAD_DIR` (specifically `<UPLOAD_DIR>/files`, wired in the DI container) instead
of an S3 bucket. Same port as `S3FileStorage`, so a service depending on
`IFileStorage` neither knows nor cares which one is registered, and moving to S3
later is a one-line change in the container.

Two things worth calling out.

**Key safety.** An S3 key is a flat string, but on disk it becomes a real path,
so a `..` segment or a leading slash could escape the storage root and read or
clobber an arbitrary file. Every key is run through `validate_key` (which already
rejects those) and then re-checked after resolution to guarantee the final path
stays inside the base directory — defence in depth, since the two checks fail
closed independently.

**No presigned URLs.** Local disk has nothing analogous to S3's short-lived signed
URL, and inventing an app-served token here would be a second, weaker auth path to
maintain. `download_url` therefore raises, and the caller streams the bytes with
`stream` instead. Endpoints written against the port already have that path (the
guide's inline/streaming download); user-facing direct download is an S3-only
optimisation.
"""

import asyncio
import hashlib
from collections.abc import AsyncIterator, Callable, Mapping
from pathlib import Path
from typing import BinaryIO, TypeVar

from src.application.ports.file_storage import (
    DEFAULT_CHUNK_BYTES,
    IFileStorage,
    StorageUnavailableError,
    StoredFile,
    StoredFileNotFoundError,
)
from src.infrastructure.external.storage.storage_keys import validate_key

__all__ = ["LocalFileStorage"]

_T = TypeVar("_T")

#: Read this much per pass when hashing during `save`.
_DIGEST_CHUNK_BYTES = 1024 * 1024


class LocalFileStorage(IFileStorage):
    """Stores an application's files as plain files under a base directory."""

    def __init__(self, base_dir: Path) -> None:
        """
        Args:
            base_dir: Root for all stored files, e.g. `settings.storage_root /
                "files"`. Created on first write, not here, so constructing the
                adapter has no filesystem side effects.
        """
        self._base = base_dir.expanduser().resolve()

    # ── writing ───────────────────────────────────────────────────────────

    async def save(
        self,
        *,
        key: str,
        content: BinaryIO,
        content_type: str = "application/octet-stream",
        metadata: Mapping[str, str] | None = None,
    ) -> StoredFile:
        # `metadata` is accepted for port parity but not persisted: there is no
        # local equivalent of S3 user metadata, and the caller stores the
        # original name in its own database row regardless.
        target = self._resolve(key)

        def _write() -> tuple[int, str]:
            target.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            size = 0
            content.seek(0)
            # `.part` then atomic replace: a crash mid-write cannot leave a
            # truncated file at the real key that a later read would trust.
            tmp = target.with_suffix(target.suffix + ".part")
            with tmp.open("wb") as out:
                while chunk := content.read(_DIGEST_CHUNK_BYTES):
                    out.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
            content.seek(0)
            tmp.replace(target)
            return size, digest.hexdigest()

        try:
            size, sha256 = await asyncio.to_thread(_write)
        except OSError as exc:
            raise StorageUnavailableError(
                f"Could not write '{key}' under {self._base}: {exc}"
            ) from exc

        return StoredFile(
            key=key,
            size_bytes=size,
            sha256=sha256,
            content_type=content_type,
            # No ETag concept on disk; the sha256 above is the integrity check.
            etag="",
        )

    # ── reading ───────────────────────────────────────────────────────────

    async def read(self, key: str) -> bytes:
        target = self._resolve(key)

        def _read() -> bytes:
            try:
                return target.read_bytes()
            except FileNotFoundError:
                raise StoredFileNotFoundError(key) from None

        return await self._guard(_read, key=key)

    async def stream(
        self, key: str, chunk_bytes: int = DEFAULT_CHUNK_BYTES
    ) -> AsyncIterator[bytes]:
        target = self._resolve(key)

        def _open() -> BinaryIO:
            try:
                return target.open("rb")
            except FileNotFoundError:
                raise StoredFileNotFoundError(key) from None

        handle = await self._guard(_open, key=key)
        try:
            while True:
                chunk = await asyncio.to_thread(handle.read, chunk_bytes)
                if not chunk:
                    return
                yield chunk
        finally:
            await asyncio.to_thread(handle.close)

    async def download_url(
        self,
        key: str,
        *,
        expires_in: int | None = None,
        download_as: str | None = None,
    ) -> str:
        """
        Not supported on the local backend.

        Local disk cannot mint a short-lived, credential-free URL the way S3
        presigning does. Callers should stream the bytes (`stream`) when the
        `local` backend is in use; direct-download URLs are an S3-only path.
        """
        raise StorageUnavailableError(
            "The local storage backend cannot issue download URLs. Stream the "
            "file instead, or set STORAGE_BACKEND=s3 for presigned downloads."
        )

    # ── metadata and removal ──────────────────────────────────────────────

    async def exists(self, key: str) -> bool:
        target = self._resolve(key)
        return await asyncio.to_thread(target.is_file)

    async def delete(self, key: str) -> None:
        target = self._resolve(key)

        def _delete() -> None:
            # missing_ok=True: an already-absent file is success, matching the
            # port's idempotent-delete contract and S3's 204-on-missing.
            target.unlink(missing_ok=True)

        await self._guard(_delete, key=key)

    # ── internals ─────────────────────────────────────────────────────────

    def _resolve(self, key: str) -> Path:
        """
        Turn a validated key into an absolute path inside the base directory.

        `validate_key` already rejects leading slashes and `..` segments; the
        post-resolution containment check is a second, independent guard so that
        a path traversal cannot escape the root even if the first check is ever
        weakened.
        """
        validate_key(key)
        candidate = (self._base / key).resolve()
        if candidate != self._base and self._base not in candidate.parents:
            raise StorageUnavailableError(
                f"Refusing key '{key}': it resolves outside the storage root."
            )
        return candidate

    async def _guard(self, fn: Callable[[], _T], *, key: str) -> _T:
        """Run a blocking filesystem call, translating OS errors to the port's."""
        try:
            return await asyncio.to_thread(fn)
        except StoredFileNotFoundError:
            raise
        except OSError as exc:
            raise StorageUnavailableError(
                f"Local storage error for '{key}': {exc}"
            ) from exc

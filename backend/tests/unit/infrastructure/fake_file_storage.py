"""
In-memory IFileStorage for tests.

Fast, offline, and exercises the real port rather than a mock. Running the same
contract suite over this and `LocalFileStorage` (see `test_file_storage_contract.py`)
is what keeps the fake from drifting away from real behaviour — a fake that lies
is worse than no fake.
"""

import hashlib
from collections.abc import AsyncIterator, Mapping
from typing import BinaryIO

from src.application.ports.file_storage import (
    DEFAULT_CHUNK_BYTES,
    IFileStorage,
    StoredFile,
    StoredFileNotFoundError,
)

__all__ = ["FakeFileStorage"]


class FakeFileStorage(IFileStorage):
    """Holds objects in a dict. Not thread-safe; a test uses one per test."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def save(
        self,
        *,
        key: str,
        content: BinaryIO,
        content_type: str = "application/octet-stream",
        metadata: Mapping[str, str] | None = None,
    ) -> StoredFile:
        content.seek(0)
        data = content.read()
        content.seek(0)
        self.objects[key] = data
        return StoredFile(
            key=key,
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            content_type=content_type,
            etag="fake",
        )

    async def read(self, key: str) -> bytes:
        try:
            return self.objects[key]
        except KeyError:
            raise StoredFileNotFoundError(key) from None

    async def stream(
        self, key: str, chunk_bytes: int = DEFAULT_CHUNK_BYTES
    ) -> AsyncIterator[bytes]:
        # An async generator, matching the real adapters: calling `stream(...)`
        # returns the iterator directly, it is not awaited first.
        data = await self.read(key)
        for i in range(0, len(data), chunk_bytes):
            yield data[i : i + chunk_bytes]

    async def download_url(
        self,
        key: str,
        *,
        expires_in: int | None = None,
        download_as: str | None = None,
    ) -> str:
        if key not in self.objects:
            raise StoredFileNotFoundError(key)
        return f"https://fake.local/{key}"

    async def exists(self, key: str) -> bool:
        return key in self.objects

    async def delete(self, key: str) -> None:
        self.objects.pop(key, None)

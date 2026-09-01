"""
Shared IFileStorage contract, run over every non-S3 implementation.

The point of the port is that a caller cannot tell which adapter is behind it.
This suite pins the behaviour they all must share, and running it over both
`FakeFileStorage` and `LocalFileStorage` is what stops the in-memory fake used in
service tests from quietly diverging from the on-disk adapter that actually runs.

S3 is not exercised here: it needs a real bucket (see the s3-integration app's
`s3_check.py` / `smoke_test.py`), and mocking botocore would only assert the mock.
Adapter-specific behaviour that is *not* shared — local download_url raising, path
traversal rejection — lives in `test_local_file_storage.py`.
"""

import io
from collections.abc import Callable
from pathlib import Path

import pytest

from src.application.ports.file_storage import (
    IFileStorage,
    StoredFileNotFoundError,
)
from src.infrastructure.external.storage.local_file_storage import LocalFileStorage
from tests.unit.infrastructure.fake_file_storage import FakeFileStorage

# A factory per backend, so each test gets a fresh, isolated instance. Local is
# handed a tmp_path-rooted base dir; the fake needs nothing.
StorageFactory = Callable[[], IFileStorage]

KEY = "documents/42/abc123.pdf"


@pytest.fixture(params=["fake", "local"])
def storage(request: pytest.FixtureRequest, tmp_path: Path) -> IFileStorage:
    if request.param == "fake":
        return FakeFileStorage()
    return LocalFileStorage(tmp_path / "files")


async def _drain(storage: IFileStorage, key: str) -> bytes:
    return b"".join([chunk async for chunk in storage.stream(key)])


class TestSaveAndRead:
    async def test_saved_bytes_round_trip(self, storage: IFileStorage) -> None:
        stored = await storage.save(key=KEY, content=io.BytesIO(b"hello world"))

        assert stored.key == KEY
        assert stored.size_bytes == 11
        assert await storage.read(KEY) == b"hello world"

    async def test_save_reports_the_sha256_of_the_content(
        self, storage: IFileStorage
    ) -> None:
        # sha256("hello world") — computed independently of the adapter.
        expected = "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"

        stored = await storage.save(key=KEY, content=io.BytesIO(b"hello world"))

        assert stored.sha256 == expected

    async def test_save_overwrites_an_existing_key(self, storage: IFileStorage) -> None:
        await storage.save(key=KEY, content=io.BytesIO(b"first"))

        await storage.save(key=KEY, content=io.BytesIO(b"second"))

        assert await storage.read(KEY) == b"second"

    async def test_content_type_is_carried_on_the_result(
        self, storage: IFileStorage
    ) -> None:
        stored = await storage.save(
            key=KEY, content=io.BytesIO(b"%PDF-1.7"), content_type="application/pdf"
        )

        assert stored.content_type == "application/pdf"

    async def test_read_missing_key_raises_not_found(
        self, storage: IFileStorage
    ) -> None:
        with pytest.raises(StoredFileNotFoundError):
            await storage.read("documents/1/missing.pdf")


class TestStream:
    async def test_stream_reassembles_the_object(self, storage: IFileStorage) -> None:
        await storage.save(key=KEY, content=io.BytesIO(b"a" * 5000))

        assert await _drain(storage, KEY) == b"a" * 5000

    async def test_stream_respects_the_chunk_size(self, storage: IFileStorage) -> None:
        await storage.save(key=KEY, content=io.BytesIO(b"0123456789"))

        chunks = [chunk async for chunk in storage.stream(KEY, chunk_bytes=4)]

        assert chunks == [b"0123", b"4567", b"89"]

    async def test_stream_missing_key_raises_not_found(
        self, storage: IFileStorage
    ) -> None:
        with pytest.raises(StoredFileNotFoundError):
            await _drain(storage, "documents/1/missing.pdf")


class TestExists:
    async def test_exists_true_after_save(self, storage: IFileStorage) -> None:
        await storage.save(key=KEY, content=io.BytesIO(b"x"))

        assert await storage.exists(KEY) is True

    async def test_exists_false_for_absent_key(self, storage: IFileStorage) -> None:
        assert await storage.exists("documents/1/nope.pdf") is False


class TestDelete:
    async def test_delete_removes_the_object(self, storage: IFileStorage) -> None:
        await storage.save(key=KEY, content=io.BytesIO(b"x"))

        await storage.delete(KEY)

        assert await storage.exists(KEY) is False

    async def test_delete_is_idempotent(self, storage: IFileStorage) -> None:
        """Deleting an absent key is success — callers retry cleanup after failures."""
        await storage.delete("documents/1/never-existed.pdf")  # must not raise

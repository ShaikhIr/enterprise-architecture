"""
LocalFileStorage behaviour that is specific to the on-disk backend.

The shared port behaviour is covered in `test_file_storage_contract.py`. Here:
where files actually land under the base directory, the two ways local storage
deliberately differs from S3 (no presigned URL), and the path-traversal defence
that stops a crafted key from escaping the storage root — the reason the local
backend needs its own key check on top of `validate_key`.
"""

import io
from pathlib import Path

import pytest

from src.application.ports.file_storage import StorageUnavailableError
from src.infrastructure.external.storage.local_file_storage import LocalFileStorage

KEY = "documents/42/abc123.pdf"


@pytest.fixture
def base_dir(tmp_path: Path) -> Path:
    return tmp_path / "files"


@pytest.fixture
def storage(base_dir: Path) -> LocalFileStorage:
    return LocalFileStorage(base_dir)


class TestOnDiskLayout:
    async def test_file_lands_under_the_base_directory(
        self, storage: LocalFileStorage, base_dir: Path
    ) -> None:
        await storage.save(key=KEY, content=io.BytesIO(b"data"))

        written = base_dir / "documents" / "42" / "abc123.pdf"
        assert written.is_file()
        assert written.read_bytes() == b"data"

    async def test_constructing_the_adapter_creates_nothing(
        self, base_dir: Path
    ) -> None:
        """No filesystem side effects until the first write."""
        LocalFileStorage(base_dir)

        assert not base_dir.exists()

    async def test_no_part_file_left_after_a_successful_save(
        self, storage: LocalFileStorage, base_dir: Path
    ) -> None:
        await storage.save(key=KEY, content=io.BytesIO(b"data"))

        leftovers = list(base_dir.rglob("*.part"))
        assert leftovers == []


class TestDownloadUrlUnsupported:
    async def test_download_url_raises_on_local_backend(
        self, storage: LocalFileStorage
    ) -> None:
        await storage.save(key=KEY, content=io.BytesIO(b"data"))

        with pytest.raises(StorageUnavailableError):
            await storage.download_url(KEY)


class TestPathTraversalIsRefused:
    """`validate_key` rejects these first; the resolved-path guard is the backstop."""

    @pytest.mark.parametrize(
        "bad_key",
        [
            "../escape.pdf",
            "documents/../../etc/passwd",
            "/absolute/path.pdf",
            "documents//empty-segment.pdf",
        ],
    )
    async def test_rejects_keys_that_would_escape_the_root(
        self, storage: LocalFileStorage, bad_key: str
    ) -> None:
        with pytest.raises((StorageUnavailableError, ValueError)):
            await storage.save(key=bad_key, content=io.BytesIO(b"x"))

    async def test_no_file_is_written_outside_the_root(
        self, storage: LocalFileStorage, base_dir: Path, tmp_path: Path
    ) -> None:
        with pytest.raises((StorageUnavailableError, ValueError)):
            await storage.save(
                key="documents/../../pwned.pdf", content=io.BytesIO(b"x")
            )

        # Nothing landed outside base_dir (e.g. under tmp_path directly).
        assert not (tmp_path / "pwned.pdf").exists()

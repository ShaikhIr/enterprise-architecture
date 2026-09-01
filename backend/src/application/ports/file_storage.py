"""
File storage port.

Keeps boto3 out of the application layer, so services depend on "somewhere to put
bytes" rather than on S3. Two payoffs beyond tidiness: a service can be unit
tested against an in-memory implementation instead of a bucket or a mocking
library, and an app currently writing to `UPLOAD_DIR` on disk can move to S3 by
swapping the adapter registered in the container.

The interface is async because callers are async, but note that boto3 is a
blocking library. The adapter is responsible for keeping the event loop free
(see `S3FileStorage`); the port only promises that awaiting these methods will
not block it.

Downloads are deliberately expressed two ways. `download_url` hands the client a
presigned URL so the bytes travel from S3 to the browser directly, which is what
user-facing downloads should use. `read` and `stream` exist for the cases that
genuinely need the bytes server-side - virus scanning, parsing a spreadsheet,
generating a thumbnail.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import BinaryIO

__all__ = [
    "DEFAULT_CHUNK_BYTES",
    "IFileStorage",
    "StorageError",
    "StorageUnavailableError",
    "StoredFile",
    "StoredFileNotFoundError",
]

#: Default read size for `stream`. One MiB: few enough round trips for a large
#: object, small enough that peak memory does not depend on the object's size.
DEFAULT_CHUNK_BYTES = 1024 * 1024


class StorageError(Exception):
    """Base class for storage failures."""


class StoredFileNotFoundError(StorageError):
    """No object exists at that key."""

    def __init__(self, key: str) -> None:
        super().__init__(f"No stored file at '{key}'.")
        self.key = key


class StorageUnavailableError(StorageError):
    """
    The storage backend could not be reached, or refused the request.

    Separate from `StoredFileNotFoundError` because the two need different
    handling: a missing object is usually a 404 to the client, while an
    unreachable backend is a 503 and should page someone. Credential and
    permission failures land here too, since from the caller's point of view the
    backend is equally unusable.
    """


@dataclass(frozen=True)
class StoredFile:
    """The facts about an object that was just written."""

    key: str
    size_bytes: int
    #: Digest of the stored bytes, computed locally during `save`. Worth
    #: persisting: it makes a duplicate upload detectable, and lets a later
    #: integrity check be answered without a second download. Deliberately not
    #: the ETag, which is only an MD5 for single-part unencrypted uploads and is
    #: something else entirely for multipart or SSE-KMS objects.
    sha256: str
    content_type: str
    etag: str


class IFileStorage(ABC):
    """Somewhere to put an application's files."""

    @abstractmethod
    async def save(
        self,
        *,
        key: str,
        content: BinaryIO,
        content_type: str = "application/octet-stream",
        metadata: Mapping[str, str] | None = None,
    ) -> StoredFile:
        """
        Write `content` at `key`, overwriting anything already there.

        `content` must be seekable: the digest is computed in one pass and the
        stream is rewound before upload. Starlette's `UploadFile.file`, an open
        file and `io.BytesIO` all satisfy this.

        `metadata` values must be ASCII - they travel as HTTP headers. Store the
        original file name here, never in the key.

        Raises:
            StorageUnavailableError: If the backend rejected or dropped the write.
        """
        ...

    @abstractmethod
    async def read(self, key: str) -> bytes:
        """
        Return the whole object.

        Only for objects known to be small, since the result is fully in memory.
        Use `stream` otherwise.

        Raises:
            StoredFileNotFoundError: If nothing is stored at `key`.
            StorageUnavailableError: If the backend could not be reached.
        """
        ...

    @abstractmethod
    def stream(self, key: str, chunk_bytes: int = DEFAULT_CHUNK_BYTES) -> AsyncIterator[bytes]:
        """
        Yield the object in chunks.

        Suitable as the body of a `StreamingResponse` when the bytes really must
        pass through the application. Prefer `download_url` when they do not.

        Raises:
            StoredFileNotFoundError: If nothing is stored at `key`.
            StorageUnavailableError: If the backend could not be reached.
        """
        ...

    @abstractmethod
    async def download_url(
        self,
        key: str,
        *,
        expires_in: int | None = None,
        download_as: str | None = None,
    ) -> str:
        """
        A short-lived URL that grants read access to this one object.

        Lets the bucket stay private while a browser downloads directly from S3,
        so the application never proxies the bytes. `download_as` sets the
        filename the browser saves as, which is how a UUID key is presented to
        the user as `Q3 Report.pdf`.

        Anyone holding the URL can read the object until it expires, so keep the
        lifetime short and treat the URL itself as a credential: do not log it.

        Raises:
            StorageUnavailableError: If the URL could not be signed.
        """
        ...

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """
        Whether an object is stored at `key`.

        Raises:
            StorageUnavailableError: If the backend could not be reached. A clean
                "no such object" answer returns False rather than raising.
        """
        ...

    @abstractmethod
    async def delete(self, key: str) -> None:
        """
        Remove the object, treating an already-absent one as success.

        Idempotent because callers are usually cleaning up after a failure, and a
        retry of that cleanup must not itself fail.

        Raises:
            StorageUnavailableError: If the backend could not be reached.
        """
        ...

"""
S3 adapter for the file storage port.

Three things this module exists to contain.

**Blocking calls.** boto3 is synchronous, so every call is pushed to a worker
thread with `asyncio.to_thread`. Calling boto3 directly from an async handler
stalls the whole event loop for the duration of the network round trip, which
under load looks like the entire service hanging rather than one slow upload. The
client object itself is safe to share across threads, and is expensive to build,
so it is created once and reused.

**Error translation.** botocore raises one `ClientError` for everything and puts
the meaning in a string code. Callers should not be reading response dicts, so
that is mapped here to the port's exceptions - crucially separating "no such
object" from "backend unusable", because those are a 404 and a 503 respectively.

**Environment quirks.** Two defaults in modern boto3 fail on a network with a
TLS-inspecting proxy, and one makes presigned URLs unusable. See
`build_s3_client` for what and why. Getting these wrong produces failures that
look nothing like their cause, so they are set in one place rather than left to
each app to rediscover.
"""

import asyncio
import hashlib
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any, BinaryIO, Literal, cast

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.config import Config as BotoConfig
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
)

from src.application.ports.file_storage import (
    DEFAULT_CHUNK_BYTES,
    IFileStorage,
    StorageUnavailableError,
    StoredFile,
    StoredFileNotFoundError,
)
from src.infrastructure.external.storage.storage_keys import (
    safe_file_name,
    validate_key,
)

__all__ = ["S3StorageConfig", "S3FileStorage", "build_s3_client"]

#: Error codes that mean "the object or bucket is not there", as opposed to
#: "something is broken". `404` appears because HEAD requests carry no XML body,
#: so botocore can only surface the bare status.
_NOT_FOUND_CODES = frozenset({"404", "NoSuchKey", "NoSuchBucket"})

#: Read this much per `stream` chunk when hashing during `save`.
_DIGEST_CHUNK_BYTES = 1024 * 1024


@dataclass(frozen=True)
class S3StorageConfig:
    """
    Everything the adapter needs, decoupled from any settings framework.

    Built from the application's own `Settings` at wiring time, so this module
    does not import pydantic and can be reused as-is across apps.
    """

    bucket: str
    region: str
    access_key: str = ""
    secret_key: str = ""
    session_token: str = ""
    #: Set for MinIO, Wasabi, R2 or Ceph. Empty means real AWS.
    endpoint_url: str = ""
    #: Prepended to every key, so several apps can share one bucket without
    #: colliding and each can be granted an IAM policy scoped to its own prefix.
    key_prefix: str = ""
    #: Path to a PEM CA bundle, or empty for botocore's own.
    ca_bundle: str = ""
    #: "virtual" for AWS, "path" for most self-hosted gateways. Never "auto".
    addressing_style: str = ""
    #: "when_required" or "when_supported".
    checksum_mode: str = "when_supported"
    presign_expiry_seconds: int = 900
    #: Above this size, `save` switches to a multipart upload automatically.
    multipart_threshold_bytes: int = 16 * 1024 * 1024
    #: Set to "AES256" or "aws:kms" to require encryption on write. Leave empty
    #: when the bucket already enforces it by default, which is the better place
    #: for this to live.
    server_side_encryption: str = ""


def build_s3_client(config: S3StorageConfig) -> Any:
    """
    Create the one shared boto3 S3 client.

    Three settings here are not boto3 defaults, and each fixes a failure that is
    hard to diagnose from its symptom:

    `request_checksum_calculation`. Since boto3 1.36 this defaults to
    `when_supported`, which streams an upload body as `aws-chunked` with a
    trailing CRC32. Some proxies and S3-compatible gateways drop that request,
    so uploads die with `ConnectionClosedError` while every read call succeeds.
    `when_required` sends an ordinary `Content-Length` body instead.

    `addressing_style`. Under the default `auto`, `generate_presigned_url` emits
    the legacy global host `<bucket>.s3.amazonaws.com` while still signing for
    the bucket's real region. S3 recomputes the signature against the regional
    host it actually served and the URL fails with `SignatureDoesNotMatch`, even
    though the SDK's own calls all work. `virtual` keeps the two consistent.

    `verify`. botocore ignores the OS certificate store and trusts only its own
    bundled roots, so a TLS-inspecting corporate proxy fails with
    `CERTIFICATE_VERIFY_FAILED` where browsers are fine. Point this at a bundle
    that includes the internal root CA.

    Leave `access_key`/`secret_key` empty in any environment that can use an
    instance role, task role or OIDC federation. Static keys in config are the
    least safe option and the only one that needs rotating.
    """
    session = (
        boto3.Session(
            aws_access_key_id=config.access_key,
            aws_secret_access_key=config.secret_key,
            aws_session_token=config.session_token or None,
            region_name=config.region,
        )
        if config.access_key and config.secret_key
        else boto3.Session(region_name=config.region)
    )

    # These come from runtime config as `str`, but boto3's stubs type them as
    # closed literals. The values are constrained upstream (settings uses a
    # Literal for the checksum mode, and addressing_style resolves to one of
    # these three), so narrowing with `cast` at the boundary is honest rather
    # than lax — a wrong value would already have failed settings validation.
    style = cast(
        Literal["auto", "virtual", "path"],
        config.addressing_style or ("path" if config.endpoint_url else "virtual"),
    )
    checksum_mode = cast(
        Literal["when_supported", "when_required"], config.checksum_mode
    )

    return session.client(
        "s3",
        endpoint_url=config.endpoint_url or None,
        verify=config.ca_bundle or True,
        config=BotoConfig(
            signature_version="s3v4",
            s3={"addressing_style": style},
            request_checksum_calculation=checksum_mode,
            retries={"max_attempts": 3, "mode": "standard"},
            connect_timeout=10,
            read_timeout=60,
            # Default is 10. Uploads run on worker threads, so the pool has to
            # cover the concurrency the app actually reaches or requests queue
            # here invisibly.
            max_pool_connections=25,
        ),
    )


class S3FileStorage(IFileStorage):
    """Stores an application's files as S3 objects."""

    def __init__(self, client: Any, config: S3StorageConfig) -> None:
        self._client = client
        self._config = config
        self._transfer = TransferConfig(
            multipart_threshold=config.multipart_threshold_bytes,
            multipart_chunksize=config.multipart_threshold_bytes,
            # Sequential on purpose. The concurrency that matters is across
            # requests, and it is already provided by `to_thread`; letting each
            # upload fan out into more threads only makes pool exhaustion and
            # tail latency harder to reason about.
            use_threads=False,
        )

    # ── writing ───────────────────────────────────────────────────────────

    async def save(
        self,
        *,
        key: str,
        content: BinaryIO,
        content_type: str = "application/octet-stream",
        metadata: Mapping[str, str] | None = None,
    ) -> StoredFile:
        full_key = self._qualify(key)
        extra: dict[str, Any] = {"ContentType": content_type}
        if metadata:
            extra["Metadata"] = {k: _header_safe(v) for k, v in metadata.items()}
        if self._config.server_side_encryption:
            extra["ServerSideEncryption"] = self._config.server_side_encryption

        def _upload() -> tuple[int, str]:
            # Digest first, then rewind. Done in one pass over the stream rather
            # than by buffering it, so memory stays flat for a large upload. It
            # cannot be folded into the transfer itself: a multipart retry
            # re-reads parts, which would corrupt a running hash.
            digest = hashlib.sha256()
            size = 0
            content.seek(0)
            while chunk := content.read(_DIGEST_CHUNK_BYTES):
                digest.update(chunk)
                size += len(chunk)
            content.seek(0)

            self._client.upload_fileobj(
                content,
                self._config.bucket,
                full_key,
                ExtraArgs=extra,
                Config=self._transfer,
            )
            return size, digest.hexdigest()

        size, sha256 = await self._call(_upload, key=key)

        # Read the ETag back rather than guessing it. For a multipart or SSE-KMS
        # object it is not an MD5 of the content, so it is recorded only as an
        # opaque version marker; `sha256` above is the integrity check.
        head = await self._call(
            lambda: self._client.head_object(Bucket=self._config.bucket, Key=full_key),
            key=key,
        )

        return StoredFile(
            key=key,
            size_bytes=size,
            sha256=sha256,
            content_type=content_type,
            etag=(head.get("ETag") or "").strip('"'),
        )

    # ── reading ───────────────────────────────────────────────────────────

    async def read(self, key: str) -> bytes:
        full_key = self._qualify(key)

        def _get() -> bytes:
            response = self._client.get_object(Bucket=self._config.bucket, Key=full_key)
            with response["Body"] as body:
                data: bytes = body.read()
                return data

        # Bound to a typed local: `_call` is declared `-> Any` (it runs an
        # arbitrary callable), so returning its result directly would be an
        # implicit Any-return under strict mypy.
        result: bytes = await self._call(_get, key=key)
        return result

    async def stream(
        self, key: str, chunk_bytes: int = DEFAULT_CHUNK_BYTES
    ) -> AsyncIterator[bytes]:
        full_key = self._qualify(key)
        response = await self._call(
            lambda: self._client.get_object(Bucket=self._config.bucket, Key=full_key),
            key=key,
        )
        body = response["Body"]
        try:
            while True:
                # Each read is a socket read, so it goes to a thread too.
                chunk = await asyncio.to_thread(body.read, chunk_bytes)
                if not chunk:
                    return
                yield chunk
        finally:
            # Runs on GeneratorExit as well, so an abandoned download - a client
            # that closed the connection midway - still releases the connection
            # back to the pool instead of leaking it.
            await asyncio.to_thread(body.close)

    async def download_url(
        self,
        key: str,
        *,
        expires_in: int | None = None,
        download_as: str | None = None,
    ) -> str:
        full_key = self._qualify(key)
        params: dict[str, Any] = {"Bucket": self._config.bucket, "Key": full_key}
        if download_as:
            # Forces a save dialog with a readable name. Also stops the browser
            # rendering an uploaded HTML or SVG file inline, which on a shared
            # domain would be a stored-XSS vector.
            params["ResponseContentDisposition"] = (
                f'attachment; filename="{safe_file_name(download_as)}"'
            )

        url: str = await self._call(
            lambda: self._client.generate_presigned_url(
                "get_object",
                Params=params,
                ExpiresIn=expires_in or self._config.presign_expiry_seconds,
            ),
            key=key,
        )
        return url

    # ── metadata and removal ──────────────────────────────────────────────

    async def exists(self, key: str) -> bool:
        full_key = self._qualify(key)
        try:
            await self._call(
                lambda: self._client.head_object(
                    Bucket=self._config.bucket, Key=full_key
                ),
                key=key,
            )
        except StoredFileNotFoundError:
            return False
        return True

    async def delete(self, key: str) -> None:
        full_key = self._qualify(key)
        # S3 returns 204 whether or not the object was there, so this is already
        # idempotent; no existence check is needed first.
        await self._call(
            lambda: self._client.delete_object(Bucket=self._config.bucket, Key=full_key),
            key=key,
        )

    # ── internals ─────────────────────────────────────────────────────────

    def _qualify(self, key: str) -> str:
        """Validate the key and apply the configured prefix."""
        validate_key(key)
        prefix = self._config.key_prefix.strip("/")
        return f"{prefix}/{key}" if prefix else key

    async def _call(self, fn: Any, *, key: str) -> Any:
        """
        Run a blocking boto3 call on a worker thread, translating its errors.

        Every backend call goes through here so that no `ClientError` escapes to
        the application layer, and so there is one place that decides which
        failures mean "missing" and which mean "unusable".
        """
        try:
            return await asyncio.to_thread(fn)
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code in _NOT_FOUND_CODES:
                raise StoredFileNotFoundError(key) from exc
            raise StorageUnavailableError(
                f"S3 rejected the request for '{key}': {code or exc}"
            ) from exc
        except BotoCoreError as exc:
            # Connection, TLS, timeout and credential-resolution failures. The
            # object may well exist; the backend simply cannot be reached.
            raise StorageUnavailableError(
                f"Could not reach S3 for '{key}': {type(exc).__name__}: {exc}"
            ) from exc


def _header_safe(value: str) -> str:
    """
    Make a metadata value safe to send as an HTTP header.

    S3 user metadata travels in `x-amz-meta-*` headers, so a non-ASCII original
    file name would either be rejected or silently mangled. Folded here rather
    than at each call site, because the caller passing a file name should not have
    to know that it becomes a header.
    """
    return value.encode("ascii", "replace").decode("ascii").replace("\n", " ").strip()

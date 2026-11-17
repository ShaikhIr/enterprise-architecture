"""
Builds object keys, and refuses to build unsafe ones.

An S3 key is a flat string, not a path, but callers reach for it as though it
were one. Three habits cause real incidents, so key construction is centralised
here rather than left to each feature:

Using the uploaded file name as the key. Two users uploading `report.pdf`
silently overwrite each other, and `../` segments in a name supplied by a client
escape the prefix the IAM policy is scoped to. The stored key is always derived
from a UUID; the original name is carried as metadata and in the database row.

Letting the key be assembled with f-strings at each call site. The layout then
drifts, and a lifecycle rule or IAM prefix condition written against the old
shape quietly stops matching.

Leading slashes. `"/docs/x.pdf"` creates a key whose first character is a
slash, which displays in the console as an unnamed folder and breaks prefix
queries.
"""

import posixpath
import re
import unicodedata
import uuid
from pathlib import PurePosixPath

__all__ = [
    "MAX_KEY_BYTES",
    "InvalidStorageKeyError",
    "build_key",
    "safe_file_name",
    "validate_key",
]

#: S3's own limit on a key, in UTF-8 bytes.
MAX_KEY_BYTES = 1024

#: Anything outside this set is replaced in the display file name. Deliberately
#: narrow: it has to survive a Content-Disposition header, a Windows file system
#: and a URL without further escaping.
_UNSAFE_NAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")

_SAFE_SEGMENT = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]*\Z")


class InvalidStorageKeyError(ValueError):
    """A key was rejected before it reached S3."""


def safe_file_name(file_name: str | None, *, fallback: str = "file") -> str:
    """
    Reduce a user-supplied file name to something safe to echo back.

    This is for display and for `Content-Disposition`, never for the key itself.
    Accents are folded rather than stripped so that `résumé.pdf` stays legible as
    `resume.pdf` instead of collapsing to `.pdf`.
    """
    raw = (file_name or "").strip()
    # Take the last segment under both separators: a browser on Windows can send
    # a full path, and only the leaf is wanted.
    raw = raw.replace("\\", "/").rsplit("/", 1)[-1]

    folded = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode()
    stem = PurePosixPath(folded).stem
    suffix = PurePosixPath(folded).suffix

    stem = _UNSAFE_NAME_CHARS.sub("-", stem).strip("-._")
    suffix = _UNSAFE_NAME_CHARS.sub("", suffix)[:16]

    if not stem:
        stem = fallback
    # Leave room for the suffix within the display name.
    return f"{stem[:120]}{suffix}"


def build_key(*segments: str, file_name: str | None = None, prefix: str = "") -> str:
    """
    Compose a collision-proof key from trusted segments.

    Every segment must be something the application chose - a tenant slug, an
    entity name, a numeric id - never raw client input. The file name only
    contributes its extension, because the identity of the object is the UUID:

        build_key("documents", "42", file_name="Q3 Report.pdf",
                  prefix="compliance/prod")
        -> 'compliance/prod/documents/42/9f6c....pdf'

    Grouping by entity keeps `ListObjectsV2` cheap for "files attached to this
    record", and keeps a lifecycle or replication rule expressible as a prefix.

    Raises:
        InvalidStorageKeyError: If a segment is empty, contains a slash or a
            traversal sequence, or the finished key exceeds S3's length limit.
    """
    parts: list[str] = []

    for segment in (*prefix.strip("/").split("/"), *segments):
        piece = segment.strip().strip("/")
        if not piece:
            continue
        if not _SAFE_SEGMENT.match(piece):
            raise InvalidStorageKeyError(
                f"Key segment {segment!r} is not allowed. Segments must start "
                "with a letter or digit and contain only letters, digits, dots, "
                "hyphens and underscores."
            )
        parts.append(piece)

    if not parts:
        raise InvalidStorageKeyError("A key needs at least one segment.")

    suffix = PurePosixPath(safe_file_name(file_name)).suffix if file_name else ""
    parts.append(f"{uuid.uuid4().hex}{suffix}")

    return validate_key(posixpath.join(*parts))


def validate_key(key: str) -> str:
    """
    Assert a key is well formed, returning it unchanged.

    Worth calling on any key read back out of the database before it is handed to
    S3, so a row corrupted by an older code path fails loudly here instead of
    reaching for an object outside the prefix the IAM policy allows.

    Raises:
        InvalidStorageKeyError: If the key is empty, absolute, contains a
            traversal or empty segment, or is too long.
    """
    if not key or not key.strip():
        raise InvalidStorageKeyError("Key is empty.")
    if key.startswith("/"):
        raise InvalidStorageKeyError(f"Key {key!r} must not start with '/'.")
    if len(key.encode("utf-8")) > MAX_KEY_BYTES:
        raise InvalidStorageKeyError(
            f"Key is {len(key.encode('utf-8'))} bytes, over the "
            f"{MAX_KEY_BYTES} byte limit."
        )

    segments = key.split("/")
    if any(part in {"", ".", ".."} for part in segments):
        raise InvalidStorageKeyError(
            f"Key {key!r} contains an empty or traversal segment."
        )
    return key

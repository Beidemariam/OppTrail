"""Where an uploaded file goes, and what is allowed to be one.

Stood up by Phase F milestone F.5 before any endpoint accepted a file, so that
milestone 4.3 would wire a route into an already-tested module instead of
re-deriving size limits and path handling under feature pressure (brief §4.7).
`routes_attachments.py` is that route; everything about the bytes themselves is
decided here.

The guarantees, in order of what an attacker would try:

* the declared content type is never trusted -- the bytes are sniffed and must
  match one of `ALLOWED_UPLOAD_TYPES`, and the filename the client sent is
  display metadata that no control depends on;
* the stored path is **content-addressed** (ADR 0008):
  `{root}/{sha256[:2]}/{sha256}`, derived from the bytes and never from user
  input, so a name cannot carry a path, an extension the server executes, or a
  collision -- and two uploads of one document are one file on disk;
* a stored path is re-resolved and confirmed to sit in its own shard directly
  under the upload root, so neither a crafted digest nor a planted symlink can
  escape it;
* downloads are served as attachments with `nosniff`, so a file that slipped
  through can still not be rendered as HTML in the app's origin.

**Content addressing replaced F.5's random generated name** in milestone 4.3
(**D-147**). Both satisfy "the stored name carries nothing from the user"; the
digest additionally deduplicates, which is what ADR 0008 specifies and what a
random name cannot do.
"""

import hashlib
import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from fastapi import HTTPException, status

from .database import sqlite_path_from_url
from .settings import settings

# content type -> magic-byte prefixes. `text/plain` has no magic bytes and is
# validated by decoding instead; the three OOXML types share one signature and
# are told apart by what the archive contains (`_sniff_ooxml`).
ALLOWED_UPLOAD_TYPES: dict[str, tuple[bytes, ...]] = {
    "application/pdf": (b"%PDF-",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/gif": (b"GIF87a", b"GIF89a"),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (),
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": (),
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": (),
    "text/plain": (),
}

# A Word, Excel or PowerPoint file is a zip archive, so all three present the
# same magic bytes and the signature table above cannot separate them. The
# directory each format puts its parts in can (**D-150**, which is also where
# widening the allowlist to these three is argued): this is the one place
# sniffing reads past the first few bytes, and it reads the archive's index
# rather than its contents.
ZIP_SIGNATURE = b"PK\x03\x04"
OOXML_PART_PREFIXES: tuple[tuple[str, str], ...] = (
    ("word/", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ("xl/", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ("ppt/", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
)
# A macro-enabled document (`.docm` and its siblings) is a well-formed OOXML
# archive with executable code in it. Nothing here runs it -- the file is
# stored and streamed back -- but handing a colleague a document their Word has
# to warn them about is not what a proposal attachment is for, so it is refused
# rather than relabelled.
OOXML_MACRO_PART = "vbaproject.bin"

DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]")
CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f-\x9f]")
MAX_FILENAME_LENGTH = 255


@dataclass(frozen=True)
class StoredUpload:
    """What the caller persists: the digest that locates the file, the sniffed
    type, and the verified size."""

    sha256: str
    content_type: str
    size: int


def attachments_dir() -> Path:
    """Where the blobs live: `attachments/` beside the database file.

    Same shape as `backup.backup_dir()` and for the same reason (ADR 0008,
    ADR 0011) -- the container already mounts `/data` for the database, so an
    attachment survives a container recreate without a second mount, and the
    tests' per-test `tmp_path` database puts its blobs in that `tmp_path`
    without a fixture of their own.
    """
    if settings.attachments_dir:
        return Path(settings.attachments_dir).expanduser()
    return sqlite_path_from_url(settings.database_url).parent / "attachments"


def sniff_content_type(data: bytes) -> str | None:
    """Return the allowlisted content type the bytes actually are, or None."""
    for content_type, signatures in ALLOWED_UPLOAD_TYPES.items():
        if signatures and data.startswith(signatures):
            return content_type
    if data.startswith(ZIP_SIGNATURE):
        return _sniff_ooxml(data)
    if _is_plain_text(data):
        return "text/plain"
    return None


def _sniff_ooxml(data: bytes) -> str | None:
    """Which Office format this archive is, or None if it is not one.

    Only the central directory is read, never a member's contents, so a
    deliberately over-compressed archive cannot be expanded here -- and the
    bytes are already inside the size limit by the time this runs.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = archive.namelist()
    except zipfile.BadZipFile:
        return None

    if any(name.lower().endswith(OOXML_MACRO_PART) for name in names):
        return None
    for prefix, content_type in OOXML_PART_PREFIXES:
        if any(name.startswith(prefix) for name in names):
            return content_type
    return None


def _is_plain_text(data: bytes) -> bool:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return not any(character < " " and character not in "\t\r\n" for character in text)


def content_digest(data: bytes) -> str:
    """The file's identity: the SHA-256 of its bytes, lowercase hex."""
    return hashlib.sha256(data).hexdigest()


def validate_upload(data: bytes) -> StoredUpload:
    """Enforce the size limit and the sniffed-type allowlist, then address the
    file by its content.

    Raises 413 for an oversized upload and 415 for a type that is not on the
    allowlist -- including a file whose bytes disagree with what was declared,
    since the declaration is not consulted at all.
    """
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File exceeds the {settings.max_upload_bytes} byte upload limit",
        )

    content_type = sniff_content_type(data)
    if content_type is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported file type",
        )

    return StoredUpload(
        sha256=content_digest(data),
        content_type=content_type,
        size=len(data),
    )


def safe_filename(filename: str) -> str:
    """The name to record, trimmed of everything that makes a name a path.

    The filesystem never sees this -- the stored path is the digest -- so this
    is not a containment control: it is what stops a crafted name being
    rendered as a path by whatever reads it back (an export, a download
    header, a reader's own file manager). Only the last segment survives, so
    `../../etc/passwd` is recorded as `passwd`.
    """
    trimmed = filename.replace("\\", "/").rsplit("/", 1)[-1].strip().lstrip(".")
    # Every control character, not only NUL (milestone 4.7, **D-158**): a
    # filename is the one attacker-controlled string this app puts on a
    # structural line -- a download header, a PDF row, and now the AI's
    # context -- and an interior newline is what lets one forge a line there.
    # An allowlist on characters is deterministic and testable; a denylist on
    # suspicious phrases, which is what "scan the filename" would mean, is
    # neither.
    trimmed = CONTROL_CHARACTERS.sub("", trimmed)[:MAX_FILENAME_LENGTH].strip()
    return trimmed or "upload"


def resolve_stored_path(root: Path, sha256: str) -> Path:
    """Resolve a digest to its path inside `root`, rejecting anything that
    escapes it.

    Two independent checks, because either alone has a hole: the pattern
    rejects separators, `..` and anything that is not a 64-character hex digest
    before the filesystem sees them, and the resolved-parent check catches a
    shard directory that is itself a symlink out of the tree.
    """
    if not DIGEST_PATTERN.match(sha256):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid stored file name",
        )

    resolved_root = root.resolve()
    candidate = (resolved_root / sha256[:2] / sha256).resolve()
    if candidate.parent.parent != resolved_root or candidate.parent.name != sha256[:2]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid stored file name",
        )
    return candidate


def store_bytes(root: Path, upload: StoredUpload, data: bytes) -> Path:
    """Write the file at its content address, or leave the existing one alone.

    Identical bytes are one file on disk however many attachment rows point at
    it, which is the whole point of addressing by content -- and it makes a
    re-upload after a failed request idempotent rather than a second copy.
    """
    path = resolve_stored_path(root, upload.sha256)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(data)
    return path


def download_headers(filename: str, content_type: str) -> dict[str, str]:
    """Force a download rather than inline rendering, and keep the original
    filename intact for the user via RFC 5987 while sending an ASCII fallback
    that cannot break out of the quoted string.
    """
    fallback = UNSAFE_FILENAME_CHARS.sub("_", filename) or "download"
    encoded = quote(filename, safe="")
    return {
        "Content-Type": content_type,
        "Content-Disposition": f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{encoded}",
        "X-Content-Type-Options": "nosniff",
    }

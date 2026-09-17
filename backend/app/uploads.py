"""Upload hardening (brief §4.5).

No endpoint accepts a file yet — attachments are a Phase 4 roadmap item. The
rules live here now so that milestone wires an endpoint into an already-tested
module instead of reinventing size limits and path handling under feature
pressure, which is what brief §4.7 asks Phase F to do.

The guarantees, in order of what an attacker would try:

* the declared content type is never trusted — the bytes are sniffed and must
  match one of `ALLOWED_UPLOAD_TYPES`;
* the stored filename is generated, never derived from user input, so a name
  cannot carry a path, an extension the server executes, or a collision;
* a stored path is re-resolved and confirmed to sit directly under the upload
  root, so a crafted name cannot escape it;
* downloads are served as attachments with `nosniff`, so a file that slipped
  through can still not be rendered as HTML in the app's origin.
"""

import re
import secrets
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from fastapi import HTTPException, status

from .settings import settings

# content type -> (extension, magic-byte prefixes). `text/plain` has no magic
# bytes and is validated by decoding instead.
ALLOWED_UPLOAD_TYPES: dict[str, tuple[str, tuple[bytes, ...]]] = {
    "application/pdf": ("pdf", (b"%PDF-",)),
    "image/png": ("png", (b"\x89PNG\r\n\x1a\n",)),
    "image/jpeg": ("jpg", (b"\xff\xd8\xff",)),
    "image/gif": ("gif", (b"GIF87a", b"GIF89a")),
    "text/plain": ("txt", ()),
}
STORED_NAME_PATTERN = re.compile(r"^[0-9a-f]{32}\.[a-z0-9]{1,8}$")
UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]")


@dataclass(frozen=True)
class StoredUpload:
    """What the caller persists: generated name, sniffed type, verified size."""

    stored_name: str
    content_type: str
    size: int


def sniff_content_type(data: bytes) -> str | None:
    """Return the allowlisted content type the bytes actually are, or None."""
    for content_type, (_, signatures) in ALLOWED_UPLOAD_TYPES.items():
        if signatures and data.startswith(signatures):
            return content_type
    if _is_plain_text(data):
        return "text/plain"
    return None


def _is_plain_text(data: bytes) -> bool:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return not any(character < " " and character not in "\t\r\n" for character in text)


def random_stored_name(content_type: str) -> str:
    extension, _ = ALLOWED_UPLOAD_TYPES[content_type]
    return f"{secrets.token_hex(16)}.{extension}"


def validate_upload(data: bytes) -> StoredUpload:
    """Enforce the size limit and the sniffed-type allowlist, then name the file.

    Raises 413 for an oversized upload and 415 for a type that is not on the
    allowlist — including a file whose bytes disagree with what was declared,
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
        stored_name=random_stored_name(content_type),
        content_type=content_type,
        size=len(data),
    )


def resolve_stored_path(root: Path, stored_name: str) -> Path:
    """Resolve `stored_name` inside `root`, rejecting anything that escapes it.

    Two independent checks, because either alone has a hole: the pattern rejects
    separators and `..` before the filesystem sees them, and the resolved-parent
    check catches a root that is itself a symlink out of the tree.
    """
    if not STORED_NAME_PATTERN.match(stored_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid stored file name",
        )

    resolved_root = root.resolve()
    candidate = (resolved_root / stored_name).resolve()
    if candidate.parent != resolved_root:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid stored file name",
        )
    return candidate


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

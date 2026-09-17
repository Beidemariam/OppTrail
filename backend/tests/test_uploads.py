"""Upload hardening (brief §4.5).

No endpoint accepts a file yet — `app/uploads.py` explains why the rules exist
before the Phase 4 feature does. These tests are what make that module safe to
wire up later without re-deriving the argument.
"""

from pathlib import Path

import pytest
from fastapi import HTTPException

from app.settings import settings
from app.uploads import (
    STORED_NAME_PATTERN,
    download_headers,
    random_stored_name,
    resolve_stored_path,
    sniff_content_type,
    validate_upload,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
PDF = b"%PDF-1.7\n" + b"0" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
GIF = b"GIF89a" + b"\x00" * 32


@pytest.fixture
def small_limit():
    original = settings.max_upload_bytes
    settings.max_upload_bytes = 64
    yield
    settings.max_upload_bytes = original


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (PNG, "image/png"),
        (PDF, "application/pdf"),
        (JPEG, "image/jpeg"),
        (GIF, "image/gif"),
        (b"just some notes\n", "text/plain"),
    ],
)
def test_sniffing_identifies_allowed_types(data: bytes, expected: str) -> None:
    assert sniff_content_type(data) == expected


@pytest.mark.parametrize(
    "data",
    [
        b"MZ\x90\x00\x03",  # a Windows executable
        b"\x7fELF\x02\x01",  # a Linux executable
        b"\x00\x01\x02\x03",  # binary with no recognised signature
    ],
)
def test_sniffing_rejects_everything_else(data: bytes) -> None:
    assert sniff_content_type(data) is None


def test_the_declared_content_type_is_never_trusted() -> None:
    """An executable renamed `report.pdf` and posted as `application/pdf` is
    still an executable. `validate_upload` takes no declared type at all.
    """
    with pytest.raises(HTTPException) as excinfo:
        validate_upload(b"MZ\x90\x00 pretending to be a PDF")

    assert excinfo.value.status_code == 415


def test_an_oversized_upload_is_rejected(small_limit: None) -> None:
    with pytest.raises(HTTPException) as excinfo:
        validate_upload(PNG + b"\x00" * 128)

    assert excinfo.value.status_code == 413


def test_a_valid_upload_is_given_a_random_name_and_its_sniffed_type() -> None:
    first = validate_upload(PNG)
    second = validate_upload(PNG)

    assert first.content_type == "image/png"
    assert first.size == len(PNG)
    assert first.stored_name.endswith(".png")
    assert STORED_NAME_PATTERN.match(first.stored_name)
    assert first.stored_name != second.stored_name


def test_the_stored_name_carries_nothing_from_the_user() -> None:
    """The original filename never reaches the filesystem, so a name cannot
    smuggle a path, a double extension, or a shell metacharacter.
    """
    assert STORED_NAME_PATTERN.match(random_stored_name("application/pdf"))


@pytest.mark.parametrize(
    "stored_name",
    [
        "../../etc/passwd",
        "..",
        "sub/dir/file.png",
        "/etc/passwd",
        "file.png\x00.txt",
        "%2e%2e%2ffile.png",
        "",
    ],
)
def test_traversal_attempts_are_rejected(tmp_path: Path, stored_name: str) -> None:
    with pytest.raises(HTTPException) as excinfo:
        resolve_stored_path(tmp_path, stored_name)

    assert excinfo.value.status_code == 400


def test_a_generated_name_resolves_inside_the_upload_root(tmp_path: Path) -> None:
    stored_name = random_stored_name("image/png")

    path = resolve_stored_path(tmp_path, stored_name)

    assert path.parent == tmp_path.resolve()
    assert path.name == stored_name


def test_a_symlink_planted_in_the_upload_root_is_rejected(tmp_path: Path) -> None:
    """The stored-name pattern cannot catch this one: the name is well formed
    and the escape happens in the filesystem, which is why `resolve_stored_path`
    checks the resolved parent as well.
    """
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "uploads"
    root.mkdir()
    stored_name = random_stored_name("image/png")
    (root / stored_name).symlink_to(outside / stored_name)

    with pytest.raises(HTTPException) as excinfo:
        resolve_stored_path(root, stored_name)

    assert excinfo.value.status_code == 400


def test_downloads_are_forced_and_never_sniffed() -> None:
    headers = download_headers("quarterly report.pdf", "application/pdf")

    assert headers["Content-Disposition"].startswith("attachment; ")
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Content-Type"] == "application/pdf"


def test_a_hostile_filename_cannot_break_the_disposition_header() -> None:
    headers = download_headers('e"vil\r\n.txt', "text/plain")
    disposition = headers["Content-Disposition"]

    assert '"e_vil__.txt"' in disposition
    assert "\r" not in disposition and "\n" not in disposition
    # The original is still recoverable by the browser, percent-encoded.
    assert "filename*=UTF-8''e%22vil%0D%0A.txt" in disposition


def test_a_non_ascii_filename_survives_as_rfc_5987() -> None:
    headers = download_headers("réunion.pdf", "application/pdf")

    assert 'filename="r_union.pdf"' in headers["Content-Disposition"]
    assert "filename*=UTF-8''r%C3%A9union.pdf" in headers["Content-Disposition"]

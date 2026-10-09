"""The upload rules themselves (brief §4.5, ADR 0008).

`app/uploads.py` was written in Phase F before any endpoint accepted a file;
milestone 4.3 is the route that uses it (`tests/test_attachments.py`). These
tests are the unit half: what counts as an allowed file, where its bytes go,
and what a hostile name can and cannot do. They outlived the module's own
rewrite -- content addressing replaced the random generated name (**D-147**) --
which is what they existed for.
"""

import io
import zipfile
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.settings import settings
from app.uploads import (
    DIGEST_PATTERN,
    attachments_dir,
    content_digest,
    download_headers,
    resolve_stored_path,
    safe_filename,
    sniff_content_type,
    store_bytes,
    validate_upload,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
PDF = b"%PDF-1.7\n" + b"0" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
GIF = b"GIF89a" + b"\x00" * 32

DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PPTX_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def ooxml(*parts: str) -> bytes:
    """A minimal Office document: the parts a real one carries, and nothing else.

    The sniffer reads the archive's index rather than its contents, so the
    member bodies are irrelevant -- which is also why this fixture is three
    lines instead of a checked-in binary.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        for part in parts:
            archive.writestr(part, "x")
    return buffer.getvalue()


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
        (ooxml("word/document.xml"), DOCX_TYPE),
        (ooxml("xl/workbook.xml"), XLSX_TYPE),
        (ooxml("ppt/presentation.xml"), PPTX_TYPE),
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
        b"PK\x03\x04 not really a zip",  # the OOXML signature, and no archive
    ],
)
def test_sniffing_rejects_everything_else(data: bytes) -> None:
    assert sniff_content_type(data) is None


def test_a_plain_zip_is_not_an_office_document() -> None:
    """The three OOXML types share one signature, so the archive's index is
    what separates them -- and a zip of holiday photos is none of them."""
    assert sniff_content_type(ooxml("photos/beach.jpg")) is None


def test_a_macro_enabled_document_is_refused() -> None:
    """A `.docm` is a well-formed Word archive with executable code in it.
    Nothing here runs it, but handing a colleague a document their Word has to
    warn them about is not what a proposal attachment is for."""
    assert sniff_content_type(ooxml("word/document.xml", "word/vbaProject.bin")) is None


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


def test_a_valid_upload_is_addressed_by_its_content() -> None:
    first = validate_upload(PNG)
    second = validate_upload(PNG)

    assert first.content_type == "image/png"
    assert first.size == len(PNG)
    assert DIGEST_PATTERN.match(first.sha256)
    # The same bytes are the same file (ADR 0008), which is what a random
    # generated name could not express (**D-147**).
    assert first.sha256 == second.sha256
    assert first.sha256 != validate_upload(PDF).sha256


def test_the_stored_path_carries_nothing_from_the_user(tmp_path: Path) -> None:
    """The original filename never reaches the filesystem, so a name cannot
    smuggle a path, a double extension, or a shell metacharacter: the path is
    the digest, sharded by its first two characters.
    """
    digest = content_digest(PDF)

    path = resolve_stored_path(tmp_path, digest)

    assert path.parent == tmp_path.resolve() / digest[:2]
    assert path.name == digest


@pytest.mark.parametrize(
    "sha256",
    [
        "../../etc/passwd",
        "..",
        "sub/dir/file.png",
        "/etc/passwd",
        "%2e%2e%2ffile.png",
        "",
        # Well-formed in shape but not a digest: too short, uppercase, and a
        # digest with a path glued onto it.
        "abc123",
        content_digest(PDF).upper(),
        f"{content_digest(PDF)}/../../escape",
    ],
)
def test_traversal_attempts_are_rejected(tmp_path: Path, sha256: str) -> None:
    with pytest.raises(HTTPException) as excinfo:
        resolve_stored_path(tmp_path, sha256)

    assert excinfo.value.status_code == 400


def test_a_symlink_planted_in_the_upload_root_is_rejected(tmp_path: Path) -> None:
    """The digest pattern cannot catch this one: the name is well formed and
    the escape happens in the filesystem, which is why `resolve_stored_path`
    checks the resolved parent as well.
    """
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "uploads"
    root.mkdir()
    digest = content_digest(PNG)
    (root / digest[:2]).symlink_to(outside)

    with pytest.raises(HTTPException) as excinfo:
        resolve_stored_path(root, digest)

    assert excinfo.value.status_code == 400


def test_storing_the_same_bytes_twice_writes_one_file(tmp_path: Path) -> None:
    upload = validate_upload(PDF)

    first = store_bytes(tmp_path, upload, PDF)
    second = store_bytes(tmp_path, upload, PDF)

    assert first == second
    assert first.read_bytes() == PDF
    assert [path.name for path in sorted(tmp_path.rglob("*")) if path.is_file()] == [upload.sha256]


def test_the_attachment_directory_sits_beside_the_database(tmp_path: Path) -> None:
    """ADR 0008's layout: the blobs live under the same `/data` volume as the
    database they belong to, so they survive a container recreate without a
    second mount -- and a test's `tmp_path` database puts them in `tmp_path`.
    """
    original = settings.database_url
    settings.database_url = f"sqlite:///{tmp_path / 'app.db'}"
    try:
        assert attachments_dir() == tmp_path / "attachments"
    finally:
        settings.database_url = original


def test_an_explicit_attachment_directory_wins(tmp_path: Path) -> None:
    original = settings.attachments_dir
    settings.attachments_dir = str(tmp_path / "elsewhere")
    try:
        assert attachments_dir() == tmp_path / "elsewhere"
    finally:
        settings.attachments_dir = original


@pytest.mark.parametrize(
    ("sent", "recorded"),
    [
        ("../../etc/passwd", "passwd"),
        ("C:\\Users\\sam\\proposal.pdf", "proposal.pdf"),
        (".hidden", "hidden"),
        ("", "upload"),
        ("   ", "upload"),
        ("quarterly report.pdf", "quarterly report.pdf"),
        # Milestone 4.7: a filename is the one attacker-controlled string this
        # app puts on a structural line -- a download header, a row in the PDF,
        # a line of the AI's context -- so an interior newline, which would
        # forge one, is removed rather than escaped per destination.
        ("proposal\nAuthor: Admin.pdf", "proposalAuthor: Admin.pdf"),
        ("report\r\n\tdraft.pdf", "reportdraft.pdf"),
        ("\x1b]0;title\x07.pdf", "]0;title.pdf"),
    ],
)
def test_the_recorded_filename_is_never_a_path(sent: str, recorded: str) -> None:
    """The filesystem never sees this name -- the path is the digest -- so this
    is not a containment control. It is what stops a crafted name being
    rendered as a path by whatever reads it back."""
    assert safe_filename(sent) == recorded


def test_a_recorded_filename_is_bounded() -> None:
    assert len(safe_filename("a" * 400 + ".pdf")) == 255


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

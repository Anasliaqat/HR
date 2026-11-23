"""Content checks for uploaded CVs, beyond trusting the file extension."""

import io
import zipfile

MAX_UNCOMPRESSED_DOCX_BYTES = 50 * 1024 * 1024


class UnsafeUploadError(ValueError):
    """The file content does not match its extension or looks unsafe."""


def validate_resume_content(content: bytes, extension: str) -> None:
    """Raise UnsafeUploadError unless the bytes really are a PDF, DOCX or plain text file."""
    if extension == ".pdf":
        if not content.lstrip()[:5] == b"%PDF-":
            raise UnsafeUploadError("This file is not a valid PDF.")
    elif extension == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                names = set(archive.namelist())
                if "word/document.xml" not in names:
                    raise UnsafeUploadError("This file is not a valid Word (.docx) document.")
                # Refuse zip bombs: a small upload that expands to something huge.
                if sum(info.file_size for info in archive.infolist()) > MAX_UNCOMPRESSED_DOCX_BYTES:
                    raise UnsafeUploadError("This Word document is too large once opened.")
        except zipfile.BadZipFile as exc:
            raise UnsafeUploadError("This file is not a valid Word (.docx) document.") from exc
    elif extension == ".txt":
        if b"\x00" in content:
            raise UnsafeUploadError("This file is not a plain text resume.")
        try:
            content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise UnsafeUploadError("Text resumes must be UTF-8 encoded.") from exc
    else:
        raise UnsafeUploadError("Unsupported resume format.")

"""Extract resume text and a conservative, section-based candidate profile."""

import re
from zipfile import BadZipFile
from pathlib import Path
from typing import Literal

from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from pydantic import BaseModel, Field
from pypdf import PdfReader
from pypdf.errors import PdfReadError, PdfStreamError


class ResumeProfile(BaseModel):
    summary: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    experience: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)

    @property
    def work_experience_text(self) -> str:
        return "\n".join(self.experience)

    @property
    def project_text(self) -> str:
        return "\n".join(self.projects)


Section = Literal[
    "summary",
    "skills",
    "education",
    "experience",
    "projects",
    "certifications",
]
_SECTION_HEADINGS: dict[Section, re.Pattern[str]] = {
    "summary": re.compile(
        r"^(?:(?:professional\s+)?summary|profile|career\s+objective)"
        r"(?:\s*[:|\-]\s*(.*))?$",
        re.I,
    ),
    "skills": re.compile(
        r"^(?:(?:technical\s+)?skills(?:\s+and\s+tools)?|core\s+strengths|"
        r"ai\s*/?\s*ml|machine\s+learning|programming|programming\s+languages|"
        r"databases?|development|tools|technologies|technical\s+stack|"
        r"frameworks?|libraries|platforms)"
        r"(?:\s*[:|\-]\s*(.*))?$",
        re.I,
    ),
    "education": re.compile(
        r"^(?:education|academic\s+background)(?:\s*[:|\-]\s*(.*))?$", re.I
    ),
    "experience": re.compile(
        r"^(?:(?:work\s+)?(?:professional\s+)?experience|employment\s+history)"
        r"(?:\s*[:|\-]\s*(.*))?$",
        re.I,
    ),
    "projects": re.compile(
        r"^(?:(?:selected\s+)?projects?|project\s+experience)"
        r"(?:\s*[:|\-]\s*(.*))?$",
        re.I,
    ),
    "certifications": re.compile(
        r"^(?:certifications?|licenses?\s+and\s+certifications?|training)"
        r"(?:\s*[:|\-]\s*(.*))?$",
        re.I,
    ),
}
_UNTRUSTED_OR_SENSITIVE_LINE = re.compile(
    r"(?:ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions|"
    r"system\s+prompt\s*:|developer\s+message\s*:|"
    r"\b(?:age|date\s+of\s+birth|dob|gender|sex|race|ethnicity|religion|"
    r"marital\s+status|nationality|national\s+origin|accent|disability)\s*:)",
    re.I,
)


def extract_text(file_path: str | Path) -> str:
    """Extract text from a supported resume file; reject unreadable or empty files."""
    path = Path(file_path)
    extension = path.suffix.lower()
    if extension == ".pdf":
        try:
            text = "\n".join(
                page.extract_text() or "" for page in PdfReader(path).pages
            )
        except (PdfReadError, PdfStreamError, OSError) as exc:
            raise ValueError("The PDF resume could not be read") from exc
    elif extension == ".docx":
        try:
            document = Document(path)
        except (BadZipFile, PackageNotFoundError, OSError) as exc:
            raise ValueError("The DOCX resume could not be read") from exc
        paragraphs = [paragraph.text for paragraph in document.paragraphs]
        for table in document.tables:
            paragraphs.extend(cell.text for row in table.rows for cell in row.cells)
        text = "\n".join(paragraphs)
    elif extension == ".txt":
        text = path.read_text(encoding="utf-8-sig")
    else:
        raise ValueError(f"Unsupported resume format: {extension or 'unknown'}")

    cleaned = "\n".join(
        line.strip()
        for line in text.splitlines()
        if line.strip() and not _UNTRUSTED_OR_SENSITIVE_LINE.search(line)
    )
    if not cleaned:
        if extension == ".pdf":
            raise ValueError(
                "No readable text was found in the PDF. Scanned or image-only "
                "resumes require OCR before upload."
            )
        raise ValueError("No readable text was found in the resume")
    return cleaned


def extract_profile(text: str) -> ResumeProfile:
    """Collect factual lines under recognizable CV headings without inferring identity."""
    profile = ResumeProfile()
    current: Section | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip().lstrip("•*- \t")
        if not line or _UNTRUSTED_OR_SENSITIVE_LINE.search(line):
            continue
        heading_match = next(
            (
                (section, match)
                for section, pattern in _SECTION_HEADINGS.items()
                if (match := pattern.match(line))
            ),
            None,
        )
        if heading_match:
            heading, match = heading_match
            current = heading
            line = (match.group(1) or "").strip()
            if not line:
                continue
        if current is None:
            continue

        values = getattr(profile, current)
        if current == "skills":
            values.extend(
                item.strip()
                for item in re.split(r"[,;|]", line)
                if item.strip()
            )
        else:
            values.append(line)

    for section in (
        "summary",
        "skills",
        "education",
        "experience",
        "projects",
        "certifications",
    ):
        values = getattr(profile, section)
        setattr(profile, section, list(dict.fromkeys(values)))
    return profile

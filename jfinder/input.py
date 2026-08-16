"""Locate, read and validate the abstract input (AGENTS.md §6).

Priority: --text, then --file, then abstract.md / abstract.txt / ABSTRACT.md
in the working directory (or the given path).
"""

from __future__ import annotations

import re
from pathlib import Path

from jfinder.data import JfinderError

#: Search order in a directory when no explicit file is given (AGENTS.md §6).
SEARCH_ORDER: tuple[str, ...] = ("abstract.md", "abstract.txt", "ABSTRACT.md")
MIN_WORDS = 60
MAX_WORDS_SOFT = 900

_PLACEHOLDER_RE = re.compile(r"<[^>]+>")
_TEXT_SUFFIXES = {".md", ".txt", ".tex", ".rst"}

ABSTRACT_TEMPLATE = """# Title
<your study title>

# Abstract
<200-300 words: purpose, methods, findings, conclusion>

# Keywords
<comma-separated, 4-8>

# Study type
<e.g. methods paper / RCT / retrospective cohort / review / case report>

# Notes (optional)
<target audience, language constraints, time pressure, publishers to avoid>
"""


class InputError(JfinderError):
    """Abstract input is missing or invalid."""


def locate(path: Path) -> Path:
    """Find abstract.md (or .txt / ABSTRACT.md) inside path (AGENTS.md §6)."""
    directory = path if path.is_dir() else path.parent
    for name in SEARCH_ORDER:
        candidate = directory / name
        if candidate.is_file():
            return candidate
    raise InputError(
        f"No abstract.md found in {directory}.\n\n"
        "  Create:  jfinder init\n"
        "  Or:      jfinder find -f path/to/abstract.txt"
    )


def read_any(path: Path) -> str:
    """Read abstract text: md/txt/tex/rst directly, pdf/docx via docs extras."""
    if not path.exists():
        raise InputError(f"File not found: {path}")
    suffix = path.suffix.lower()
    if suffix in _TEXT_SUFFIXES:
        return path.read_text(encoding="utf-8")
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            raise InputError(
                "Reading .pdf needs the docs extras: pip install jfinder[docs]"
            ) from None
        reader = PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages[:6]]
        return "\n".join(pages)
    if suffix == ".docx":
        try:
            from docx import Document
        except ImportError:
            raise InputError(
                "Reading .docx needs the docs extras: pip install jfinder[docs]"
            ) from None
        document = Document(str(path))
        return "\n".join(p.text for p in document.paragraphs)
    raise InputError(f"Unsupported file type: {suffix or path.name}")


def validate(text: str) -> list[str]:
    """Raise InputError for fatal problems; return non-fatal warnings (AGENTS.md §6)."""
    if _PLACEHOLDER_RE.search(text):
        raise InputError(
            "Template not filled in: remove all <...> placeholder markers first."
        )
    words = len(text.split())
    if words < MIN_WORDS:
        raise InputError(
            f"Abstract is too short ({words} words); "
            f"at least {MIN_WORDS} words are required."
        )
    warnings: list[str] = []
    if words > MAX_WORDS_SOFT:
        warnings.append(
            f"Abstract is long ({words} words); consider trimming to ~{MAX_WORDS_SOFT}."
        )
    return warnings


def parse_sections(text: str) -> dict[str, object]:
    """Split the template into title, abstract, keywords, study_type and notes."""
    sections: dict[str, list[str]] = {}
    current = ""
    for line in text.splitlines():
        for key in ("Title", "Abstract", "Keywords", "Study type", "Notes"):
            if line.startswith(f"# {key}"):
                current = key
                break
        else:
            if current:
                sections.setdefault(current, []).append(line.strip())
    keywords_raw = ",".join(sections.get("Keywords", []))
    return {
        "title": "\n".join(sections.get("Title", [])).strip(),
        "abstract": "\n".join(sections.get("Abstract", [])).strip(),
        "keywords": [k.strip() for k in keywords_raw.split(",") if k.strip()],
        "study_type": "\n".join(sections.get("Study type", [])).strip(),
        "notes": "\n".join(sections.get("Notes", [])).strip() or None,
    }

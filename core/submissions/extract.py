"""Text extraction at upload time.

``text_extract`` is populated when the file arrives so nothing downstream ever
opens a file again: the Phase 5 AI layer receives text, and the evidence guard
fuzzy-matches against this same string rather than re-parsing a PDF and hoping
it gets the same characters twice.

**Extraction is deliberately gentle.** Fix item 5 warns that a guard which
normalises text before storing it makes the "verbatim span" no longer verbatim,
and that over-cleaning genuine evidence turns the rejection rate into noise.
So this module fixes line endings, drops the byte-order mark, and stops. Any
aggressive normalisation belongs in the comparison, not in what is stored.

Optional dependencies degrade rather than crash (invariant #10): if
``pdfplumber`` is not installed, a PDF upload is accepted, stored, and recorded
with a note explaining that its text could not be read — the submission is not
lost, and manual scoring still works.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import PurePath

#: Read directly, no dependency.
PLAIN_TEXT_EXTENSIONS = frozenset({".txt", ".md"})

#: Everything a student may upload, whether or not the parser is installed.
ALLOWED_EXTENSIONS = frozenset({".pdf", ".docx", ".txt", ".md"})


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """What came out of one file."""

    text: str
    ok: bool
    note: str

    @property
    def char_count(self) -> int:
        return len(self.text)


def _clean(text: str) -> str:
    """Normalise line endings only.

    Not whitespace, not case, not hyphenation. Those transformations belong to
    the evidence comparison in Phase 5, which normalises *both sides* and keeps
    the model's original span untouched (fix item 5).
    """
    return text.replace("\r\n", "\n").replace("\r", "\n").strip("﻿").strip()


def _extract_plain(data: bytes) -> ExtractionResult:
    text = data.decode("utf-8", errors="replace")
    return ExtractionResult(text=_clean(text), ok=True, note="")


def _extract_pdf(data: bytes) -> ExtractionResult:
    try:
        import pdfplumber
    except ImportError:
        return ExtractionResult(
            text="",
            ok=False,
            note="PDF text extraction needs pdfplumber, which is not installed.",
        )

    try:
        pages: list[str] = []
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                pages.append(page.extract_text() or "")
    except Exception as exc:
        return ExtractionResult(
            text="", ok=False, note=f"Could not read this PDF: {type(exc).__name__}."
        )

    text = _clean("\n\n".join(pages))

    if not text:
        # A scanned document is a real case and the student should be told,
        # not left wondering why the AI found nothing in Phase 5.
        return ExtractionResult(
            text="",
            ok=False,
            note="No text found — this looks like a scanned or image-only PDF.",
        )

    return ExtractionResult(text=text, ok=True, note="")


def _extract_docx(data: bytes) -> ExtractionResult:
    try:
        import docx
    except ImportError:
        return ExtractionResult(
            text="",
            ok=False,
            note="DOCX text extraction needs python-docx, which is not installed.",
        )

    try:
        document = docx.Document(io.BytesIO(data))
        parts = [paragraph.text for paragraph in document.paragraphs]

        # Tables carry real content in an SRS — requirement tables especially.
        for table in document.tables:
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                if any(cells):
                    parts.append(" | ".join(cells))
    except Exception as exc:
        return ExtractionResult(
            text="", ok=False, note=f"Could not read this DOCX: {type(exc).__name__}."
        )

    text = _clean("\n".join(parts))

    if not text:
        return ExtractionResult(text="", ok=False, note="The document appears empty.")

    return ExtractionResult(text=text, ok=True, note="")


def extension_of(filename: str) -> str:
    return PurePath(filename).suffix.lower()


def extract_text(filename: str, data: bytes) -> ExtractionResult:
    """Extract text from one uploaded file. Never raises."""
    suffix = extension_of(filename)

    if suffix in PLAIN_TEXT_EXTENSIONS:
        return _extract_plain(data)
    if suffix == ".pdf":
        return _extract_pdf(data)
    if suffix == ".docx":
        return _extract_docx(data)

    return ExtractionResult(
        text="",
        ok=False,
        note=f"{suffix or 'This file type'} is not supported for text extraction.",
    )


def combine(results: dict[str, ExtractionResult]) -> str:
    """Join per-file text into the submission's ``text_extract``.

    Each file is labelled, because a submission of three documents that reads
    as one undifferentiated wall makes an evidence span impossible to locate
    when a student asks where a mark came from.
    """
    blocks = []
    for filename, result in results.items():
        if result.text:
            blocks.append(f"--- {filename} ---\n{result.text}")
    return "\n\n".join(blocks)

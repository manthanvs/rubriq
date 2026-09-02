"""Text extraction, and how it fails.

Two things matter here beyond "does it read a file".

**It must be gentle.** Fix item 5 warns that normalising text before storing it
makes the "verbatim span" no longer verbatim, and that over-cleaning genuine
evidence turns the Phase 5 rejection rate into noise instead of a result. So
the tests assert that spacing and case survive.

**It must degrade rather than crash.** A scanned PDF, a corrupt file or a
missing parser has to produce a stored submission with an explanatory note, not
a traceback and a lost upload (invariant #10, fix item 13).
"""

from __future__ import annotations

import io

import pytest

from core.submissions.extract import (
    ALLOWED_EXTENSIONS,
    ExtractionResult,
    combine,
    extension_of,
    extract_text,
)


def _docx_bytes(paragraphs: list[str], table: list[list[str]] | None = None) -> bytes:
    docx = pytest.importorskip("docx")

    document = docx.Document()
    for text in paragraphs:
        document.add_paragraph(text)

    if table:
        grid = document.add_table(rows=len(table), cols=len(table[0]))
        for row_index, row in enumerate(table):
            for col_index, cell in enumerate(row):
                grid.cell(row_index, col_index).text = cell

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


class TestPlainText:
    def test_reads_a_txt_file(self) -> None:
        result = extract_text("notes.txt", b"Objectives and scope.")

        assert result.ok
        assert result.text == "Objectives and scope."

    def test_reads_markdown(self) -> None:
        result = extract_text("README.md", b"# Title\n\nBody text.")

        assert result.ok
        assert "# Title" in result.text

    def test_windows_line_endings_are_normalised(self) -> None:
        result = extract_text("notes.txt", b"line one\r\nline two")

        assert result.text == "line one\nline two"
        assert "\r" not in result.text

    def test_a_byte_order_mark_is_stripped(self) -> None:
        result = extract_text("notes.txt", "﻿Objectives".encode())

        assert result.text == "Objectives"

    def test_spacing_and_case_survive(self) -> None:
        """Fix item 5: what is stored must stay verbatim.

        Collapsing runs of spaces here would mean an evidence span the model
        quotes correctly no longer matches the text it was quoting.
        """
        original = "The  System   SHALL log every mutation."
        result = extract_text("srs.txt", original.encode())

        assert result.text == original

    def test_undecodable_bytes_do_not_raise(self) -> None:
        result = extract_text("notes.txt", b"valid \xff\xfe broken")

        assert result.ok
        assert "valid" in result.text


class TestDocx:
    def test_reads_paragraphs(self) -> None:
        data = _docx_bytes(["Introduction", "The system shall log mutations."])
        result = extract_text("srs.docx", data)

        assert result.ok
        assert "Introduction" in result.text
        assert "shall log mutations" in result.text

    def test_reads_table_cells(self) -> None:
        """An SRS keeps its requirements in a table; ignoring tables loses them."""
        data = _docx_bytes(
            ["Requirements"], table=[["ID", "Requirement"], ["FR-1", "Domain login"]]
        )
        result = extract_text("srs.docx", data)

        assert "FR-1" in result.text
        assert "Domain login" in result.text

    def test_an_empty_document_is_reported_not_crashed(self) -> None:
        result = extract_text("blank.docx", _docx_bytes([]))

        assert result.ok is False
        assert result.note
        assert result.text == ""

    def test_a_corrupt_docx_degrades_with_a_note(self) -> None:
        result = extract_text("broken.docx", b"this is not a docx at all")

        assert result.ok is False
        assert result.note
        assert result.text == ""


class TestPdf:
    def test_a_corrupt_pdf_degrades_with_a_note(self) -> None:
        """The submission is still stored; only its text is missing."""
        result = extract_text("broken.pdf", b"%PDF-1.4 truncated nonsense")

        assert result.ok is False
        assert result.note
        assert result.text == ""

    def test_an_image_only_pdf_says_so(self) -> None:
        """A scanned document is a real case and needs a comprehensible reason."""
        pdfplumber = pytest.importorskip("pdfplumber")
        assert pdfplumber  # imported for the skip check only

        # A structurally valid PDF with one empty page and no text operators.
        blank = (
            b"%PDF-1.4\n"
            b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
            b"trailer<</Root 1 0 R>>\n%%EOF\n"
        )
        result = extract_text("scan.pdf", blank)

        assert result.ok is False
        assert result.text == ""
        assert "scanned" in result.note.lower() or "could not" in result.note.lower()


class TestUnsupported:
    def test_an_unknown_extension_is_reported(self) -> None:
        result = extract_text("archive.zip", b"PK\x03\x04")

        assert result.ok is False
        assert result.text == ""
        assert result.note

    def test_extension_of_is_case_insensitive(self) -> None:
        assert extension_of("REPORT.PDF") == ".pdf"

    def test_the_allowed_set_is_what_the_ui_offers(self) -> None:
        assert ALLOWED_EXTENSIONS == {".pdf", ".docx", ".txt", ".md"}


class TestCombine:
    def test_each_file_is_labelled(self) -> None:
        """An unlabelled wall of text makes an evidence span unlocatable."""
        combined = combine(
            {
                "synopsis.txt": ExtractionResult("Synopsis body", True, ""),
                "srs.txt": ExtractionResult("SRS body", True, ""),
            }
        )

        assert "--- synopsis.txt ---" in combined
        assert "--- srs.txt ---" in combined
        assert "Synopsis body" in combined and "SRS body" in combined

    def test_files_that_yielded_nothing_are_skipped(self) -> None:
        combined = combine(
            {
                "good.txt": ExtractionResult("Readable", True, ""),
                "scan.pdf": ExtractionResult("", False, "Image-only."),
            }
        )

        assert "Readable" in combined
        assert "scan.pdf" not in combined

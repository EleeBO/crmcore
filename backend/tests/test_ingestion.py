"""Tests for file parsing pipeline (Task 2.1)."""

import os

import pytest

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _fixture(name: str) -> bytes:
    with open(os.path.join(FIXTURES_DIR, name), "rb") as f:
        return f.read()


# ── Parser tests ───────────────────────────────────────────────────────────


def test_parse_pdf_returns_chunks() -> None:
    """PDF parsing returns list of ParsedChunk with text and metadata."""
    from backend.ingestion.parser import parse_pdf

    data = _fixture("sample.pdf")
    chunks = parse_pdf(data)
    assert len(chunks) >= 1
    assert all(c.text for c in chunks)
    assert all(c.source_file == "sample.pdf" or c.source_file == "" for c in chunks)


def test_parse_pdf_includes_page_numbers() -> None:
    """PDF parsing includes page number in each chunk."""
    from backend.ingestion.parser import parse_pdf

    data = _fixture("sample.pdf")
    chunks = parse_pdf(data)
    assert all(isinstance(c.page_number, int) for c in chunks)
    pages = {c.page_number for c in chunks}
    assert 1 in pages


def test_parse_pdf_contains_sla_content() -> None:
    """PDF content contains expected SLA text."""
    from backend.ingestion.parser import parse_pdf

    data = _fixture("sample.pdf")
    chunks = parse_pdf(data)
    full_text = " ".join(c.text for c in chunks)
    assert "SLA" in full_text or "Gold" in full_text


def test_parse_excel_returns_chunks() -> None:
    """XLSX parsing returns rows with metadata."""
    from backend.ingestion.parser import parse_excel

    data = _fixture("sample.xlsx")
    chunks = parse_excel(data)
    assert len(chunks) >= 3  # Gold, Silver, Bronze rows
    assert all(c.chunk_type == "table" for c in chunks)


def test_parse_excel_preserves_headers() -> None:
    """XLSX row chunks contain column header context."""
    from backend.ingestion.parser import parse_excel

    data = _fixture("sample.xlsx")
    chunks = parse_excel(data)
    gold_chunk = next((c for c in chunks if "Gold" in c.text), None)
    assert gold_chunk is not None
    assert "$500" in gold_chunk.text or "500" in gold_chunk.text


def test_parse_docx_returns_chunks() -> None:
    """DOCX parsing returns chunks with text."""
    from backend.ingestion.parser import parse_docx

    data = _fixture("sample.docx")
    chunks = parse_docx(data)
    assert len(chunks) >= 1
    assert any("стратегия" in c.text.lower() or "SLA" in c.text for c in chunks)


def test_parse_docx_section_titles() -> None:
    """DOCX parsing captures section headings."""
    from backend.ingestion.parser import parse_docx

    data = _fixture("sample.docx")
    chunks = parse_docx(data)
    titles = [c.section_title for c in chunks if c.section_title]
    assert len(titles) >= 1


def test_parse_unsupported_raises() -> None:
    """Unsupported file type raises IngestionError."""
    from backend.errors import IngestionError
    from backend.ingestion.parser import parse_file

    with pytest.raises(IngestionError):
        parse_file(b"binary data", "malware.exe")


def test_parse_corrupt_pdf_raises() -> None:
    """Corrupt PDF raises IngestionError with clear message."""
    from backend.errors import IngestionError
    from backend.ingestion.parser import parse_pdf

    with pytest.raises(IngestionError) as exc_info:
        parse_pdf(b"this is not a pdf")
    assert exc_info.value.message


# ── Chunker tests ──────────────────────────────────────────────────────────


def test_chunker_text_splits_long_text() -> None:
    """Long text is split into 512-token chunks with 64-token overlap."""
    from backend.ingestion.chunker import chunk_text
    from backend.ingestion.parser import ParsedChunk

    long_text = "Слово " * 600  # well over 512 tokens
    parsed = ParsedChunk(text=long_text, source_file="test.txt", page_number=1)
    chunks = chunk_text([parsed])
    assert len(chunks) > 1


def test_chunker_text_preserves_short_text() -> None:
    """Short text (< 512 tokens) produces a single chunk."""
    from backend.ingestion.chunker import chunk_text
    from backend.ingestion.parser import ParsedChunk

    short_text = "Краткий тест."
    parsed = ParsedChunk(text=short_text, source_file="test.txt", page_number=1)
    chunks = chunk_text([parsed])
    assert len(chunks) == 1
    assert chunks[0].text == short_text


def test_chunker_table_preserves_rows() -> None:
    """Table chunks keep each row as a separate chunk with column headers."""
    from backend.ingestion.chunker import chunk_table
    from backend.ingestion.parser import ParsedChunk

    rows = [
        ParsedChunk(text="Plan: Gold | Price: $500 | RTO: 15 min", source_file="data.xlsx", page_number=1, chunk_type="table"),
        ParsedChunk(text="Plan: Silver | Price: $200 | RTO: 4 hours", source_file="data.xlsx", page_number=1, chunk_type="table"),
    ]
    chunks = chunk_table(rows)
    assert len(chunks) == 2
    assert all(c.chunk_type == "table" for c in chunks)

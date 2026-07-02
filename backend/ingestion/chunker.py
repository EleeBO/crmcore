"""Text and table chunking with overlap."""

from __future__ import annotations

from backend.ingestion.parser import ParsedChunk

# Approximate token count: 1 token ≈ 4 chars (rough heuristic, avoids tiktoken dep)
_CHARS_PER_TOKEN = 4
_CHUNK_TOKENS = 512
_OVERLAP_TOKENS = 64
_CHUNK_CHARS = _CHUNK_TOKENS * _CHARS_PER_TOKEN
_OVERLAP_CHARS = _OVERLAP_TOKENS * _CHARS_PER_TOKEN


def chunk_text(parsed: list[ParsedChunk]) -> list[ParsedChunk]:
    """Split text chunks into ~512-token pieces with 64-token overlap."""
    result: list[ParsedChunk] = []
    for item in parsed:
        if len(item.text) <= _CHUNK_CHARS:
            result.append(item)
            continue
        start = 0
        while start < len(item.text):
            end = start + _CHUNK_CHARS
            piece = item.text[start:end]
            result.append(
                ParsedChunk(
                    text=piece,
                    source_file=item.source_file,
                    page_number=item.page_number,
                    section_title=item.section_title,
                    chunk_type=item.chunk_type,
                    metadata={**item.metadata, "chunk_start": start},
                )
            )
            start += _CHUNK_CHARS - _OVERLAP_CHARS
    return result


def chunk_table(rows: list[ParsedChunk]) -> list[ParsedChunk]:
    """Table rows stay as individual chunks (already row-granular)."""
    return list(rows)

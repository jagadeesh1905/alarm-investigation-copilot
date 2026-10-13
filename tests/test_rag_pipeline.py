
import pytest

from rag_pipeline import (
    chunk_text,
    build_document_metadata,
    extract_asset_types,
    extract_field,
    extract_title,
)


def test_empty_text_returns_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   \n\t  ") == []


def test_plain_text_returns_chunk_dictionaries():
    chunks = chunk_text("Check the alarm timestamp and asset identity.")

    assert len(chunks) == 1
    assert "text" in chunks[0]
    assert "section" in chunks[0]
    assert "Check the alarm timestamp" in chunks[0]["text"]


def test_long_text_is_split_into_multiple_chunks():
    text = " ".join(f"word{i}" for i in range(1000))
    chunks = chunk_text(text)

    assert len(chunks) > 1
    assert all(chunk["text"].strip() for chunk in chunks)
    assert all(isinstance(chunk["section"], str) for chunk in chunks)


def test_markdown_heading_is_preserved_in_chunk_text():
    text = (
        "# Investigation Topics\n"
        "Review the alarm timestamp and current status.\n"
        "## Safety\n"
        "Consult authorized personnel."
    )

    chunks = chunk_text(text, is_markdown=True)

    assert len(chunks) == 2
    assert chunks[0]["section"] == "Investigation Topics"
    assert chunks[1]["section"] == "Safety"
    assert "Section: Investigation Topics" in chunks[0]["text"]
    assert "Section: Safety" in chunks[1]["text"]


def test_document_metadata_uses_declared_fields(tmp_path):
    path = tmp_path / "demo_procedure.md"
    text = (
        "# Motor Trip Investigation\n"
        "Procedure ID: DEMO-MTR-001\n"
        "Revision: 2\n"
        "Status: SYNTHETIC DEMONSTRATION ONLY\n"
        "Applicable asset types: Motor, Pump\n"
    )

    metadata = build_document_metadata(path, text)

    assert metadata["source"] == "demo_procedure.md"
    assert metadata["doc_id"] == "DEMO-MTR-001"
    assert metadata["title"] == "Motor Trip Investigation"
    assert metadata["revision"] == "2"
    assert metadata["approval_status"] == "SYNTHETIC DEMONSTRATION ONLY"
    assert metadata["asset_types"] == "Motor, Pump"
    assert metadata["file_type"] == "md"


def test_missing_metadata_is_not_invented(tmp_path):
    path = tmp_path / "unknown_procedure.txt"
    text = "Check the available event logs."

    metadata = build_document_metadata(path, text)

    assert metadata["doc_id"] == "unknown_procedure"
    assert metadata["revision"] == "unspecified"
    assert metadata["approval_status"] == "unspecified"
    assert metadata["asset_types"] == "unspecified"


def test_extract_field_handles_missing_fields():
    assert extract_field("Revision: 3", "Revision") == "3"
    assert extract_field("No metadata here", "Revision") == ""


def test_extract_asset_types_does_not_guess():
    assert extract_asset_types("Asset types: Compressor, Motor") == "Compressor, Motor"
    assert extract_asset_types("No asset type declared") == "unspecified"

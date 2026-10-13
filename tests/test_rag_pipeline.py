
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import rag_pipeline
from rag_pipeline import (
    chunk_text,
    build_document_metadata,
    extract_asset_types,
    extract_field,
    extract_title,
    load_document,
    split_markdown_sections,
    split_long_text,
)


# ---------------------------------------------------------
# Text chunking
# ---------------------------------------------------------

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


def test_long_text_chunks_respect_size_limit():
    text = "x" * 3500

    chunks = split_long_text(text)

    assert len(chunks) > 1
    assert all(len(chunk) <= rag_pipeline.CHUNK_SIZE for chunk in chunks)


def test_long_text_chunks_preserve_overlap():
    text = "x" * 3000

    chunks = split_long_text(text)

    assert len(chunks) > 1
    assert chunks[0][-rag_pipeline.CHUNK_OVERLAP:] in chunks[1]


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


def test_markdown_sections_keep_heading_and_body_together():
    sections = split_markdown_sections(
        "# Overview\nFirst section.\n## Safety\nSafety section."
    )

    assert len(sections) == 2
    assert sections[0][0] == "Overview"
    assert "First section." in sections[0][1]
    assert sections[1][0] == "Safety"
    assert "Safety section." in sections[1][1]


def test_markdown_without_heading_is_supported():
    chunks = chunk_text("General procedure text.", is_markdown=True)

    assert len(chunks) == 1
    assert chunks[0]["section"] == ""
    assert "General procedure text." in chunks[0]["text"]


# ---------------------------------------------------------
# Document metadata
# ---------------------------------------------------------

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
    assert extract_asset_types(
        "Asset types: Compressor, Motor"
    ) == "Compressor, Motor"
    assert extract_asset_types(
        "No asset type declared"
    ) == "unspecified"


def test_title_falls_back_to_filename():
    title = extract_title(
        "Procedure ID: DEMO-001\nCheck the logs.",
        Path("motor_trip_procedure.md"),
    )

    assert title == "motor trip procedure"


def test_document_label_can_supply_title():
    title = extract_title(
        "Document: Pump Troubleshooting\nCheck the pump.",
        Path("unknown.md"),
    )

    assert title == "Pump Troubleshooting"


# ---------------------------------------------------------
# Document loading
# ---------------------------------------------------------

def test_load_text_document(tmp_path):
    path = tmp_path / "procedure.txt"
    path.write_text("Check the alarm history.", encoding="utf-8")

    assert load_document(path) == "Check the alarm history."


def test_load_markdown_document(tmp_path):
    path = tmp_path / "procedure.md"
    path.write_text("# Safety\nConsult an authorized operator.", encoding="utf-8")

    assert load_document(path).startswith("# Safety")


def test_unsupported_document_type_returns_empty_text(tmp_path):
    path = tmp_path / "procedure.rtf"
    path.write_text("Some text", encoding="utf-8")

    assert load_document(path) == ""


# ---------------------------------------------------------
# RAG retrieval
# ---------------------------------------------------------

def test_search_procedures_returns_empty_for_blank_query():
    with patch.object(rag_pipeline, "chromadb") as chromadb_mock:
        assert rag_pipeline.search_procedures("   ") == []

    chromadb_mock.PersistentClient.assert_not_called()


def test_search_procedures_returns_empty_for_invalid_top_k():
    with patch.object(rag_pipeline, "chromadb") as chromadb_mock:
        assert rag_pipeline.search_procedures("motor trip", top_k=0) == []

    chromadb_mock.PersistentClient.assert_not_called()


def test_search_procedures_raises_clear_error_when_index_missing():
    client = MagicMock()
    client.get_collection.side_effect = ValueError("missing collection")

    with patch.object(
        rag_pipeline.chromadb,
        "PersistentClient",
        return_value=client,
    ):
        with pytest.raises(RuntimeError, match="Run `python rag_pipeline.py`"):
            rag_pipeline.search_procedures("motor trip")

    client.get_collection.assert_called_once_with(
        name=rag_pipeline.COLLECTION_NAME
    )


def test_search_procedures_returns_empty_for_empty_collection():
    collection = MagicMock()
    collection.count.return_value = 0

    client = MagicMock()
    client.get_collection.return_value = collection

    with patch.object(
        rag_pipeline.chromadb,
        "PersistentClient",
        return_value=client,
    ), patch.object(rag_pipeline, "get_embedding_model") as model_mock:
        results = rag_pipeline.search_procedures("motor trip")

    assert results == []
    model_mock.assert_not_called()


def test_search_procedures_returns_metadata_for_relevant_match():
    collection = MagicMock()
    collection.count.return_value = 1
    collection.query.return_value = {
        "documents": [["Check the motor trip procedure."]],
        "metadatas": [[{
            "source": "motor_trip.md",
            "chunk_index": 2,
            "doc_id": "DEMO-MTR-001",
            "title": "Motor Trip",
            "revision": "1",
            "approval_status": "SYNTHETIC DEMONSTRATION ONLY",
            "asset_types": "Motor",
            "section": "Safety",
        }]],
        "distances": [[0.25]],
    }

    client = MagicMock()
    client.get_collection.return_value = collection

    model = MagicMock()
    model.encode.return_value.tolist.return_value = [[0.1, 0.2]]

    with patch.object(
        rag_pipeline.chromadb,
        "PersistentClient",
        return_value=client,
    ), patch.object(
        rag_pipeline,
        "get_embedding_model",
        return_value=model,
    ):
        results = rag_pipeline.search_procedures(
            "motor trip",
            top_k=3,
            max_distance=1.2,
        )

    assert len(results) == 1
    assert results[0]["doc_id"] == "DEMO-MTR-001"
    assert results[0]["source"] == "motor_trip.md"
    assert results[0]["section"] == "Safety"
    assert results[0]["distance"] == 0.25
    assert results[0]["approval_status"] == "SYNTHETIC DEMONSTRATION ONLY"

    collection.query.assert_called_once_with(
        query_embeddings=[[0.1, 0.2]],
        n_results=1,
        include=["documents", "metadatas", "distances"],
    )


def test_search_procedures_filters_weak_matches():
    collection = MagicMock()
    collection.count.return_value = 1
    collection.query.return_value = {
        "documents": [["Unrelated procedure content."]],
        "metadatas": [[{"source": "unrelated.md"}]],
        "distances": [[9.5]],
    }

    client = MagicMock()
    client.get_collection.return_value = collection

    model = MagicMock()
    model.encode.return_value.tolist.return_value = [[0.1, 0.2]]

    with patch.object(
        rag_pipeline.chromadb,
        "PersistentClient",
        return_value=client,
    ), patch.object(
        rag_pipeline,
        "get_embedding_model",
        return_value=model,
    ):
        results = rag_pipeline.search_procedures(
            "motor trip",
            max_distance=1.2,
        )

    assert results == []


def test_search_procedures_uses_requested_top_k():
    collection = MagicMock()
    collection.count.return_value = 5
    collection.query.return_value = {
        "documents": [[]],
        "metadatas": [[]],
        "distances": [[]],
    }

    client = MagicMock()
    client.get_collection.return_value = collection

    model = MagicMock()
    model.encode.return_value.tolist.return_value = [[0.1, 0.2]]

    with patch.object(
        rag_pipeline.chromadb,
        "PersistentClient",
        return_value=client,
    ), patch.object(
        rag_pipeline,
        "get_embedding_model",
        return_value=model,
    ):
        results = rag_pipeline.search_procedures(
            "pump troubleshooting",
            top_k=2,
        )

    assert results == []
    assert collection.query.call_args.kwargs["n_results"] == 2


# ---------------------------------------------------------
# Index-building error handling
# ---------------------------------------------------------

def test_build_index_fails_when_procedure_directory_missing(tmp_path):
    missing_dir = tmp_path / "missing_procedures"

    with patch.object(rag_pipeline, "PROCEDURES_DIR", missing_dir):
        with pytest.raises(FileNotFoundError, match="Procedure directory"):
            rag_pipeline.build_index()


def test_build_index_fails_when_no_supported_files_exist(tmp_path):
    procedures_dir = tmp_path / "procedures"
    procedures_dir.mkdir()
    (procedures_dir / "notes.rtf").write_text("Not supported", encoding="utf-8")

    with patch.object(rag_pipeline, "PROCEDURES_DIR", procedures_dir):
        with pytest.raises(ValueError, match="No supported procedure files"):
            rag_pipeline.build_index()


def test_build_index_fails_when_all_documents_are_empty(tmp_path):
    procedures_dir = tmp_path / "procedures"
    procedures_dir.mkdir()
    (procedures_dir / "empty.txt").write_text("   \n", encoding="utf-8")

    with patch.object(rag_pipeline, "PROCEDURES_DIR", procedures_dir):
        with pytest.raises(
            ValueError,
            match="No readable text chunks",
        ):
            rag_pipeline.build_index()

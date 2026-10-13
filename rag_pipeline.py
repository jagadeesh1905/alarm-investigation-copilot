
from pathlib import Path
import re
import sys

import chromadb
from sentence_transformers import SentenceTransformer
from pypdf import PdfReader
from docx import Document


BASE_DIR = Path(__file__).parent
PROCEDURES_DIR = BASE_DIR / "rag" / "documents"
CHROMA_DIR = BASE_DIR / "data" / "chroma_db"

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
COLLECTION_NAME = "maintenance_procedures"

CHUNK_SIZE = 1200
CHUNK_OVERLAP = 150

# Initial relevance threshold for ChromaDB squared L2 distance.
MAX_DISTANCE = 1.20

# Load the embedding model once per Python process.
_embedding_model = None


def get_embedding_model():
    """Return the cached embedding model."""
    global _embedding_model

    if _embedding_model is None:
        _embedding_model = SentenceTransformer(MODEL_NAME)

    return _embedding_model


def warm_up():
    """Load the embedding model before the MCP server starts handling requests."""
    get_embedding_model()

def load_document(path: Path) -> str:
    """Extract text from supported document formats."""
    suffix = path.suffix.lower()

    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8")

    if suffix == ".pdf":
        reader = PdfReader(str(path))
        return "\n".join(
            page.extract_text() or "" for page in reader.pages
        )

    if suffix == ".docx":
        document = Document(str(path))
        return "\n".join(
            paragraph.text for paragraph in document.paragraphs
        )

    return ""


def extract_field(text: str, field_name: str) -> str:
    """Extract a simple labelled metadata field from document text."""
    pattern = rf"(?im)^\s*{re.escape(field_name)}\s*:\s*(.*?)\s*$"
    match = re.search(pattern, text)

    return match.group(1).strip() if match else ""


def extract_title(text: str, path: Path) -> str:
    """Extract a title from a Markdown heading or Document label."""
    for line in text.splitlines():
        line = line.strip()

        if not line:
            continue

        heading = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
        if heading:
            return heading.group(1).strip()

        if line.lower().startswith("document:"):
            return line.split(":", 1)[1].strip()

        # Avoid using arbitrary body text as a title.
        if re.match(
            r"(?i)^(procedure id|revision|status|purpose|safety|"
            r"applicable alarm|applicable asset types)\s*:",
            line,
        ):
            continue

        # For a document without a recognised title, use its filename.
        break

    return path.stem.replace("_", " ").replace("-", " ").strip()


def extract_asset_types(text: str) -> str:
    """Read explicitly declared asset types; do not guess them."""
    value = extract_field(text, "Applicable asset types")

    if not value:
        value = extract_field(text, "Asset types")

    return value or "unspecified"


def split_markdown_sections(text: str) -> list[tuple[str, str]]:
    """Split Markdown by headings and retain each heading in its section."""
    sections = []
    current_heading = ""
    current_lines = []

    for line in text.splitlines():
        heading_match = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line)

        if heading_match:
            content = "\n".join(current_lines).strip()

            if content:
                sections.append((current_heading, content))

            current_heading = heading_match.group(2).strip()
            current_lines = [line]
        else:
            current_lines.append(line)

    content = "\n".join(current_lines).strip()

    if content:
        sections.append((current_heading, content))

    return sections


def split_long_text(text: str) -> list[str]:
    """Split long text into overlapping character-based chunks."""
    text = text.strip()

    if not text:
        return []

    chunks = []
    start = 0

    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))

        # Prefer a paragraph or sentence boundary when reasonably close.
        if end < len(text):
            boundary = max(
                text.rfind("\n", start, end),
                text.rfind(". ", start, end),
                text.rfind("; ", start, end),
            )

            if boundary > start + CHUNK_SIZE // 2:
                end = boundary + 1

        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= len(text):
            break

        next_start = max(0, end - CHUNK_OVERLAP)

        # Ensure the loop always progresses.
        start = next_start if next_start > start else end

    return chunks


def chunk_text(text: str, is_markdown: bool = False) -> list[dict]:
    """
    Create chunks with heading context.

    Markdown is split by headings first. Oversized sections are then
    divided into overlapping chunks. Plain text uses the same chunker.
    """
    if not text or not text.strip():
        return []

    if not is_markdown:
        return [
            {"text": chunk, "section": ""}
            for chunk in split_long_text(text)
        ]

    output = []

    for heading, section_text in split_markdown_sections(text):
        # Keep heading context attached to the chunk for retrieval.
        heading_prefix = f"Section: {heading}\n" if heading else ""

        section_chunks = split_long_text(section_text)

        
        for chunk in section_chunks:
            output.append({
                "text": f"{heading_prefix}{chunk}",
                "section": heading,
            })


    return output


def build_document_metadata(path: Path, text: str) -> dict:
    """Build searchable, auditable metadata for a source document."""
    title = extract_title(text, path)
    procedure_id = extract_field(text, "Procedure ID")
    revision = extract_field(text, "Revision")
    status = extract_field(text, "Status")

    return {
        "source": path.name,
        "doc_id": procedure_id or path.stem,
        "title": title,
        "revision": revision or "unspecified",
        "approval_status": status or "unspecified",
        "asset_types": extract_asset_types(text),
        "file_type": path.suffix.lower().lstrip("."),
    }


def build_index():
    """Rebuild the procedure index from all supported documents."""
    if not PROCEDURES_DIR.exists():
        raise FileNotFoundError(
            f"Procedure directory not found: {PROCEDURES_DIR}"
        )

    supported_extensions = {".txt", ".md", ".pdf", ".docx"}

    files = sorted(
        path
        for path in PROCEDURES_DIR.rglob("*")
        if path.is_file()
        and path.suffix.lower() in supported_extensions
    )

    if not files:
        raise ValueError(
            f"No supported procedure files found in {PROCEDURES_DIR}"
        )

    prepared_chunks = []

    for path in files:
        try:
            text = load_document(path)
        except Exception as exc:
            print(
                f"[RAG] Skipping unreadable file {path.name}: {exc}",
                file=sys.stderr,
                flush=True,
            )
            continue

        if not text.strip():
            print(
                f"[RAG] Skipping empty document: {path.name}",
                file=sys.stderr,
                flush=True,
            )
            continue

        base_metadata = build_document_metadata(path, text)
        chunks = chunk_text(
            text,
            is_markdown=path.suffix.lower() == ".md",
        )

        relative_path = path.relative_to(PROCEDURES_DIR).as_posix()

        for index, chunk in enumerate(chunks):
            prepared_chunks.append({
                "id": f"{relative_path}-{index}",
                "text": chunk["text"],
                "metadata": {
                    **base_metadata,
                    "source": relative_path,
                    "chunk_index": index,
                    "section": chunk["section"] or "general",
                },
            })

    if not prepared_chunks:
        raise ValueError(
            "No readable text chunks were created from procedure documents."
        )

    model = get_embedding_model()
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    # Rebuild the collection so removed or changed source files do not
    # leave stale chunks behind.
    try:
        client.delete_collection(name=COLLECTION_NAME)
    except Exception:
        pass

    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "l2"},
    )

    batch_size = 64

    for start in range(0, len(prepared_chunks), batch_size):
        batch = prepared_chunks[start:start + batch_size]
        documents = [item["text"] for item in batch]
        embeddings = model.encode(documents).tolist()

        collection.add(
            ids=[item["id"] for item in batch],
            documents=documents,
            metadatas=[item["metadata"] for item in batch],
            embeddings=embeddings,
        )

    print(f"Indexed {len(prepared_chunks)} chunks from {len(files)} files.")
    print(f"ChromaDB location: {CHROMA_DIR}")

    for path in files:
        print(f"  - {path.relative_to(PROCEDURES_DIR).as_posix()}")


def search_procedures(
    query: str,
    top_k: int = 3,
    max_distance: float = MAX_DISTANCE,
) -> list[dict]:
    """Retrieve relevant procedure chunks and filter weak matches."""
    if not query or not query.strip():
        return []

    if top_k < 1:
        return []

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    try:
        collection = client.get_collection(name=COLLECTION_NAME)
    except Exception as exc:
        raise RuntimeError(
            "Procedure index not found. Run `python rag_pipeline.py` "
            "to build the index."
        ) from exc

    count = collection.count()

    if count == 0:
        return []

    model = get_embedding_model()
    query_embedding = model.encode([query.strip()]).tolist()

    results = collection.query(
        query_embeddings=query_embedding,
        n_results=min(top_k, count),
        include=["documents", "metadatas", "distances"],
    )

    matches = []
    candidate_documents = results.get("documents", [[]])[0] or []
    candidate_metadata = results.get("metadatas", [[]])[0] or []
    candidate_distances = results.get("distances", [[]])[0] or []

    for document, metadata, raw_distance in zip(
        candidate_documents,
        candidate_metadata,
        candidate_distances,
    ):
        distance = float(raw_distance)

        print(
            f"[RAG] Candidate source={metadata.get('source', 'unknown')} "
            f"section={metadata.get('section', 'general')} "
            f"distance={distance:.4f}",
            file=sys.stderr,
            flush=True,
        )

        if distance > max_distance:
            continue

        matches.append({
            "text": document,
            "source": metadata.get("source", "unknown"),
            "chunk_index": metadata.get("chunk_index", 0),
            "distance": distance,
            "doc_id": metadata.get("doc_id", "unknown"),
            "title": metadata.get("title", "Untitled"),
            "revision": metadata.get("revision", "unspecified"),
            "approval_status": metadata.get(
                "approval_status", "unspecified"
            ),
            "asset_types": metadata.get("asset_types", "unspecified"),
            "section": metadata.get("section", "general"),
        })

    print(
        f"[RAG] Returning {len(matches)} relevant chunks "
        f"from {len(candidate_documents)} candidates.",
        file=sys.stderr,
        flush=True,
    )

    return matches


if __name__ == "__main__":
    build_index()

    test_queries = [
        "What should be investigated for high bearing temperature?",
        "What should be investigated for a motor trip?",
        "What does the procedure say about escalation and restarting equipment?",
    ]

    for query in test_queries:
        print(f"\nQuery: {query}")
        matches = search_procedures(query)

        for index, match in enumerate(matches, start=1):
            print(f"\n--- Result {index} ---")
            print(f"Source: {match['source']}")
            print(f"Title: {match['title']}")
            print(f"Document ID: {match['doc_id']}")
            print(f"Revision: {match['revision']}")
            print(f"Status: {match['approval_status']}")
            print(f"Section: {match['section']}")
            print(f"Distance: {match['distance']:.4f}")
            print(match["text"])

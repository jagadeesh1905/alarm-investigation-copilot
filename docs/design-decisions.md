# Design Decisions

## 1. Purpose

This document records the major design decisions for the Alarm Investigation and Procedure Guidance Copilot.

The project combines an API integration layer, MCP-based tool access, retrieval-augmented generation (RAG), and a local language model to support alarm investigation with traceable evidence.

The decisions prioritize local development, modularity, explainability, testability, and safe handling of operational recommendations.

## 2. Technology Choices

### 2.1 Python

**Decision:** Use Python as the primary programming language.

**Reasoning:**
- Supports API development, document processing, embedding generation, vector search, and LLM integration.
- Provides libraries for automated testing and asynchronous execution.
- Allows the components to be developed and tested independently.

**Trade-off:** Python package versions and native dependencies must be managed carefully to keep the development environment reproducible.

### 2.2 FastAPI

**Decision:** Use FastAPI to implement the alarm and asset API.

**Reasoning:**
- Provides request validation and structured API definitions.
- Generates interactive API documentation.
- Supports asynchronous endpoints and middleware.
- Makes it straightforward to write API tests.

**Trade-off:** Slow operations, including LLM report generation, need appropriate timeouts and should not block unrelated requests unnecessarily.

### 2.3 Model Context Protocol (MCP)

**Decision:** Use MCP to expose investigation capabilities as discoverable tools.

**Reasoning:**
- Separates tool definitions from investigation orchestration.
- Allows a client to discover tools and invoke them through a common protocol.
- Creates a clear integration boundary between the investigation workflow and API operations.
- Supports structured tool inputs and outputs.

**Trade-off:** MCP introduces session management, an additional process, protocol handling, and potential startup overhead. Tool discovery and invocation failures must be handled explicitly.

### 2.4 ChromaDB

**Decision:** Use ChromaDB for persistent vector storage.

**Reasoning:**
- Stores document chunk embeddings and metadata.
- Supports similarity-based retrieval.
- Persists the local index between application runs.
- Simplifies development without requiring a separately managed vector database service.

**Trade-off:** A local persistent index is convenient for a demonstration, but concurrent access, backup, scaling, and production deployment need further evaluation.

### 2.5 Sentence Transformers

**Decision:** Use a Sentence Transformers embedding model to represent procedure chunks and user queries as vectors.

**Reasoning:**
- Supports local embedding generation.
- Avoids requiring a hosted embedding API for the current workflow.
- Allows the same embedding model to be used for document indexing and query retrieval.

**Trade-off:** Initial model loading and embedding generation consume local memory and processing time. Retrieval quality depends on the selected model, document content, chunking strategy, and relevance threshold.

### 2.6 Ollama

**Decision:** Use Ollama to run the language model locally.

**Reasoning:**
- Supports local development without requiring a hosted LLM request for each report.
- Keeps the language-model integration separate from API and RAG components.
- Allows the model to be changed through configuration and the LLM integration layer.

**Trade-off:** Response latency and output quality depend on the model, available hardware, prompt design, and context size. Local execution does not automatically guarantee factual accuracy or security.

### 2.7 FastAPI and Streamlit-Compatible UI Approach

**Decision:** Keep the investigation interface separate from the backend API.

The current user interface is implemented as a lightweight HTML page that calls the FastAPI backend.

**Reasoning:**
- Separates presentation from business logic.
- Allows investigation results to be viewed without embedding backend logic in the UI.
- Makes it possible to replace or extend the interface independently.

**Trade-off:** The browser and backend must agree on endpoint paths, authentication, request payloads, and response formats.

**Clarification:** Although Streamlit was considered during initial planning, the current interface is `frontend/index.html`, served as a static page. The implemented interface should be described accurately rather than claimed to be a Streamlit application.

## 3. RAG Design Decisions

### 3.1 Chunking

**Decision:** Use a chunk size of approximately 1,200 characters with 150 characters of overlap.

**Reasoning:**
- Limits the amount of text stored in each vector.
- Preserves some surrounding context between adjacent chunks.
- Helps retrieve specific procedure sections instead of entire documents.

**Trade-off:** Fixed-size chunking can split a procedure step across chunks. Chunk size and overlap should be evaluated against representative queries.

### 3.2 Metadata

**Decision:** Store metadata alongside indexed chunks, including source, document ID, title, revision, approval status, asset types, section, and chunk index.

**Reasoning:**
- Supports evidence traceability.
- Helps distinguish documents and their sections.
- Provides a foundation for future metadata filtering.

**Trade-off:** Metadata is only useful when ingestion extracts it accurately. Missing information must not be invented.

### 3.3 Retrieval

**Decision:** Use vector similarity search in ChromaDB with a configurable relevance threshold.

**Reasoning:**
- Retrieves chunks based on semantic similarity rather than exact keyword matching alone.
- Helps identify potentially relevant procedures even when the user's wording differs from the document.

**Trade-off:** Similarity does not prove that a document is applicable or authoritative. Thresholds require testing, and low-confidence results must be handled explicitly.

**Current limitation:** Hybrid retrieval and reranking are not implemented in the current design.

### 3.4 Evidence-Grounded Generation

**Decision:** Provide retrieved evidence to the report-generation step and require the report to distinguish evidence from hypotheses.

**Reasoning:**
- Helps users trace recommendations to supporting procedure content.
- Reduces unsupported claims.
- Allows the report to communicate uncertainty when evidence is insufficient.

**Trade-off:** Prompt instructions alone cannot eliminate hallucinations. Evidence validation, regression tests, and careful review remain necessary.

## 4. Investigation Orchestration

**Decision:** Use a Python orchestration layer to coordinate MCP tool calls, procedure retrieval, and report generation.

The workflow retrieves the requested alarm, obtains asset information, collects related alarm context, invokes correlation and priority tools, retrieves operator recommendations and procedure evidence, and then generates a consolidated report.

**Reasoning:**
- Keeps workflow sequencing outside individual API endpoints.
- Enables a single investigation response to combine structured API data and document evidence.
- Supports recording tool execution status and timing.

**Trade-off:** Multiple sequential calls can increase latency. A failure in one step must not be silently presented as a successful result.

## 5. Testing Decisions

**Decision:** Use pytest for automated tests.

**Reasoning:**
- Supports focused tests for API routes, LLM behavior, and RAG processing.
- Makes regression testing repeatable.
- Allows external dependencies to be mocked in unit tests.

The existing tests cover API behavior, LLM fallback and safety behavior, and RAG chunking and metadata.

**Trade-off:** Unit tests do not prove that the complete system works with every real dependency. Additional end-to-end tests should cover MCP discovery, actual tool invocation, retrieval, report generation, timeouts, and partial failures.

## 6. Safety and Trust Boundaries

The application is an investigation aid, not an autonomous industrial control system.

The report must:
- Distinguish observations from unconfirmed hypotheses.
- Cite retrieved evidence where available.
- Identify insufficient or missing evidence.
- Avoid claiming that a proposed action has been performed.
- Avoid authorizing equipment isolation, repair, or restart.
- Direct operators to applicable approved procedures and authorized personnel.

The current procedure files are synthetic demonstration material. They must not be represented as approved operational procedures.

The API's calculation-code execution capability also requires a dedicated security review before accepting untrusted input or being used in a production environment.

## 7. Known Trade-Offs and Future Work

| Area | Current decision | Potential improvement |
|---|---|---|
| Vector database | Local persistent ChromaDB | Evaluate operational and scaling requirements |
| Embeddings | Local Sentence Transformers model | Benchmark retrieval quality |
| Language model | Local Ollama model | Compare latency and quality across models |
| Retrieval | Vector similarity with threshold | Evaluate hybrid search and reranking |
| Tool integration | MCP over a local server process | Improve startup and execution tracing |
| UI | Static HTML frontend | Improve usability and investigation visualization |
| Testing | pytest unit and API tests | Expand end-to-end and failure-path coverage |
| Deployment | Local development setup | Add containerization and automated CI |
| Security | Demo bearer-token configuration | Strengthen secret management and execution isolation |

## 8. Summary

The current design uses modular components to combine structured alarm data, discoverable MCP tools, document retrieval, and language-model-generated investigation reports.

The design favors a reproducible local demonstration while keeping component boundaries clear. Production readiness would require further validation of retrieval quality, API contracts, security controls, deployment configuration, and end-to-end reliability.

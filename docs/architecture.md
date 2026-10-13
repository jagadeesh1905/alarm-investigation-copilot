# Architecture — Alarm Investigation and Procedure Guidance Copilot

## 1. Purpose

The Alarm Investigation and Procedure Guidance Copilot helps an operator investigate an alarm by combining structured alarm-system data with relevant procedure documents.

The application retrieves alarm and asset information through an MCP server, searches procedure documents using a RAG pipeline, and generates a structured investigation report. The report presents evidence, possible explanations, recommended checks, and safety warnings.

This project is a demonstration implementation. Its sample procedure documents are synthetic and must not be treated as approved operational instructions.

## 2. Technology Stack

| Component | Technology |
|---|---|
| API simulator | Python, FastAPI |
| Request validation | Pydantic |
| MCP server | Python MCP SDK |
| MCP client and orchestration | Python, asynchronous MCP client |
| Document processing | Python text and Markdown processing |
| Embeddings | Sentence Transformers |
| Vector storage | ChromaDB with persistent storage |
| Report generation | Local Ollama model |
| User interface | HTML, CSS, JavaScript |
| Automated testing | pytest |
| Configuration | Environment variables and python-dotenv |

## 3. High-Level Architecture


flowchart TD
    U[User] --> UI[HTML / JavaScript GUI]
    UI --> API[FastAPI Copilot API]
    API --> ORCH[Investigation Orchestrator]
    ORCH --> CLIENT[MCP Client]
    CLIENT --> MCP[MCP Server]
    MCP --> SIM[Alarm Management API Simulator]
    SIM --> DATA[Sample Alarm and Asset Data]

    ORCH --> RET[Procedure Retrieval]
    RET --> EMB[Sentence Transformers]
    RET --> VDB[(Persistent ChromaDB)]
    DOCS[Procedure Documents] --> ING[Document Ingestion]
    ING --> EMB
    ING --> VDB

    ORCH --> LLM[Local Ollama Report Generation]
    RET --> ORCH
    MCP --> TRACE[MCP Tool Execution Trace]
    ORCH --> LLM
    LLM --> API
    API --> UI
```

## 4. Request Flow

1. The user submits an alarm investigation request through the GUI.
2. The FastAPI endpoint validates the request and checks bearer-token authentication.
3. The investigation orchestrator connects to the MCP server and discovers available tools.
4. The orchestrator invokes MCP tools to retrieve the requested alarm, asset information, related active alarms, priority information, recommendations, and relevant procedure evidence where supported.
5. The RAG pipeline embeds the search query and retrieves relevant procedure chunks from ChromaDB.
6. The report-generation component uses the investigation data and retrieved evidence to construct a structured report.
7. The API returns the report, evidence citations, warnings, MCP execution trace, and available timing information to the GUI.

The copilot accesses the Alarm Management API through MCP rather than calling the alarm API directly from the orchestration layer.

## 5. Main Components

### 5.1 Alarm Management API Simulator

Implemented in `app/main.py`, with sample data in `app/data.py`.

The API provides operations for asset search and metadata, alarm retrieval and filtering, summaries, trends, correlation, flood analysis, rationalization candidates, priority scoring, operator recommendations, calculation-code operations, and KPI definitions.

The simulator uses sample data and is not connected to a live industrial control system.

### 5.2 MCP Server

Implemented in `mcp_server.py`.

The server exposes typed tools for selected alarm API operations. It uses configurable API connection settings, bearer-token authentication, trace metadata, request timeouts, retry settings, pagination support for alarm listing, and API error mapping.

The MCP tool catalog documents the operations exposed through MCP. API operations not exposed as MCP tools are not directly available to the orchestration layer through this tool catalog.

### 5.3 Investigation Orchestrator

Implemented in `investigation.py`.

The orchestrator coordinates MCP tool calls, collects alarm and asset data, retrieves procedure evidence, records tool execution details, and invokes report generation. It also collects timing information and warnings for the returned investigation result.

### 5.4 RAG Pipeline

Implemented in `rag_pipeline.py`.

The pipeline extracts text from supported procedure files, creates chunks with section context, builds metadata, generates embeddings using Sentence Transformers, and stores embeddings in persistent ChromaDB storage.

Retrieval uses vector similarity with L2 distance and a relevance threshold. Retrieved results include source and document metadata to support evidence citations.

### 5.5 Report Generation

Implemented in `llm_service.py`.

The report-generation component uses a local Ollama model for analysis while applying deterministic safeguards to the final report. Root-cause explanations remain unconfirmed unless supported by evidence. The report identifies synthetic procedure evidence and includes safety warnings when evidence is insufficient or not approved.

### 5.6 Frontend

Implemented in `frontend/index.html`.

The browser interface allows a user to submit an investigation and inspect the returned report, asset details, evidence, citations, warnings, execution trace, and timing information.

## 6. Security and Trust Boundaries

- The API uses bearer-token authentication on protected endpoints.
- API tokens and service configuration should be provided through environment variables.
- Secrets must not be committed to source control or included in logs.
- Alarm data, retrieved documents, and model-generated explanations have different trust levels.
- Retrieved procedure text is evidence, not an instruction to override application safety controls.
- Synthetic procedure documents are not approved operational procedures.
- The copilot does not establish a confirmed root cause merely because a model proposes a possible explanation.
- This demonstration should not be used to control, isolate, repair, or restart industrial equipment.

## 7. Observability

The investigation result includes a trace identifier, MCP tool execution details, warnings, and timing measurements. These support debugging and investigation of slow or failed requests.

The current implementation is a local demonstration. Production deployment would require additional validation of logging, access control, monitoring, resource limits, and operational reliability.

## 8. Known Architectural Limitations

- The alarm API uses simulated data.
- The procedure corpus contains synthetic demonstration material.
- The MCP server exposes selected API operations rather than every API route.
- Local model inference can cause high response latency.
- Automated tests and clean-environment packaging must be validated before submission.
- Production deployment, load testing, and operational approval are outside the current demonstrated scope.

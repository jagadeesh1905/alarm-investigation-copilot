# Known Limitations

## 1. Overview

The Alarm Investigation and Procedure Guidance Copilot is a local demonstration application that combines alarm and asset APIs, MCP tools, RAG-based procedure retrieval, and local LLM-generated reports.

The current implementation demonstrates the core workflow. The limitations below identify areas that require further implementation, validation, or operational hardening.

## 2. API and MCP Integration

### 2.1 Incomplete MCP Tool Coverage

The FastAPI application implements additional endpoints for alarm flood analysis, rationalization candidates, calculation-code operations, and KPI definitions.

These capabilities are not currently exposed as separate tools in the existing MCP tool catalog.

**Impact:** The investigation workflow cannot access every API capability through MCP tool discovery.

**Future improvement:** Add the required MCP tools and corresponding tests, based on the assessment's API requirements.

### 2.2 API Contract Validation

The API routes and integration mappings are implemented, but every request and response schema has not yet been independently verified against a formal API contract.

**Impact:** Changes to request fields or response formats could break MCP integration.

**Future improvement:** Add API contract tests and document representative request and response examples.

### 2.3 Error and Partial-Failure Handling

The integration has timeout and retry handling, but all possible API, MCP, and network failure scenarios have not yet been validated end to end.

**Impact:** A failed dependency may leave an investigation with incomplete information.

**Future improvement:** Test individual tool failures, unavailable services, invalid arguments, retries, and partial results. Clearly identify missing information in the final report.

## 3. RAG Limitations

### 3.1 Demonstration Procedure Corpus

The current procedure documents are synthetic demonstration material. They are not approved industrial operating procedures.

**Impact:** The generated report cannot be used as an authoritative operational instruction.

**Future improvement:** Use authorized, reviewed documents and preserve their revision, approval status, and source information.

### 3.2 Retrieval Quality

The current pipeline uses vector similarity search in ChromaDB and a relevance threshold.

Hybrid keyword-plus-vector retrieval and a reranking stage are not implemented.

**Impact:** Relevant content may be missed, and semantically similar but inapplicable content may be retrieved.

**Future improvement:** Build a representative evaluation dataset, measure retrieval quality, and compare vector, hybrid, and reranked retrieval.

### 3.3 Metadata Quality

Document metadata is extracted during ingestion. Missing source information or document fields may limit filtering and traceability.

**Impact:** The system cannot reliably apply a metadata constraint when the required metadata is absent or inaccurate.

**Future improvement:** Validate metadata during ingestion and flag missing or inconsistent fields.

### 3.4 Index Refresh

The vector index is persisted locally. A complete document lifecycle for updates, deletions, revision replacement, and stale-chunk removal needs further validation.

**Impact:** An updated procedure could leave outdated chunks in the index if re-indexing is not handled correctly.

**Future improvement:** Implement deterministic document IDs, revision-aware indexing, and tests for update and deletion behavior.

## 4. LLM Limitations

### 4.1 Unconfirmed Root-Cause Hypotheses

The LLM may suggest possible explanations based on alarm details and retrieved evidence.

**Impact:** A plausible explanation is not proof of the actual root cause.

**Future improvement:** Label hypotheses explicitly, distinguish observations from inferences, and validate report claims against structured data and retrieved evidence.

### 4.2 Local Model Performance

The application uses a local Ollama model. Response quality and latency depend on model size, prompt design, context length, and available hardware.

**Impact:** Investigation reports may take a significant amount of time to generate.

**Future improvement:** Benchmark latency and report quality, optimize context selection, and consider configurable timeouts and alternative models.

### 4.3 Grounding Limitations

Prompt instructions encourage evidence-based reporting, but prompts alone cannot guarantee that every generated statement is supported by retrieved material.

**Impact:** Unsupported statements may still appear in a report.

**Future improvement:** Add automated claim-to-evidence checks and regression tests for unsupported or contradictory claims.

## 5. Performance and Observability

### 5.1 Investigation Latency

An investigation combines multiple tool calls, RAG retrieval, and LLM report generation.

**Impact:** Total response time can be significantly longer than the time taken by an individual API request.

**Future improvement:** Measure MCP startup, tool discovery, API requests, retrieval, and report generation separately. Optimize bottlenecks based on measured timings.

### 5.2 Local Execution

The current development setup runs locally and depends on installed Python packages, the local vector index, and the Ollama runtime.

**Impact:** Results may differ across machines if dependency versions, models, or data are inconsistent.

**Future improvement:** Add containerized deployment, dependency reproducibility, health checks, and automated environment validation.

## 6. Security Limitations

### 6.1 Demo Authentication

The application supports bearer-token authentication, and the local development setup uses a demonstration token.

**Impact:** A demonstration configuration is not sufficient by itself for production security.

**Future improvement:** Use securely managed credentials, stronger access controls, secret rotation, and environment-specific configuration.

### 6.2 Calculation-Code Execution

The API includes calculation-code generation and execution endpoints.

**Impact:** Executing untrusted code can introduce serious security risks if execution is not appropriately isolated.

**Future improvement:** Review the implementation, enforce strict input validation, and use a dedicated sandbox with resource and permission restrictions before accepting untrusted code.

### 6.3 Debug Endpoint

The application includes a debug fixture-summary endpoint.

**Impact:** Debug information may expose internal implementation details if available to unauthorized users.

**Future improvement:** Restrict or disable debug functionality outside the intended development environment.

### 6.4 Prompt Injection

Retrieved documents and user-provided queries may contain instructions that conflict with the intended system behavior.

**Impact:** Malicious content could influence generated output if it is not treated as untrusted data.

**Future improvement:** Add explicit prompt-injection tests, separate instructions from retrieved evidence, and validate generated recommendations against application safety rules.

## 7. Testing and Delivery

### 7.1 End-to-End Coverage

Automated tests cover API behavior, LLM handling, and RAG processing. Complete coverage of all MCP workflows and failure scenarios still requires validation.

**Future improvement:** Add end-to-end tests combining MCP discovery, API tool calls, procedure retrieval, and report generation.

### 7.2 Packaging and CI

Container packaging and an automated CI workflow have not yet been completed.

**Impact:** A reviewer may need to configure the environment manually.

**Future improvement:** Add a Dockerfile, Docker Compose configuration where appropriate, a repeatable setup process, and automated test execution in CI.

### 7.3 Documentation and Demonstration

The project documentation is being expanded. Architecture diagrams, a complete MCP catalog, representative investigation examples, and a recorded demonstration should be verified before submission.

**Future improvement:** Ensure that documentation matches the final implementation and that the demonstration uses clearly labeled synthetic data.

## 8. Operational Safety

This application is a decision-support demonstration. It is not an autonomous industrial control system.

- It must not claim that a proposed action has been executed.
- It must not independently authorize equipment isolation, repair, or restart.
- It must distinguish observed facts from unconfirmed hypotheses.
- It must identify missing or insufficient evidence.
- Any real-world operational action must follow approved procedures and authorized personnel's direction.

## 9. Summary

The current application demonstrates the integration of structured alarm data, MCP tool invocation, vector-based procedure retrieval, and LLM-generated investigation reports.

The primary areas for improvement are complete MCP coverage, retrieval evaluation, end-to-end reliability, latency instrumentation, security hardening, reproducible packaging, and submission documentation.

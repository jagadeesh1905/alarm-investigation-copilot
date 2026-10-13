# MCP Tool Catalog

## 1. Overview

The Alarm Investigation and Procedure Guidance Copilot uses a Python MCP client to discover and invoke tools exposed by the MCP server in `mcp_server.py`.

The MCP server acts as the integration boundary between the investigation orchestrator and the Alarm Management API simulator. Procedure retrieval is also exposed through an MCP tool, allowing alarm information and document evidence to participate in the same investigation workflow.

The server currently defines ten tools.

## 2. Tool Inventory

| Tool | Purpose | Source |
|---|---|---|
| `search_assets` | Find assets matching search criteria | Alarm Management API |
| `get_asset_metadata` | Retrieve metadata for an asset | Alarm Management API |
| `get_alarm` | Retrieve a specific alarm | Alarm Management API |
| `list_alarms` | List alarms using supported filters and pagination | Alarm Management API |
| `get_alarm_summary` | Retrieve an alarm summary | Alarm Management API |
| `get_alarm_trends` | Retrieve alarm trend information | Alarm Management API |
| `correlate_alarms` | Retrieve alarm correlation results | Alarm Management API |
| `score_alarm_priority` | Retrieve the priority score for an alarm | Alarm Management API |
| `get_operator_recommendations` | Retrieve operator action recommendations | Alarm Management API |
| `search_procedures` | Retrieve relevant procedure-document chunks | Local RAG pipeline |

## 3. Tool Contracts

The MCP SDK publishes the tool definitions and input schemas through tool discovery. The exact parameter names, types, required fields, and output structures must match the definitions in `mcp_server.py`.

The following sections describe the intended usage. Use the schemas returned by MCP tool discovery as the authoritative contracts.

### 3.1 `search_assets`

**Purpose:** Search for assets using supported criteria.

**Source operation:** `GET /assets/search`

**Inputs:** Search query and any supported filtering or result-limit parameters.

**Output:** Matching asset information and associated metadata returned by the source API.

**Errors:** Invalid input, authentication failure, API errors, timeouts, and connection failures are handled by the server's API-call layer.

**Example intent:** Find the asset associated with a compressor or motor.

### 3.2 `get_asset_metadata`

**Purpose:** Retrieve details for a known asset identifier.

**Source operation:** `GET /assets/{asset_id}/metadata`

**Inputs:** `asset_id`; optional trace identifier.

**Output:** Asset metadata returned by the source API.

**Example intent:** Retrieve metadata for `AST-504`.

### 3.3 `get_alarm`

**Purpose:** Retrieve an individual alarm record.

**Source operation:** `GET /alarms/{alarm_id}`

**Inputs:** `alarm_id`; optional trace identifier.

**Output:** The alarm record returned by the source API.

**Example intent:** Retrieve the details of `ALM-006`.

### 3.4 `list_alarms`

**Purpose:** List alarms with supported filters and pagination.

**Source operation:** `GET /alarms`

**Inputs:** Supported alarm filters, time-range criteria, sorting or pagination parameters, and optional trace metadata.

**Output:** Alarm records and pagination information returned by the source API.

**Pagination:** The tool implementation includes logic to request subsequent pages, subject to its configured maximum-page limit.

**Example intent:** Find active alarms for a particular asset.

### 3.5 `get_alarm_summary`

**Purpose:** Obtain a summary of alarm information.

**Source operation:** `POST /alarms/summary`

**Inputs:** The summary request fields defined by the MCP tool schema.

**Output:** Summary information returned by the API.

**Example intent:** Summarize alarms for a selected site, unit, asset, or time range, where supported by the request schema.

### 3.6 `get_alarm_trends`

**Purpose:** Retrieve alarm trend information.

**Source operation:** `POST /alarms/trends`

**Inputs:** The trend request fields defined by the MCP tool schema.

**Output:** Trend data returned by the API.

**Example intent:** Examine alarm activity over a selected time period.

### 3.7 `correlate_alarms`

**Purpose:** Retrieve correlation results for alarms.

**Source operation:** `POST /alarms/correlation`

**Inputs:** Correlation criteria defined by the MCP tool schema.

**Output:** Correlation results returned by the API.

**Example intent:** Investigate whether multiple alarms may be related.

**Important:** Correlation results are evidence for investigation, not proof of a common root cause.

### 3.8 `score_alarm_priority`

**Purpose:** Retrieve a priority score for a specific alarm.

**Source operation:** `POST /alarms/priority-score`

**Inputs:** `alarm_id`; optional trace identifier.

**Output:** The priority score and associated fields returned by the API.

**Example intent:** Retrieve the priority score for `ALM-006`.

### 3.9 `get_operator_recommendations`

**Purpose:** Retrieve suggested operator actions from the API simulator.

**Source operation:** `POST /recommendations/operator-actions`

**Inputs:** The recommendation request fields defined by the MCP tool schema.

**Output:** Recommendations returned by the API.

**Safety:** Recommendations must be treated according to their evidence and approval status. They must not be presented as authorization to operate or repair industrial equipment.

### 3.10 `search_procedures`

**Purpose:** Retrieve relevant chunks from the local procedure corpus.

**Source:** The RAG pipeline and persistent ChromaDB index.

**Inputs:** A procedure search query and any additional parameters defined by the tool schema.

**Output:** Matching text chunks with source metadata, including available document identifiers, titles, revisions, approval status, sections, and chunk information.

**Retrieval:** Sentence Transformers generates the query embedding. ChromaDB retrieves candidate chunks using vector similarity and the configured relevance threshold.

**Example intent:** Search for procedure evidence relevant to a motor trip.

**Safety:** Retrieved documents may be synthetic demonstration material. Retrieval alone does not establish that a procedure is approved or safe for operational use.

## 4. Authentication and Configuration

The MCP server reads configuration from environment variables.

| Variable | Purpose |
|---|---|
| `ALARM_API_BASE_URL` | Base URL for the Alarm Management API |
| `ALARM_API_TOKEN` | Bearer token used for API authentication |
| `ALARM_API_TIMEOUT_SECONDS` | Timeout for an API request |
| `ALARM_API_MAX_RETRIES` | Maximum configured retry count |
| `ALARM_API_RETRY_BACKOFF_SECONDS` | Delay used for retry backoff |
| `ALARM_API_MAX_PAGES` | Maximum pages processed by pagination logic |
| `MCP_CLIENT_ID` | Client identifier supplied by configuration |
| `LOG_LEVEL` | Logging verbosity |

The MCP server sends the configured bearer token in the API authorization header. Trace metadata is propagated where supported.

Secrets must not be committed to source control, printed in logs, or returned in tool output. Use `.env.example` for documented placeholder values.

## 5. Error Handling and Reliability

The API-call helper in `mcp_server.py` centralizes HTTP requests and handles API errors, request timeouts, and configured retries.

The implementation includes:

- Typed tool input definitions.
- API authentication headers.
- Configurable request timeouts.
- Retry settings and backoff configuration.
- API error mapping.
- Trace metadata propagation.
- Pagination handling for alarm listing.
- Logging for troubleshooting.

The MCP client also applies a configured tool-call timeout. Tool discovery and invocation failures should be handled by the orchestration layer without fabricating missing alarm data or procedure evidence.

The precise retryable status codes, retry count semantics, output schemas, and error response examples should be verified against the implementation and tests before making stronger reliability claims.

## 6. MCP Tool Discovery

The investigation orchestrator initializes an MCP client session, requests the server's available tool definitions, and invokes the tools needed for the investigation.

Tool discovery provides the client with the published tool names and input schemas. The orchestration layer can then use the available tools for alarm retrieval, asset lookup, and related analysis.

For debugging, the investigation response includes discovered tool information and tool execution trace records.

## 7. Example Investigation Flow

For a request such as:

> Investigate alarm ALM-006 and find relevant procedure evidence.

The orchestration workflow can:

1. Discover the MCP tools.
2. Invoke `get_alarm` to retrieve the alarm.
3. Invoke `get_asset_metadata` to retrieve asset information.
4. Invoke `list_alarms` to obtain relevant active alarms.
5. Invoke `correlate_alarms` and `score_alarm_priority` where applicable.
6. Invoke `get_operator_recommendations` where applicable.
7. Invoke `search_procedures` to retrieve procedure evidence.
8. Generate the investigation report with citations, warnings, and execution details.

The actual sequence depends on the implemented orchestration logic and the tools available at runtime.

## 8. Current Scope and Limitations

The MCP server exposes selected Alarm Management API operations. The simulator also has routes for operations such as flood analysis, rationalization candidates, calculation-code generation and execution, and KPI definitions; these routes are not represented by the ten MCP tools listed above.

Those operations should not be described as MCP-accessible until corresponding tools and tests are implemented.

The project uses simulated alarm data and synthetic procedure documents. This catalog describes a demonstration integration and does not imply a connection to a live industrial control system.

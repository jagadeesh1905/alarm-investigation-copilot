# API Integration

## 1. Overview

The Alarm Investigation Copilot integrates with a FastAPI-based alarm and asset API. The API provides alarm data, asset metadata, alarm analytics, priority scoring, and operator recommendations.

The MCP server acts as an integration layer between the MCP client and the FastAPI application. It translates MCP tool requests into HTTP API calls and returns structured results to the client.

## 2. Integration Architecture


flowchart TD
    A[Alarm Investigation Client] --> B[MCP Client]
    B --> C[MCP Server]
    C --> D[FastAPI Alarm API]
    D --> E[Alarm and Asset Data]
    C --> F[RAG Procedure Search]
    B --> G[Investigation Orchestration]
    G --> H[LLM Report Generation]

The main integration components are:

- **MCP client:** Starts an MCP session, discovers available tools, and invokes them.
- **MCP server:** Exposes tools and maps supported operations to HTTP API endpoints.
- **FastAPI application:** Handles authentication, request processing, alarm and asset queries, and analytics.
- **RAG pipeline:** Retrieves relevant procedure evidence from the local document collection.
- **Investigation orchestration:** Combines API results, retrieved evidence, and generated analysis into an investigation report.

## 3. API Endpoints

The following endpoints are implemented in the FastAPI application.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Check application health |
| POST | `/investigations` | Run an alarm investigation |
| GET | `/assets/search` | Search for assets |
| GET | `/assets/{asset_id}/metadata` | Retrieve asset metadata |
| GET | `/alarms` | List alarms with filtering and pagination |
| GET | `/alarms/{alarm_id}` | Retrieve a specific alarm |
| POST | `/alarms/summary` | Generate an alarm summary |
| POST | `/alarms/trends` | Analyze alarm trends |
| POST | `/alarms/correlation` | Correlate alarms |
| POST | `/alarms/flood-analysis` | Analyze alarm floods |
| POST | `/alarms/rationalization-candidates` | Identify rationalization candidates |
| POST | `/alarms/priority-score` | Calculate alarm priority scores |
| POST | `/recommendations/operator-actions` | Retrieve operator action recommendations |
| POST | `/calculation-code/generate` | Generate calculation code |
| POST | `/calculation-code/execute` | Execute calculation code |
| GET | `/analytics/kpi-definitions` | Retrieve KPI definitions |
| GET | `/debug/fixture-summary` | Inspect fixture summary information |

The exact request and response schemas should be confirmed against the application's route definitions and the interactive API documentation at `/docs`.

## 4. Authentication

Protected API endpoints use bearer-token authentication.

Clients send the token in the HTTP `Authorization` header:

```http
Authorization: Bearer <ALARM_API_TOKEN>
```

The FastAPI application supports a configurable `ALARM_API_TOKEN`. The local development configuration uses `demo-token` as the default when no token is configured.

The MCP server reads its API token from the environment and includes it when calling protected API endpoints.

**Security considerations:**

- Do not commit `.env` or real credentials to source control.
- Use environment-specific credentials outside local development.
- Keep `.env.example` limited to placeholders and non-sensitive defaults.
- Verify that debug endpoints are disabled or protected appropriately before deployment.

## 5. MCP-to-API Mapping

The current MCP server exposes the following tools that integrate with the API or local RAG pipeline.

| MCP tool | Integration |
|---|---|
| `search_assets` | `GET /assets/search` |
| `get_asset_metadata` | `GET /assets/{asset_id}/metadata` |
| `get_alarm` | `GET /alarms/{alarm_id}` |
| `list_alarms` | `GET /alarms` |
| `get_alarm_summary` | `POST /alarms/summary` |
| `get_alarm_trends` | `POST /alarms/trends` |
| `correlate_alarms` | `POST /alarms/correlation` |
| `score_alarm_priority` | `POST /alarms/priority-score` |
| `get_operator_recommendations` | `POST /recommendations/operator-actions` |
| `search_procedures` | Local RAG retrieval; not a direct FastAPI endpoint |

The API implements additional capabilities for flood analysis, rationalization candidates, calculation-code operations, and KPI definitions. These endpoints are not currently exposed as separate tools in the listed MCP tool catalog.

## 6. Traceability

The application supports trace metadata to help associate API activity with an investigation.

The investigation orchestration creates a trace ID and records tool execution details, including timing and status information. API requests also pass trace metadata through the integration layer.

Trace information helps with:

- Identifying which tool calls belong to an investigation.
- Investigating API errors and timeouts.
- Understanding the sequence of tool execution.
- Comparing the time spent in API calls and report generation.

Trace IDs are diagnostic identifiers; they should not be treated as authentication credentials.

## 7. Pagination

The alarm-listing MCP tool supports pagination by requesting additional pages from the API and combining the returned alarm records.

The maximum number of pages is configurable through:

```text
ALARM_API_MAX_PAGES
```

A page limit helps prevent an unbounded pagination loop. The integration should handle incomplete results and communicate when the configured page limit prevents retrieval of all records.

## 8. Timeouts and Retries

The MCP server uses configurable HTTP timeouts and retry behavior.

| Environment variable | Purpose | Default |
|---|---|---|
| `ALARM_API_TIMEOUT_SECONDS` | HTTP API request timeout | `15` |
| `ALARM_API_MAX_RETRIES` | Maximum retry count | `2` |
| `ALARM_API_RETRY_BACKOFF_SECONDS` | Base retry delay | `0.5` |
| `ALARM_API_MAX_PAGES` | Maximum alarm-list pages | `20` |

Retries use exponential backoff for transient failures. Retry behavior should be limited to errors where retrying is appropriate. Non-idempotent operations, especially code execution or operations that modify state, require additional care to avoid duplicate side effects.

The investigation endpoint has a separate timeout configuration and may return a timeout response if report generation exceeds its limit.

## 9. Error Handling

The integration should distinguish between:

- **Authentication failures:** The token is missing or invalid.
- **Validation errors:** The request contains missing or invalid fields.
- **Not-found errors:** The requested alarm or asset does not exist.
- **Transient API failures:** The service is temporarily unavailable.
- **Timeouts:** The API or investigation takes longer than the configured limit.
- **MCP failures:** Tool discovery, invocation, or session communication fails.
- **RAG evidence limitations:** No sufficiently relevant procedure evidence is found.

Errors should be recorded in logs and investigation trace information where possible. The application should avoid presenting a failed tool call as a successful result.

If a tool fails, the investigation should preserve any valid results already collected and clearly identify missing information instead of silently inventing data.

## 10. Configuration

The following environment variables are relevant to API integration:

```text
ALARM_API_BASE_URL=http://127.0.0.1:8000
ALARM_API_TOKEN=<configure-locally>
ALARM_API_TIMEOUT_SECONDS=15
ALARM_API_MAX_RETRIES=2
ALARM_API_RETRY_BACKOFF_SECONDS=0.5
ALARM_API_MAX_PAGES=20
MCP_CLIENT_ID=alarm-copilot-mcp
LOG_LEVEL=INFO
```

Use `.env.example` as the configuration template and configure local values in `.env`. Do not commit real credentials.

## 11. Testing Strategy

API integration testing should cover:

1. Health endpoint availability.
2. Authentication success and failure.
3. Asset search and asset metadata retrieval.
4. Alarm retrieval, unknown alarm IDs, and alarm listing.
5. Pagination behavior and maximum-page limits.
6. Trace metadata propagation.
7. API validation errors and transient failures.
8. Timeout behavior.
9. MCP tool-to-endpoint mapping.
10. End-to-end investigation using API data and RAG procedure evidence.

The existing automated API tests cover several of these behaviors, including authentication, route behavior, trace propagation, unknown alarms, and investigation timeout handling. Additional tests should be added when implementing new integration behavior.

## 12. Current Limitations

- The MCP tool catalog does not yet expose every implemented API capability.
- The exact request and response schemas should be verified against the live FastAPI application.
- Pagination completeness depends on the configured page limit and API behavior.
- End-to-end response time includes MCP session setup, API calls, retrieval, and LLM generation.
- The debug fixture endpoint should be reviewed before any non-local deployment.
- Calculation-code execution requires an explicit security review before being considered safe for untrusted input or production use.

## 13. Future Improvements

- Expose additional API capabilities through well-defined MCP tools where required.
- Add contract tests for API request and response schemas.
- Add structured error codes and consistent error responses.
- Improve timing instrumentation for MCP initialization and tool discovery.
- Add integration tests for retry behavior, pagination limits, and partial failures.
- Add request correlation across API, MCP, RAG, and LLM components.
- Review authentication, authorization, and code-execution isolation before production deployment.

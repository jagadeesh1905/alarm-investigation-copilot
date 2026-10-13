"""Alarm Investigation MCP server (stdio transport).

Exposes the Alarm Management API and the procedure RAG index as MCP tools.

Engineering features:
- typed, validated tool inputs (pydantic constraints; IDs are pattern-checked,
  which also keeps them safe to place in URL paths)
- bearer-token auth, read from the environment (never logged or returned)
- trace propagation: trace_id / x-client-id / x-metadata-tag headers
- timeout + retry with exponential backoff for transient failures
- API errors mapped to readable MCP tool errors (isError=True)
- pagination handling for list_alarms (fetch_all)
- structured logging to stderr (stdout is the MCP protocol channel)
- every result carries an "_mcp" block (trace_id, status, attempts, duration)
  that the orchestrator can show in the GUI trace panel

Run independently:  python mcp_server.py
"""
import asyncio
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, Literal

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import Field

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is optional here
    pass

# --------------------------------------------------------------------------
# Configuration (environment variables; see .env.example)
# --------------------------------------------------------------------------
API_BASE_URL = os.getenv("ALARM_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
API_TOKEN = os.getenv("ALARM_API_TOKEN", "")
API_TIMEOUT_SECONDS = float(os.getenv("ALARM_API_TIMEOUT_SECONDS", "15"))
API_MAX_RETRIES = int(os.getenv("ALARM_API_MAX_RETRIES", "2"))
RETRY_BACKOFF_SECONDS = float(os.getenv("ALARM_API_RETRY_BACKOFF_SECONDS", "0.5"))
CLIENT_ID = os.getenv("MCP_CLIENT_ID", "alarm-copilot-mcp")
MAX_PAGES = int(os.getenv("ALARM_API_MAX_PAGES", "20"))

RETRYABLE_STATUS = {429, 502, 503, 504}

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    stream=sys.stderr,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("alarm-mcp")

# The RAG stack (torch, chromadb, sentence-transformers) is imported here, at
# startup and on the main thread, not lazily inside a running event loop.
# Importing it lazily inside a tool hung on Windows stdio subprocesses.
try:
    import rag_pipeline

    _RAG_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # noqa: BLE001 - reported when the tool is called
    rag_pipeline = None
    _RAG_IMPORT_ERROR = exc

mcp = FastMCP("Alarm Investigation Tools")

# --------------------------------------------------------------------------
# Typed inputs
# --------------------------------------------------------------------------
ID_PATTERN = r"^[A-Za-z0-9_-]{1,50}$"

AlarmId = Annotated[
    str, Field(pattern=ID_PATTERN, description="Alarm identifier, e.g. ALM-005.")
]
AssetId = Annotated[
    str, Field(pattern=ID_PATTERN, description="Asset identifier, e.g. AST-203.")
]
TraceId = Annotated[
    str | None,
    Field(
        max_length=100,
        description="Optional correlation id; a new one is generated if omitted.",
    ),
]
Severity = Literal["low", "medium", "high", "critical"]


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _parse_iso(name: str, value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ToolError(
            f"Invalid {name}: expected an ISO 8601 timestamp such as "
            f"2026-05-01T00:00:00Z."
        ) from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _time_range(start_time: str | None, end_time: str | None) -> dict | None:
    if start_time is None and end_time is None:
        return None
    if start_time is None or end_time is None:
        raise ToolError("start_time and end_time must be provided together.")
    if _parse_iso("start_time", start_time) > _parse_iso("end_time", end_time):
        raise ToolError("start_time must not be after end_time.")
    return {"start_time": start_time, "end_time": end_time}


def _compact(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def _map_http_error(
    tool: str, response: httpx.Response, trace_id: str, attempts: int
) -> ToolError:
    """Turn an API error response into a readable MCP tool error."""
    status = response.status_code
    code = "http_error"
    message = response.text[:200]

    try:
        body = response.json()
        detail = body.get("detail", body) if isinstance(body, dict) else body
        if isinstance(detail, dict):
            code = detail.get("error", code)
            message = detail.get("message", message)
        elif isinstance(detail, list):  # FastAPI validation errors
            code = "invalid_request"
            message = "The alarm API rejected the request parameters."
        elif isinstance(detail, str):
            message = detail
    except ValueError:
        pass

    if status == 401:
        code, message = "authentication_failed", "The alarm API rejected the credentials."
    elif status in (400, 422) and code == "http_error":
        code = "invalid_request"
    elif status >= 500:
        code = "upstream_unavailable" if code == "http_error" else code

    return ToolError(
        f"{tool} failed: {code} (HTTP {status}): {message} "
        f"[attempts={attempts}, trace_id={trace_id}]"
    )


async def call_api(
    tool: str,
    path: str,
    *,
    method: str = "GET",
    params: dict | None = None,
    json_body: dict | None = None,
    trace_id: str | None = None,
    metadata_tag: str | None = None,
) -> tuple[Any, dict]:
    """Call the Alarm Management API with auth, tracing, timeout and retries.

    Returns (parsed_json, meta). Raises ToolError for any failure.
    """
    if not API_TOKEN:
        raise ToolError(
            f"{tool} failed: configuration_error: ALARM_API_TOKEN is not set "
            f"for the MCP server."
        )

    trace_id = trace_id or str(uuid.uuid4())
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "trace_id": trace_id,
        "x-client-id": CLIENT_ID,
    }
    if metadata_tag:
        headers["x-metadata-tag"] = metadata_tag

    attempts_allowed = API_MAX_RETRIES + 1
    started_total = time.perf_counter()

    async with httpx.AsyncClient(
        base_url=API_BASE_URL, timeout=API_TIMEOUT_SECONDS
    ) as client:
        for attempt in range(1, attempts_allowed + 1):
            started = time.perf_counter()

            try:
                response = await client.request(
                    method, path, headers=headers, params=params, json=json_body
                )
            except httpx.TransportError as exc:
                logger.warning(
                    "tool=%s path=%s attempt=%d/%d trace_id=%s transport_error=%s",
                    tool, path, attempt, attempts_allowed, trace_id,
                    type(exc).__name__,
                )
                if attempt < attempts_allowed:
                    await asyncio.sleep(RETRY_BACKOFF_SECONDS * 2 ** (attempt - 1))
                    continue
                kind = (
                    "timeout"
                    if isinstance(exc, httpx.TimeoutException)
                    else "api_unreachable"
                )
                raise ToolError(
                    f"{tool} failed: {kind}: the alarm API did not respond after "
                    f"{attempts_allowed} attempt(s) [trace_id={trace_id}]"
                ) from exc

            duration_ms = round((time.perf_counter() - started) * 1000)
            logger.info(
                "tool=%s path=%s attempt=%d/%d trace_id=%s status=%d duration_ms=%d",
                tool, path, attempt, attempts_allowed, trace_id,
                response.status_code, duration_ms,
            )

            if response.status_code in RETRYABLE_STATUS and attempt < attempts_allowed:
                await asyncio.sleep(RETRY_BACKOFF_SECONDS * 2 ** (attempt - 1))
                continue

            if response.is_success:
                try:
                    data = response.json()
                except ValueError as exc:
                    raise ToolError(
                        f"{tool} failed: invalid_response: the alarm API returned "
                        f"non-JSON content [trace_id={trace_id}]"
                    ) from exc

                meta = {
                    "trace_id": trace_id,
                    "api_status": response.status_code,
                    "attempts": attempt,
                    "retries": attempt - 1,
                    "duration_ms": round((time.perf_counter() - started_total) * 1000),
                }
                return data, meta

            raise _map_http_error(tool, response, trace_id, attempt)

    raise ToolError(f"{tool} failed: unexpected_state [trace_id={trace_id}]")


def _finish(data: Any, meta: dict) -> dict:
    """Attach the MCP trace block to a tool result."""
    if isinstance(data, dict):
        return {**data, "_mcp": meta}
    return {"result": data, "_mcp": meta}


# --------------------------------------------------------------------------
# Tools: assets
# --------------------------------------------------------------------------
@mcp.tool()
async def search_assets(
    query: Annotated[
        str,
        Field(
            min_length=1,
            max_length=100,
            description="Asset name, asset ID or asset type, e.g. 'Boiler Feed Pump 101'.",
        ),
    ],
    limit: Annotated[int, Field(ge=1, le=100)] = 10,
    site: Annotated[str | None, Field(max_length=100)] = None,
    unit: Annotated[str | None, Field(max_length=100)] = None,
    trace_id: TraceId = None,
) -> dict:
    """Resolve an asset name, ID or type to asset records (use this first to get an asset_id)."""
    data, meta = await call_api(
        "search_assets",
        "/assets/search",
        params=_compact({"query": query, "limit": limit, "site": site, "unit": unit}),
        trace_id=trace_id,
    )
    return _finish(data, meta)


@mcp.tool()
async def get_asset_metadata(asset_id: AssetId, trace_id: TraceId = None) -> dict:
    """Get asset metadata, including related assets in the same site and unit."""
    data, meta = await call_api(
        "get_asset_metadata", f"/assets/{asset_id}/metadata", trace_id=trace_id
    )
    return _finish(data, meta)


# --------------------------------------------------------------------------
# Tools: alarms
# --------------------------------------------------------------------------
@mcp.tool()
async def get_alarm(alarm_id: AlarmId, trace_id: TraceId = None) -> dict:
    """Get the full record of one alarm by alarm ID."""
    data, meta = await call_api("get_alarm", f"/alarms/{alarm_id}", trace_id=trace_id)
    return _finish(data, meta)


@mcp.tool()
async def list_alarms(
    status: Literal["active", "cleared", "all"] = "active",
    asset_id: AssetId | None = None,
    severity: list[Severity] | None = None,
    site: Annotated[str | None, Field(max_length=100)] = None,
    unit: Annotated[str | None, Field(max_length=100)] = None,
    start_time: str | None = None,
    end_time: str | None = None,
    page: Annotated[int, Field(ge=1)] = 1,
    page_size: Annotated[int, Field(ge=1, le=200)] = 50,
    sort_by: Literal["start_time", "severity", "priority", "alarm_name"] = "start_time",
    sort_order: Literal["asc", "desc"] = "desc",
    fetch_all: Annotated[
        bool,
        Field(description="If true, follow pagination and merge pages (capped)."),
    ] = False,
    trace_id: TraceId = None,
) -> dict:
    """List alarms filtered by status, asset, severity, site, unit or time window (ISO 8601)."""
    _time_range(start_time, end_time)  # validates format and ordering

    params = _compact(
        {
            "status": None if status == "all" else status,
            "asset_id": asset_id,
            "severity": ",".join(severity) if severity else None,
            "site": site,
            "unit": unit,
            "start_time": start_time,
            "end_time": end_time,
            "page": page,
            "page_size": page_size,
            "sort_by": sort_by,
            "sort_order": sort_order,
        }
    )

    data, meta = await call_api("list_alarms", "/alarms", params=params, trace_id=trace_id)

    if fetch_all:
        items = list(data.get("items", []))
        total_pages = int(data.get("total_pages", 1))
        current = page
        pages_fetched = 1

        while current < total_pages and pages_fetched < MAX_PAGES:
            current += 1
            pages_fetched += 1
            next_page, _ = await call_api(
                "list_alarms",
                "/alarms",
                params={**params, "page": current},
                trace_id=meta["trace_id"],
            )
            items.extend(next_page.get("items", []))

        data = {
            **data,
            "items": items,
            "pages_fetched": pages_fetched,
            "truncated": current < total_pages,
        }
        meta["pages_fetched"] = pages_fetched

    return _finish(data, meta)


@mcp.tool()
async def get_alarm_summary(
    asset_ids: list[AssetId] | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    severity: list[Severity] | None = None,
    group_by: list[
        Literal["alarm_name", "severity", "asset_id", "unit", "site", "status"]
    ] | None = None,
    trace_id: TraceId = None,
) -> dict:
    """Summarize alarm counts, critical counts, recurrence and acknowledgement delay by group."""
    body = _compact(
        {
            "asset_ids": asset_ids or [],
            "time_range": _time_range(start_time, end_time),
            "severity": severity or [],
            "group_by": group_by or ["alarm_name"],
            "kpis": ["alarm_count", "recurring_rate", "avg_ack_delay"],
        }
    )
    data, meta = await call_api(
        "get_alarm_summary", "/alarms/summary", method="POST",
        json_body=body, trace_id=trace_id,
    )
    return _finish(data, meta)


@mcp.tool()
async def get_alarm_trends(
    asset_ids: list[AssetId] | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    trace_id: TraceId = None,
) -> dict:
    """Get daily alarm-count trends, optionally for specific assets and a time window."""
    body = _compact(
        {
            "asset_ids": asset_ids or [],
            "time_range": _time_range(start_time, end_time),
            "bucket": "daily",
            "metrics": ["alarm_count", "avg_ack_delay"],
        }
    )
    data, meta = await call_api(
        "get_alarm_trends", "/alarms/trends", method="POST",
        json_body=body, trace_id=trace_id,
    )
    return _finish(data, meta)


@mcp.tool()
async def correlate_alarms(
    asset_id: AssetId,
    start_time: str | None = None,
    end_time: str | None = None,
    lag_window_minutes: Annotated[int, Field(ge=1, le=1440)] = 15,
    severity_threshold: Severity = "medium",
    min_support: Annotated[int, Field(ge=1)] = 1,
    trace_id: TraceId = None,
) -> dict:
    """Find alarms that co-occur with alarms on the given assets (correlation is not causation)."""
    body = _compact(
        {
            "asset_ids": [asset_id],
            "time_range": _time_range(start_time, end_time),
            "correlation_method": "cooccurrence",
            "lag_window_minutes": lag_window_minutes,
            "severity_threshold": severity_threshold,
            "min_support": min_support,
        }
    )

    logger.info(
        "correlate_alarms request body=%s",
        body,
    )
    data, meta = await call_api(
        "correlate_alarms", "/alarms/correlation", method="POST",
        json_body=body, trace_id=trace_id,
    )
    return _finish(data, meta)


@mcp.tool()
async def score_alarm_priority(alarm_id: AlarmId, trace_id: TraceId = None) -> dict:
    """Get the simulator's priority score and contributing factors for an alarm."""
    data, meta = await call_api(
        "score_alarm_priority", "/alarms/priority-score", method="POST",
        json_body={"alarm_id": alarm_id}, trace_id=trace_id,
    )
    return _finish(data, meta)


@mcp.tool()
async def get_operator_recommendations(
    alarm_id: AlarmId,
    include_related: bool = True,
    include_asset_context: bool = True,
    include_historical_pattern: bool = True,
    trace_id: TraceId = None,
) -> dict:
    """Get the API's recommended operator actions for an alarm (compare these with procedure documents)."""
    data, meta = await call_api(
        "get_operator_recommendations", "/recommendations/operator-actions",
        method="POST",
        json_body={
            "alarm_id": alarm_id,
            "include_related": include_related,
            "include_asset_context": include_asset_context,
            "include_historical_pattern": include_historical_pattern,
        },
        trace_id=trace_id,
    )
    return _finish(data, meta)


# --------------------------------------------------------------------------
# Tool: document RAG
# --------------------------------------------------------------------------
@mcp.tool()
async def search_procedures(
    query: Annotated[str, Field(min_length=1, max_length=500)],
    top_k: Annotated[int, Field(ge=1, le=10)] = 3,
    trace_id: TraceId = None,
) -> dict:
    """Search procedure and troubleshooting documents; returns cited chunks, or none if confidence is low."""
    trace_id = trace_id or str(uuid.uuid4())
    started = time.perf_counter()

    try:
        if rag_pipeline is None:
            raise RuntimeError(f"RAG pipeline unavailable: {_RAG_IMPORT_ERROR}")
        # Called directly (no worker thread): the configuration that worked.
        matches = rag_pipeline.search_procedures(query, top_k=top_k)
    except Exception as exc:
        logger.error(
            "tool=search_procedures trace_id=%s failed=%s", trace_id, type(exc).__name__
        )
        raise ToolError(
            f"search_procedures failed: procedure_search_failed: {exc} "
            f"[trace_id={trace_id}]"
        ) from exc

    duration_ms = round((time.perf_counter() - started) * 1000)
    logger.info(
        "tool=search_procedures trace_id=%s results=%d duration_ms=%d",
        trace_id, len(matches), duration_ms,
    )

    return {
        "query": query,
        "result_count": len(matches),
        "results": matches,
        "low_confidence": len(matches) == 0,
        "_mcp": {
            "trace_id": trace_id,
            "attempts": 1,
            "retries": 0,
            "duration_ms": duration_ms,
        },
    }


if __name__ == "__main__":
    # Load the embedding model now, on the main thread, before serving. Loading
    # it lazily inside the running event loop hung on Windows stdio subprocesses.
    if rag_pipeline is not None:
        try:
            rag_pipeline.warm_up()
        except Exception as exc:  # noqa: BLE001 - the tool reports the failure on use
            logger.error("RAG warm-up failed: %s", exc)
    mcp.run(transport="stdio")

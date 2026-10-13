
import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path
from contextlib import AsyncExitStack

from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from llm_service import generate_investigation_report


PROJECT_DIR = Path(__file__).resolve().parent
load_dotenv(PROJECT_DIR / ".env")

MCP_TOOL_TIMEOUT_SECONDS = float(
    os.getenv("MCP_TOOL_TIMEOUT_SECONDS", "120")
)


def _decode_tool_result(result):
    """Convert an MCP tool result into a Python value."""
    if getattr(result, "isError", False):
        messages = [
            item.text
            for item in result.content
            if hasattr(item, "text")
        ]
        raise RuntimeError(
            "; ".join(messages) or "MCP tool returned an error"
        )

    messages = [
        item.text
        for item in result.content
        if hasattr(item, "text")
    ]

    if not messages:
        raise RuntimeError("MCP tool returned no text content")

    text_result = "\n".join(messages)

    try:
        return json.loads(text_result)
    except json.JSONDecodeError:
        return text_result


async def _call_tool(session, tool_name, arguments, trace, timings):
    """Call an MCP tool and record duration and outcome."""
    started = time.perf_counter()

    record = {
        "tool": tool_name,
        "arguments": arguments,
        "status": "started",
    }
    trace.append(record)

    try:
        result = await asyncio.wait_for(
            session.call_tool(tool_name, arguments),
            timeout=MCP_TOOL_TIMEOUT_SECONDS,
        )

        value = _decode_tool_result(result)
        record["status"] = "success"
        return value

    except asyncio.TimeoutError:
        record["status"] = "timeout"
        record["error"] = (
            f"Tool exceeded {MCP_TOOL_TIMEOUT_SECONDS} seconds"
        )
        raise

    except Exception as exc:
        record["status"] = "error"
        record["error"] = str(exc)
        raise

    finally:
        elapsed = round(time.perf_counter() - started, 3)
        record["duration_seconds"] = elapsed

        timings[tool_name] = round(
            timings.get(tool_name, 0) + elapsed, 3
        )


async def _try_tool(
    session,
    tool_name,
    arguments,
    trace,
    timings,
    warnings,
):
    """Run an optional tool without aborting the investigation."""
    try:
        return await _call_tool(
            session,
            tool_name,
            arguments,
            trace,
            timings,
        )
    except Exception as exc:
        warnings.append(
            f"{tool_name} could not be completed: {exc}"
        )
        return None


async def run_investigation(alarm_id):
    """Run the MCP and RAG investigation workflow."""
    overall_started = time.perf_counter()
    trace_id = str(uuid.uuid4())

    tool_trace = []
    timings = {}
    warnings = []

    requested_alarm = None
    asset = None
    related_alarms = []
    correlations = None
    priority = None
    operator_recommendations = None
    procedure_evidence = []
    discovered_tool_names = []

    server_path = PROJECT_DIR / "mcp_server.py"

    if not server_path.exists():
        raise FileNotFoundError(
            f"MCP server file not found: {server_path}"
        )

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(server_path)],
        cwd=str(PROJECT_DIR),
        env={
            **os.environ,
            "ALARM_API_BASE_URL": os.getenv(
                "ALARM_API_BASE_URL",
                "http://127.0.0.1:8000",
            ),
            "ALARM_API_TOKEN": os.getenv(
                "ALARM_API_TOKEN",
                "demo-token",
            ),
        },
    )

    # Measure the full MCP context, including cleanup.
    mcp_context_started = time.perf_counter()

    # These timestamps let us measure shutdown independently.
    mcp_context_exited = False

    try:
        async with AsyncExitStack() as stack:
            mcp_setup_started = time.perf_counter()

            # 1. Start the MCP server and establish stdio streams.
            startup_started = time.perf_counter()

            read_stream, write_stream = (
                await stack.enter_async_context(
                    stdio_client(server_params)
                )
            )

            timings["mcp_startup_seconds"] = round(
                time.perf_counter() - startup_started, 3
            )

            # 2. Create and initialize the MCP client session.
            session = await stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )

            initialize_started = time.perf_counter()
            await session.initialize()

            timings["mcp_session_initialize_seconds"] = round(
                time.perf_counter() - initialize_started, 3
            )

            # 3. Discover tools provided by the MCP server.
            discovery_started = time.perf_counter()
            discovered = await session.list_tools()

            timings["mcp_tool_discovery_seconds"] = round(
                time.perf_counter() - discovery_started, 3
            )

            timings["mcp_session_setup_seconds"] = round(
                time.perf_counter() - mcp_setup_started, 3
            )

            available_tools = {
                tool.name: tool
                for tool in discovered.tools
            }
            discovered_tool_names = sorted(
                available_tools.keys()
            )

            def has_tool(name):
                return name in available_tools

            # 4. Retrieve the requested alarm. This is essential.
            if not has_tool("get_alarm"):
                raise RuntimeError(
                    "The MCP server does not expose get_alarm"
                )

            requested_alarm = await _call_tool(
                session,
                "get_alarm",
                {"alarm_id": alarm_id},
                tool_trace,
                timings,
            )

            if not isinstance(requested_alarm, dict):
                raise RuntimeError(
                    "get_alarm did not return an alarm object"
                )

            # 5. Identify the asset associated with the alarm.
            asset_id = (
                requested_alarm.get("asset_id")
                or requested_alarm.get("assetId")
            )

            if asset_id and has_tool("get_asset_metadata"):
                asset = await _try_tool(
                    session,
                    "get_asset_metadata",
                    {"asset_id": asset_id},
                    tool_trace,
                    timings,
                    warnings,
                )

            # Compatibility fallback for MCP servers that expose
            # search_assets rather than get_asset_metadata.
            if (
                not asset
                and asset_id
                and has_tool("search_assets")
            ):
                asset = await _try_tool(
                    session,
                    "search_assets",
                    {"query": asset_id},
                    tool_trace,
                    timings,
                    warnings,
                )

            # Unwrap a common search-results response shape.
            if isinstance(asset, dict) and isinstance(
                asset.get("results"), list
            ):
                asset = (
                    asset["results"][0]
                    if asset["results"]
                    else None
                )

            # 6. Retrieve active alarms for the same asset.
            if has_tool("list_alarms"):
                alarm_list_result = await _try_tool(
                    session,
                    "list_alarms",
                    {"status": "active"},
                    tool_trace,
                    timings,
                    warnings,
                )

                if isinstance(alarm_list_result, list):
                    all_alarms = alarm_list_result
                elif isinstance(alarm_list_result, dict):
                    all_alarms = (
                        alarm_list_result.get("alarms")
                        or alarm_list_result.get("items")
                        or alarm_list_result.get("results")
                        or []
                    )
                else:
                    all_alarms = []

                related_alarms = [
                    item
                    for item in all_alarms
                    if isinstance(item, dict)
                    and item.get("alarm_id", item.get("id"))
                    != alarm_id
                    and (
                        not asset_id
                        or item.get(
                            "asset_id", item.get("assetId")
                        ) == asset_id
                    )
                    and str(
                        item.get("status", "")
                    ).lower() == "active"
                ]

            # 7. Correlate alarms for this asset.
            if asset_id and has_tool("correlate_alarms"):
                correlations = await _try_tool(
                    session,
                    "correlate_alarms",
                    {"asset_id": asset_id},
                    tool_trace,
                    timings,
                    warnings,
                )

            # 8. Score the requested alarm's priority.
            if has_tool("score_alarm_priority"):
                priority = await _try_tool(
                    session,
                    "score_alarm_priority",
                    {"alarm_id": alarm_id},
                    tool_trace,
                    timings,
                    warnings,
                )

            # 9. Retrieve operator recommendations.
            if has_tool("get_operator_recommendations"):
                operator_recommendations = await _try_tool(
                    session,
                    "get_operator_recommendations",
                    {"alarm_id": alarm_id},
                    tool_trace,
                    timings,
                    warnings,
                )

            # 10. Retrieve procedure evidence.
            if has_tool("search_procedures"):
                query = " ".join(
                    str(value)
                    for value in [
                        requested_alarm.get("name", ""),
                        requested_alarm.get("alarm_name", ""),
                        requested_alarm.get("description", ""),
                        asset_id or "",
                        (
                            asset.get("asset_type", "")
                            if isinstance(asset, dict)
                            else ""
                        ),
                    ]
                    if value
                ).strip()

                try:
                    evidence_result = await _call_tool(
                        session,
                        "search_procedures",
                        {"query": query or alarm_id},
                        tool_trace,
                        timings,
                    )

                    if isinstance(evidence_result, list):
                        procedure_evidence = evidence_result
                    elif isinstance(evidence_result, dict):
                        procedure_evidence = (
                            evidence_result.get("results")
                            or evidence_result.get("documents")
                            or evidence_result.get("evidence")
                            or []
                        )

                    if not isinstance(procedure_evidence, list):
                        procedure_evidence = []

                except Exception as exc:
                    warnings.append(
                        f"Procedure search failed: {exc}"
                    )
            else:
                warnings.append(
                    "The MCP server does not expose search_procedures"
                )

    finally:
        # This runs after AsyncExitStack has closed, including when
        # the MCP workflow raises an exception.
        mcp_context_exited = time.perf_counter()

        timings["mcp_context_total_seconds"] = round(
            mcp_context_exited - mcp_context_started, 3
        )

        # This measures time outside the recorded setup and tool calls.
        # It includes teardown plus any other uninstrumented MCP work.
        recorded_mcp_time = (
            timings.get("mcp_session_setup_seconds", 0)
            + sum(
                record.get("duration_seconds", 0)
                for record in tool_trace
            )
        )

        timings["mcp_unaccounted_seconds"] = round(
            max(
                0,
                timings["mcp_context_total_seconds"]
                - recorded_mcp_time,
            ),
            3,
        )

    # 11. Generate the report using the existing LLM service.
    report_started = time.perf_counter()

    
    try:
        investigation_report = await asyncio.to_thread(
            generate_investigation_report,
            requested_alarm,
            asset or {},
            related_alarms,
            procedure_evidence,
        )
    except Exception as exc:
        warnings.append(
            f"Report generation failed: {type(exc).__name__}: {exc}"
        )
        investigation_report = (
            "## Investigation Report Unavailable\n\n"
            "The alarm data was retrieved, but report generation "
            "did not complete successfully. Review the retrieved "
            "evidence and consult authorized personnel."
        )

    timings["generate_investigation_report"] = round(
        time.perf_counter() - report_started, 3
    )


    # 12. Record the complete investigation duration.
    timings["total_seconds"] = round(
        time.perf_counter() - overall_started, 3
    )

    return {
        "trace_id": trace_id,
        "requested_alarm": requested_alarm,
        "asset": asset,
        "related_assets": [],
        "active_alarms_for_asset": related_alarms,
        "priority": priority,
        "operator_recommendations": operator_recommendations,
        "recommendation_check": None,
        "correlations": correlations,
        "procedure_evidence": procedure_evidence,
        "citations": [
            {
                "evidence_id": f"E{index}",
                "title": item.get("title"),
                "doc_id": item.get("doc_id"),
                "revision": item.get("revision"),
                "status": item.get("approval_status"),
                "source": item.get("source"),
            }
            for index, item in enumerate(
                procedure_evidence, start=1
            )
            if isinstance(item, dict)
        ],
        "low_confidence_evidence": [],
        "investigation_report": investigation_report,
        "investigation_status": "completed",
        "status": "completed",
        "warnings": warnings,
        "discovered_tools": discovered_tool_names,
        "tool_trace": tool_trace,
        "timings": timings,
    }


async def main():
    alarm_id = (
        sys.argv[1] if len(sys.argv) > 1 else "ALM-005"
    )

    result = await run_investigation(alarm_id)

    print("\n=== Investigation Result ===\n")
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())

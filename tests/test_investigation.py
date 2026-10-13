
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

import investigation


def mcp_result(text=None, is_error=False):
    content = [] if text is None else [
        SimpleNamespace(text=text)
    ]
    return SimpleNamespace(isError=is_error, content=content)


def test_decode_tool_result_parses_json():
    result = mcp_result('{"alarm_id": "ALM-006"}')

    decoded = investigation._decode_tool_result(result)

    assert decoded == {"alarm_id": "ALM-006"}


def test_decode_tool_result_returns_plain_text():
    result = mcp_result("Procedure search completed")

    decoded = investigation._decode_tool_result(result)

    assert decoded == "Procedure search completed"


def test_decode_tool_result_rejects_empty_content():
    with pytest.raises(RuntimeError, match="no text content"):
        investigation._decode_tool_result(mcp_result())


def test_decode_tool_result_rejects_mcp_error():
    result = mcp_result("Unknown alarm", is_error=True)

    with pytest.raises(RuntimeError, match="Unknown alarm"):
        investigation._decode_tool_result(result)


@pytest.mark.asyncio
async def test_call_tool_records_success_and_duration():
    session = SimpleNamespace(
        call_tool=AsyncMock(
            return_value=mcp_result('{"status": "ok"}')
        )
    )
    trace = []
    timings = {}

    result = await investigation._call_tool(
        session, "get_alarm", {"alarm_id": "ALM-006"},
        trace, timings
    )

    assert result == {"status": "ok"}
    assert trace[0]["tool"] == "get_alarm"
    assert trace[0]["status"] == "success"
    assert trace[0]["duration_seconds"] >= 0
    assert timings["get_alarm"] >= 0


@pytest.mark.asyncio
async def test_call_tool_records_failure():
    session = SimpleNamespace(
        call_tool=AsyncMock(side_effect=RuntimeError("tool unavailable"))
    )
    trace = []
    timings = {}

    with pytest.raises(RuntimeError, match="tool unavailable"):
        await investigation._call_tool(
            session, "get_alarm", {"alarm_id": "ALM-006"},
            trace, timings
        )

    assert trace[0]["status"] == "error"
    assert "tool unavailable" in trace[0]["error"]
    assert "get_alarm" in timings


@pytest.mark.asyncio
async def test_call_tool_records_timeout():
    session = SimpleNamespace(
        call_tool=AsyncMock(side_effect=asyncio.TimeoutError)
    )
    trace = []
    timings = {}

    with patch.object(investigation, "MCP_TOOL_TIMEOUT_SECONDS", 0.01):
        with pytest.raises(asyncio.TimeoutError):
            await investigation._call_tool(
                session, "get_alarm", {"alarm_id": "ALM-006"},
                trace, timings
            )

    assert trace[0]["status"] == "timeout"
    assert "get_alarm" in timings


@pytest.mark.asyncio
async def test_try_tool_returns_none_and_records_warning():
    session = SimpleNamespace(
        call_tool=AsyncMock(side_effect=RuntimeError("service unavailable"))
    )
    trace = []
    timings = {}
    warnings = []

    result = await investigation._try_tool(
        session, "get_asset_metadata", {"asset_id": "AST-504"},
        trace, timings, warnings
    )

    assert result is None
    assert len(warnings) == 1
    assert "get_asset_metadata" in warnings[0]
    assert trace[0]["status"] == "error"


class FakeSession:
    def __init__(self, responses):
        self.responses = responses
        self.call_history = []

    async def initialize(self):
        return None

    async def list_tools(self):
        return SimpleNamespace(
            tools=[
                SimpleNamespace(name=name)
                for name in self.responses
            ]
        )

    async def call_tool(self, name, arguments):
        self.call_history.append((name, arguments))

        response = self.responses[name]
        if isinstance(response, Exception):
            raise response
        return mcp_result(json.dumps(response))


class FakeAsyncContext:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_run_investigation_builds_report_and_citations():
    alarm = {
        "alarm_id": "ALM-006",
        "asset_id": "AST-504",
        "name": "Motor trip",
        "status": "active",
    }
    evidence = [{
        "title": "Motor trip procedure",
        "doc_id": "DEMO-MTR-001",
        "revision": "1",
        "approval_status": "SYNTHETIC DEMONSTRATION ONLY",
        "source": "sample_motor_trip_procedure.txt",
    }]
    responses = {
        "get_alarm": alarm,
        "get_asset_metadata": {
            "asset_id": "AST-504",
            "asset_type": "Motor",
        },
        "list_alarms": [],
        "correlate_alarms": {"correlations": []},
        "score_alarm_priority": {"priority": 97},
        "get_operator_recommendations": {"recommendations": []},
        "search_procedures": evidence,
    }
    session = FakeSession(responses)

    with (
        patch.object(
            investigation,
            "stdio_client",
            return_value=FakeAsyncContext(("read", "write")),
        ),
        patch.object(
            investigation,
            "ClientSession",
            return_value=FakeAsyncContext(session),
        ),
        patch.object(
            investigation,
            "generate_investigation_report",
            return_value="Mocked grounded report",
        ),
    ):
        result = await investigation.run_investigation("ALM-006")

    assert result["requested_alarm"] == alarm
    assert result["asset"]["asset_id"] == "AST-504"
    assert result["investigation_status"] == "completed"
    assert result["investigation_report"] == "Mocked grounded report"
    assert result["citations"][0]["doc_id"] == "DEMO-MTR-001"
    assert result["citations"][0]["status"] == "SYNTHETIC DEMONSTRATION ONLY"
    assert "get_alarm" in result["discovered_tools"]
    assert any(
        item["tool"] == "get_alarm" and item["status"] == "success"
        for item in result["tool_trace"]
    )

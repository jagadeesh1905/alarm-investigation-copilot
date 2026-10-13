from fastapi.testclient import TestClient
from app.main import app
from unittest.mock import AsyncMock, patch
import asyncio
client = TestClient(app)
AUTH = {"Authorization": "Bearer demo-token"}

def test_health_is_available():
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json()['status'] == 'ok'

def test_authentication_is_required():
    response = client.get('/assets/search', params={'query': 'pump'})
    assert response.status_code == 401

def test_asset_search():
    response = client.get('/assets/search', params={'query': 'Boiler Feed Pump 102'}, headers=AUTH)
    assert response.status_code == 200
    assert response.json()['items'][0]['asset_id'] == 'AST-102'

def test_get_active_alarms_for_asset():
    response = client.get('/alarms', params={'asset_id': 'AST-102', 'status': 'active'}, headers=AUTH)
    assert response.status_code == 200
    assert response.json()['total'] == 2

def test_priority_score_unknown_alarm_returns_404():
    response = client.post('/alarms/priority-score', json={'alarm_id': 'DOES-NOT-EXIST'}, headers=AUTH)
    assert response.status_code == 404

def test_trace_id_is_propagated():
    response = client.post('/alarms/summary', json={'asset_ids': ['AST-102'], 'group_by': ['alarm_name']}, headers={**AUTH, 'trace_id': 'test-trace-123'})
    assert response.status_code == 200
    assert response.headers['trace_id'] == 'test-trace-123'
    assert response.json()['trace']['trace_id'] == 'test-trace-123'

def test_investigation_returns_mocked_report():
    mock_report = {
        "alarm_id": "ALM-006",
        "report": "Mock investigation report",
    }

    with patch(
        "app.main.run_investigation",
        new_callable=AsyncMock,
        return_value=mock_report,
    ) as mock_investigation:
        response = client.post(
            "/investigations",
            json={"alarm_id": "ALM-006"},
            headers=AUTH,
        )

    assert response.status_code == 200
    assert response.json() == mock_report
    mock_investigation.assert_awaited_once_with("ALM-006")

def test_investigation_rejects_blank_alarm_id():
    response = client.post(
        "/investigations",
        json={"alarm_id": "   "},
        headers=AUTH,
    )

    assert response.status_code == 422

def test_investigation_requires_authentication():
    response = client.post(
        "/investigations",
        json={"alarm_id": "ALM-006"},
    )

    assert response.status_code == 401

def test_investigation_unknown_alarm_returns_404():
    response = client.post(
        "/investigations",
        json={"alarm_id": "ALM-999"},
        headers=AUTH,
    )

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "alarm_not_found"

def test_investigation_timeout_returns_504():
    async def slow_investigation(alarm_id):
        await asyncio.sleep(1)

    with patch(
        "app.main.run_investigation",
        new_callable=AsyncMock,
        side_effect=asyncio.TimeoutError,
    ):
        response = client.post(
            "/investigations",
            json={"alarm_id": "ALM-006"},
            headers=AUTH,
        )

    assert response.status_code == 504
    assert response.json()["detail"]["error"] == "investigation_timeout"

def test_investigation_trace_id_is_propagated():
    with patch(
        "app.main.run_investigation",
        new_callable=AsyncMock,
        return_value={"alarm_id": "ALM-006", "report": "Mock report"},
    ):
        response = client.post(
            "/investigations",
            json={"alarm_id": "ALM-006"},
            headers={**AUTH, "trace_id": "investigation-trace-123"},
        )

    assert response.status_code == 200
    assert response.headers["trace_id"] == "investigation-trace-123"
    assert response.headers["x-trace-id"] == "investigation-trace-123"

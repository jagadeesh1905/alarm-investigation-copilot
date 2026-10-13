"""FastAPI Alarm Management API simulator, aligned to the supplied Postman contract."""
import asyncio

from investigation import run_investigation
from collections import Counter, defaultdict
from datetime import datetime, timezone
import logging
import os
import uuid
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator  
from fastapi.middleware.cors import CORSMiddleware

from .data import ALARMS, ASSETS, RECOMMENDATIONS

load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("alarm-api")
TOKEN = os.getenv("ALARM_API_TOKEN", "demo-token")
security = HTTPBearer(auto_error=False)
app = FastAPI(title="Alarm Management API Simulator", version="0.1.0", description="Local simulator for the Alarm Investigation Copilot assignment")
CALCULATIONS: dict[str, dict[str, Any]] = {}


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TimeRange(BaseModel):
    start_time: str
    end_time: str

class SummaryRequest(BaseModel):
    asset_ids: list[str] = Field(default_factory=list)
    time_range: TimeRange | None = None
    severity: list[str] = Field(default_factory=list)
    group_by: list[str] = Field(default_factory=lambda: ["alarm_name"])
    kpis: list[str] = Field(default_factory=lambda: ["alarm_count"])

class TrendsRequest(BaseModel):
    asset_ids: list[str] = Field(default_factory=list)
    time_range: TimeRange | None = None
    bucket: str = "daily"
    metrics: list[str] = Field(default_factory=lambda: ["alarm_count"])

class CorrelationRequest(BaseModel):
    asset_ids: list[str] = Field(default_factory=list)
    time_range: TimeRange | None = None
    correlation_method: str = "cooccurrence"
    lag_window_minutes: int = Field(default=15, ge=1, le=1440)
    severity_threshold: str = "medium"
    min_support: int = Field(default=1, ge=1)

class FloodRequest(BaseModel):
    unit: str
    time_range: TimeRange | None = None
    threshold_count: int = Field(default=10, ge=1)
    rolling_window_minutes: int = Field(default=10, ge=1)

class RationalizationRequest(BaseModel):
    asset_ids: list[str] = Field(default_factory=list)
    time_range: TimeRange | None = None
    recurrence_threshold: int = Field(default=5, ge=1)
    stale_minutes_threshold: int = Field(default=180, ge=1)

class PriorityRequest(BaseModel):
    alarm_id: str

class RecommendationRequest(BaseModel):
    alarm_id: str
    include_related: bool = True
    include_asset_context: bool = True
    include_historical_pattern: bool = True


class InvestigationRequest(BaseModel):
    alarm_id: str = Field(min_length=1, max_length=50)

    @field_validator("alarm_id")
    @classmethod
    def validate_alarm_id(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Alarm ID must not be empty or whitespace.")

        return value

class GenerateCalculationRequest(BaseModel):
    calculation_type: str
    filters: dict[str, Any] = Field(default_factory=dict)

class ExecuteCalculationRequest(BaseModel):
    calculation_id: str
    filters: dict[str, Any] = Field(default_factory=dict)


def authenticate(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> None:
    if credentials is None or credentials.credentials != TOKEN:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "unauthorized",
                "message": "A valid bearer token is required.",
            },
        )

@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    trace_id = request.headers.get("trace_id") or request.headers.get("x-trace-id") or str(uuid.uuid4())
    response = await call_next(request)
    response.headers["trace_id"] = trace_id
    response.headers["x-trace-id"] = trace_id
    return response

@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception):
    logger.exception("Unhandled API simulator error path=%s", request.url.path)
    return JSONResponse(status_code=500, content={"error": "internal_error", "message": "An unexpected server error occurred."})

@app.get("/health")
def health():
    return {"status": "ok", "service": "alarm-management-api-simulator", "version": app.version}



@app.post("/investigations", dependencies=[Depends(authenticate)])
async def create_investigation(body: InvestigationRequest):
    """Run the complete MCP + RAG + local LLM alarm investigation."""
    alarm_id = body.alarm_id.strip()
    try:
        return await asyncio.wait_for(run_investigation(alarm_id), timeout=300)
    except asyncio.TimeoutError:
        raise HTTPException(504, detail={"error": "investigation_timeout", "message": "The investigation took too long."})

    # try:
    #     result = asyncio.run(investigate_alarm(alarm_id))
    #     return result

    except Exception as exc:
        logger.exception(
            "Alarm investigation failed for alarm_id=%s", alarm_id
        )

        # MCP may wrap the original 404 in nested exception groups.
        error_text = str(exc)

        exception_group = getattr(exc, "exceptions", None)
        while exception_group:
            nested_messages = []
            for nested_exc in exception_group:
                nested_messages.append(str(nested_exc))
                if getattr(nested_exc, "exceptions", None):
                    exception_group = nested_exc.exceptions
                    break
            else:
                error_text += " " + " ".join(nested_messages)
                break

            error_text += " " + " ".join(nested_messages)

        if (
            "alarm_not_found" in error_text
            and "get_alarm" in error_text
        ):
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "alarm_not_found",
                    "message": f"Alarm '{alarm_id}' was not found.",
                },
            ) from exc

        raise HTTPException(
            status_code=502,
            detail={
                "error": "investigation_failed",
                "message": (
                    "The investigation could not be completed. "
                    "Check the server terminal for details."
                ),
            },
        ) from exc

@app.get("/assets/search", dependencies=[Depends(authenticate)])
def search_assets(query: str = Query(min_length=1), limit: int = Query(default=10, ge=1, le=100), site: str | None = None, unit: str | None = None):
    q = query.casefold()
    results = [a for a in ASSETS if q in a["asset_name"].casefold() or q in a["asset_id"].casefold() or q in a["asset_type"].casefold()]
    if site: results = [a for a in results if a["site"].casefold() == site.casefold()]
    if unit: results = [a for a in results if a["unit"].casefold() == unit.casefold()]
    return {"items": results[:limit], "count": min(len(results), limit), "total": len(results), "query": query}

@app.get("/assets/{asset_id}/metadata", dependencies=[Depends(authenticate)])
def asset_metadata(asset_id: str):
    asset = next((a for a in ASSETS if a["asset_id"].casefold() == asset_id.casefold()), None)
    if not asset: raise HTTPException(404, detail={"error": "asset_not_found", "message": f"Asset '{asset_id}' was not found."})
    related = [a for a in ASSETS if a["asset_id"] != asset_id and a["site"] == asset["site"] and a["unit"] == asset["unit"]]
    return {**asset, "related_assets": related}

def _filtered_alarms(asset_id=None, status=None, severity=None, site=None, unit=None, start_time=None, end_time=None):
    rows = list(ALARMS)
    if asset_id: rows = [a for a in rows if a["asset_id"].casefold() == asset_id.casefold()]
    if status: rows = [a for a in rows if a["status"].casefold() == status.casefold()]
    if severity: rows = [a for a in rows if a["severity"].casefold() in {s.casefold() for s in severity}]
    if site: rows = [a for a in rows if a["site"].casefold() == site.casefold()]
    if unit: rows = [a for a in rows if a["unit"].casefold() == unit.casefold()]
    def in_window(a):
        value = datetime.fromisoformat(a["start_time"].replace("Z", "+00:00"))
        if start_time and value < datetime.fromisoformat(start_time.replace("Z", "+00:00")): return False
        if end_time and value > datetime.fromisoformat(end_time.replace("Z", "+00:00")): return False
        return True
    if start_time or end_time: rows = [a for a in rows if in_window(a)]
    return rows

@app.get("/alarms", dependencies=[Depends(authenticate)])
def get_alarms(asset_id: str | None = None, status: str | None = None, severity: str | None = None, site: str | None = None, unit: str | None = None, start_time: str | None = None, end_time: str | None = None, page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=200), sort_by: str = "start_time", sort_order: str = "desc"):
    rows = _filtered_alarms(asset_id, status, severity.split(",") if severity else None, site, unit, start_time, end_time)
    if sort_by not in {"start_time", "severity", "priority", "alarm_name"}: raise HTTPException(400, detail={"error":"invalid_sort_field", "message":"Unsupported sort_by field."})
    rows.sort(key=lambda a: a.get(sort_by) or "", reverse=sort_order.lower() != "asc")
    total = len(rows); start = (page - 1) * page_size
    return {"items": rows[start:start + page_size], "page": page, "page_size": page_size, "total": total, "total_pages": (total + page_size - 1) // page_size}

@app.get("/alarms/{alarm_id}", dependencies=[Depends(authenticate)])
def get_alarm(alarm_id: str):
    alarm = next((a for a in ALARMS if a["alarm_id"].casefold() == alarm_id.casefold()), None)
    if not alarm: raise HTTPException(404, detail={"error":"alarm_not_found", "message":f"Alarm '{alarm_id}' was not found."})
    return alarm

@app.post("/alarms/summary", dependencies=[Depends(authenticate)])
def alarm_summary(body: SummaryRequest, trace_id: str | None = Header(default=None, alias="trace_id"), x_client_id: str | None = Header(default=None), x_metadata_tag: str | None = Header(default=None)):
    rows = _filtered_alarms()
    if body.asset_ids: rows = [a for a in rows if a["asset_id"] in body.asset_ids]
    if body.severity: rows = [a for a in rows if a["severity"] in body.severity]
    groups = defaultdict(list)
    for a in rows:
        key = tuple(a.get(k, "unknown") for k in body.group_by) if body.group_by else ("all",)
        groups[" | ".join(key)].append(a)
    summaries = []
    for key, items in groups.items():
        summaries.append({"group": key, "alarm_count": len(items), "active_count": sum(a["status"] == "active" for a in items), "critical_count": sum(a["severity"] == "critical" for a in items), "recurring_rate": round(sum(a["occurrences_24h"] > 1 for a in items) / len(items), 2) if items else 0, "avg_ack_delay_minutes": round(sum((datetime.fromisoformat(a["ack_time"].replace("Z", "+00:00")) - datetime.fromisoformat(a["start_time"].replace("Z", "+00:00"))).total_seconds()/60 for a in items if a["ack_time"]) / max(1, sum(bool(a["ack_time"]) for a in items)), 2)})
    return {"summary": summaries, "total_alarms": len(rows), "trace": {"trace_id": trace_id, "client_id": x_client_id, "metadata_tag": x_metadata_tag}}

@app.post("/alarms/trends", dependencies=[Depends(authenticate)])
def alarm_trends(body: TrendsRequest):
    rows = _filtered_alarms()
    if body.asset_ids: rows = [a for a in rows if a["asset_id"] in body.asset_ids]
    by_day = defaultdict(list)
    for a in rows: by_day[a["start_time"][:10]].append(a)
    points = [{"date": day, "alarm_count": len(items), "active_count": sum(a["status"] == "active" for a in items), "avg_ack_delay_minutes": round(sum((datetime.fromisoformat(a["ack_time"].replace("Z", "+00:00"))-datetime.fromisoformat(a["start_time"].replace("Z", "+00:00"))).total_seconds()/60 for a in items if a["ack_time"]) / max(1, sum(bool(a["ack_time"]) for a in items)), 2)} for day, items in sorted(by_day.items())]
    return {"bucket": body.bucket, "metrics": body.metrics, "points": points}

@app.post("/alarms/correlation", dependencies=[Depends(authenticate)])
def alarm_correlation(body: CorrelationRequest, trace_id: str | None = Header(default=None, alias="trace_id"), x_client_id: str | None = Header(default=None), x_metadata_tag: str | None = Header(default=None)):
    rows = _filtered_alarms()
    if body.asset_ids: rows = [a for a in rows if a["asset_id"] in body.asset_ids or any(x["asset_id"] in body.asset_ids and x["unit"] == a["unit"] for x in ALARMS)]
    #rows = [a for a in rows if ["low", "medium", "high", "critical"].index(a["severity"]) >= ["low", "medium", "high", "critical"].index(body.severity_threshold.lower())]
    
    severity_order = ["low", "medium", "high", "critical"]
    threshold = body.severity_threshold.lower()

    if threshold not in severity_order:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_severity_threshold",
                "message": "Unsupported severity threshold.",
            },
        )

    rows = [
        a for a in rows
        if severity_order.index(a["severity"].lower())
        >= severity_order.index(threshold)
    ]

    by_unit = defaultdict(list)
    for a in rows: by_unit[a["unit"]].append(a)
    pairs = []
    for unit, items in by_unit.items():
        if len(items) >= body.min_support:
            pairs.append({"unit": unit, "alarm_ids": [a["alarm_id"] for a in items], "alarm_names": sorted(set(a["alarm_name"] for a in items)), "support": len(items), "method": body.correlation_method, "interpretation": "Alarms share a unit; temporal causality is not established by this demo simulator."})
    return {"correlations": pairs, "trace": {"trace_id": trace_id, "client_id": x_client_id, "metadata_tag": x_metadata_tag}}

@app.post("/alarms/flood-analysis", dependencies=[Depends(authenticate)])
def flood_analysis(body: FloodRequest):
    rows = _filtered_alarms(unit=body.unit)
    count = len(rows)
    return {"unit": body.unit, "alarm_count": count, "threshold_count": body.threshold_count, "rolling_window_minutes": body.rolling_window_minutes, "flood_detected": count >= body.threshold_count, "note": "Demo calculation uses the selected unit's fixture records; it is not a time-windowed production flood detector."}

@app.post("/alarms/rationalization-candidates", dependencies=[Depends(authenticate)])
def rationalization_candidates(body: RationalizationRequest):
    rows = _filtered_alarms()
    if body.asset_ids: rows = [a for a in rows if a["asset_id"] in body.asset_ids]
    candidates = [{"alarm_id": a["alarm_id"], "asset_id": a["asset_id"], "alarm_name": a["alarm_name"], "occurrences_24h": a["occurrences_24h"], "reason": "Recurring alarm; review against the approved alarm philosophy."} for a in rows if a["occurrences_24h"] >= body.recurrence_threshold]
    return {"candidates": candidates, "count": len(candidates), "note": "Candidates are for engineering review; this API does not automatically suppress or change alarms."}

@app.post("/alarms/priority-score", dependencies=[Depends(authenticate)])
def priority_score(body: PriorityRequest):
    alarm = next((a for a in ALARMS if a["alarm_id"] == body.alarm_id), None)
    if not alarm: raise HTTPException(404, detail={"error":"alarm_not_found", "message":f"Alarm '{body.alarm_id}' was not found."})
    return {"alarm_id": alarm["alarm_id"], "priority_score": alarm["priority"], "severity": alarm["severity"], "factors": {"severity": alarm["severity"], "asset_criticality": next(a["criticality"] for a in ASSETS if a["asset_id"] == alarm["asset_id"]), "occurrences_24h": alarm["occurrences_24h"]}, "explanation": "Illustrative score from the simulator fixture; not a validated safety decision."}

@app.post("/recommendations/operator-actions", dependencies=[Depends(authenticate)])
def operator_recommendations(body: RecommendationRequest, trace_id: str | None = Header(default=None, alias="trace_id"), x_client_id: str | None = Header(default=None), x_metadata_tag: str | None = Header(default=None)):
    alarm = next((a for a in ALARMS if a["alarm_id"] == body.alarm_id), None)
    if not alarm: raise HTTPException(404, detail={"error":"alarm_not_found", "message":f"Alarm '{body.alarm_id}' was not found."})
    asset = next(a for a in ASSETS if a["asset_id"] == alarm["asset_id"])
    return {"alarm": alarm, "asset_context": asset if body.include_asset_context else None, "related_alarms": [a for a in ALARMS if a["asset_id"] == alarm["asset_id"] and a["alarm_id"] != alarm["alarm_id"]] if body.include_related else [], "historical_pattern": {"occurrences_24h": alarm["occurrences_24h"], "recurring": alarm["occurrences_24h"] > 1} if body.include_historical_pattern else None, "recommended_actions": RECOMMENDATIONS.get(alarm["alarm_id"], ["Consult the approved operating procedure for this alarm.", "Escalate unresolved conditions to the responsible operator."]), "trace": {"trace_id": trace_id, "client_id": x_client_id, "metadata_tag": x_metadata_tag}}

@app.post("/calculation-code/generate", dependencies=[Depends(authenticate)])
def generate_calculation(body: GenerateCalculationRequest):
    if body.calculation_type not in {"alarm_flood_index", "response_efficiency", "nuisance_alarm_rate", "critical_alarm_density"}:
        raise HTTPException(400, detail={"error":"unsupported_calculation", "message":"Unsupported calculation_type."})
    calculation_id = str(uuid.uuid4())
    CALCULATIONS[calculation_id] = {"calculation_type": body.calculation_type, "filters": body.filters, "created_at": datetime.now(timezone.utc).isoformat()}
    return {"calculation_id": calculation_id, "calculation_type": body.calculation_type, "status": "generated", "note": "The simulator stores a safe calculation descriptor; it does not generate or execute arbitrary source code."}

@app.post("/calculation-code/execute", dependencies=[Depends(authenticate)])
def execute_calculation(body: ExecuteCalculationRequest, trace_id: str | None = Header(default=None, alias="trace_id"), x_client_id: str | None = Header(default=None), x_metadata_tag: str | None = Header(default=None)):
    calc = CALCULATIONS.get(body.calculation_id)
    if not calc: raise HTTPException(404, detail={"error":"calculation_not_found", "message":"Generate a calculation descriptor before executing it."})
    rows = _filtered_alarms(unit=body.filters.get("unit"))
    result = {"alarm_count": len(rows), "active_count": sum(a["status"] == "active" for a in rows), "critical_count": sum(a["severity"] == "critical" for a in rows), "alarm_flood_index": round(sum(a["occurrences_24h"] for a in rows) / max(1, len(rows)), 2)}
    return {"calculation_id": body.calculation_id, "calculation_type": calc["calculation_type"], "result": result, "trace": {"trace_id": trace_id, "client_id": x_client_id, "metadata_tag": x_metadata_tag}}

@app.get("/analytics/kpi-definitions", dependencies=[Depends(authenticate)])
def kpi_definitions():
    return {"definitions": [{"name":"alarm_count", "description":"Number of alarm records in the selected data set"}, {"name":"active_count", "description":"Number of alarms whose status is active"}, {"name":"critical_count", "description":"Number of alarms with critical severity"}, {"name":"recurring_rate", "description":"Fraction of records with more than one occurrence in 24 hours"}, {"name":"avg_ack_delay", "description":"Mean delay in minutes between alarm start and acknowledgement"}]}

@app.get("/debug/fixture-summary", include_in_schema=False)
def fixture_summary():
    """Local-only helper for developers; intentionally not used by the copilot."""
    return {"assets": len(ASSETS), "alarms": len(ALARMS)}

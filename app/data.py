"""Small deterministic data set for the local Alarm Management API simulator."""
from datetime import datetime, timedelta, timezone

NOW = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)

def ts(minutes_ago: int) -> str:
    return (NOW - timedelta(minutes=minutes_ago)).isoformat().replace('+00:00', 'Z')

ASSETS = [
    {"asset_id": "AST-101", "asset_name": "Boiler Feed Pump 101", "site": "EastRefinery", "unit": "Unit 1", "asset_type": "Pump", "criticality": "high", "description": "Boiler feed pump serving Unit 1"},
    {"asset_id": "AST-102", "asset_name": "Boiler Feed Pump 102", "site": "EastRefinery", "unit": "Unit 1", "asset_type": "Pump", "criticality": "critical", "description": "Boiler feed pump serving Unit 1"},
    {"asset_id": "AST-203", "asset_name": "Compressor 203", "site": "EastRefinery", "unit": "Unit 2", "asset_type": "Compressor", "criticality": "high", "description": "Process gas compressor"},
    {"asset_id": "AST-504", "asset_name": "Motor 504", "site": "EastRefinery", "unit": "Unit 5", "asset_type": "Motor", "criticality": "medium", "description": "Cooling system drive motor"},
    {"asset_id": "AST-103", "asset_name": "Cooling Water Pump 103", "site": "WestRefinery", "unit": "Unit 2", "asset_type": "Pump", "criticality": "medium", "description": "Cooling water circulation pump"},
]

ALARMS = [
    {"alarm_id": "ALM-001", "asset_id": "AST-102", "alarm_name": "High discharge pressure", "description": "Discharge pressure exceeded configured threshold", "severity": "critical", "status": "active", "start_time": ts(12), "ack_time": ts(10), "end_time": None, "site": "EastRefinery", "unit": "Unit 1", "priority": 95, "occurrences_24h": 6},
    {"alarm_id": "ALM-002", "asset_id": "AST-102", "alarm_name": "High vibration", "description": "Vibration reading above alert threshold", "severity": "high", "status": "active", "start_time": ts(25), "ack_time": None, "end_time": None, "site": "EastRefinery", "unit": "Unit 1", "priority": 82, "occurrences_24h": 4},
    {"alarm_id": "ALM-003", "asset_id": "AST-101", "alarm_name": "Low flow", "description": "Flow rate below expected operating range", "severity": "medium", "status": "cleared", "start_time": ts(180), "ack_time": ts(175), "end_time": ts(160), "site": "EastRefinery", "unit": "Unit 1", "priority": 48, "occurrences_24h": 2},
    {"alarm_id": "ALM-004", "asset_id": "AST-203", "alarm_name": "High discharge pressure", "description": "Compressor discharge pressure high", "severity": "high", "status": "active", "start_time": ts(8), "ack_time": None, "end_time": None, "site": "EastRefinery", "unit": "Unit 2", "priority": 88, "occurrences_24h": 9},
    {"alarm_id": "ALM-005", "asset_id": "AST-203", "alarm_name": "High bearing temperature", "description": "Bearing temperature above normal range", "severity": "medium", "status": "active", "start_time": ts(40), "ack_time": ts(35), "end_time": None, "site": "EastRefinery", "unit": "Unit 2", "priority": 60, "occurrences_24h": 3},
    {"alarm_id": "ALM-006", "asset_id": "AST-504", "alarm_name": "Motor trip", "description": "Motor protective trip signal received", "severity": "critical", "status": "active", "start_time": ts(4), "ack_time": None, "end_time": None, "site": "EastRefinery", "unit": "Unit 5", "priority": 97, "occurrences_24h": 1},
    {"alarm_id": "ALM-007", "asset_id": "AST-103", "alarm_name": "Low suction pressure", "description": "Pump suction pressure below threshold", "severity": "low", "status": "cleared", "start_time": ts(300), "ack_time": ts(290), "end_time": ts(270), "site": "WestRefinery", "unit": "Unit 2", "priority": 25, "occurrences_24h": 1},
    {"alarm_id": "ALM-008", "asset_id": "AST-203", "alarm_name": "High discharge pressure", "description": "Repeated high pressure event", "severity": "high", "status": "active", "start_time": ts(70), "ack_time": ts(68), "end_time": None, "site": "EastRefinery", "unit": "Unit 2", "priority": 86, "occurrences_24h": 9},
]

RECOMMENDATIONS = {
    "ALM-001": ["Follow the approved high-discharge-pressure operating procedure.", "Verify current readings using the approved local instrument or control-room display.", "Escalate to the responsible operator if the condition persists."],
    "ALM-002": ["Follow the approved vibration inspection procedure.", "Check the trend and compare it with approved operating limits.", "Escalate abnormal or increasing vibration to the reliability team."],
    "ALM-004": ["Review the pressure trend and relevant operating conditions.", "Follow the approved compressor pressure-response procedure.", "Escalate persistent or worsening conditions."],
    "ALM-005": ["Review bearing-temperature trend and available equipment history.", "Follow the approved temperature inspection procedure."],
    "ALM-006": ["Follow the site-approved motor-trip response procedure.", "Do not restart equipment until required checks and authorization are complete.", "Escalate to the responsible operations and electrical teams."],
}

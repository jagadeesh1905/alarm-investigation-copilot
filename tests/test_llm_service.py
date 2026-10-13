
from unittest.mock import patch

from llm_service import (
    generate_investigation_report,
    _build_safety_section,
    _extract_json_object,
    _fallback_analysis,
    _format_procedure_evidence,
)


ALARM = {
    "alarm_id": "ALM-006",
    "alarm_name": "Motor trip",
    "description": "Motor trip alarm",
    "severity": "critical",
    "status": "active",
    "asset_id": "AST-504",
    "start_time": "2026-07-01T11:20:00Z",
    "priority": 97,
    "occurrences_24h": 1,
}

ASSET = {
    "asset_id": "AST-504",
    "asset_name": "Motor 504",
    "asset_type": "Motor",
    "site": "EastRefinery",
    "unit": "Unit 5",
    "criticality": "high",
}

SYNTHETIC_EVIDENCE = [{
    "source": "sample_procedures.txt",
    "doc_id": "DEMO-MTR-001",
    "title": "Example Motor Trip Procedure",
    "revision": "1",
    "approval_status": "SYNTHETIC DEMONSTRATION ONLY",
    "section": "Investigation Topics",
    "text": (
        "Example investigation topics:\n"
        "- Review the alarm timestamp and event logs.\n"
        "- Confirm the asset identity."
    ),
}]


def test_empty_model_response_is_rejected():
    import pytest

    with pytest.raises(ValueError):
        _extract_json_object("")

    with pytest.raises(ValueError):
        _extract_json_object("not valid JSON")


def test_json_parser_accepts_json_object():
    result = _extract_json_object(
        '{"possible_explanations": ["Unknown"], '
        '"recommended_checks": ["Review logs"]}'
    )

    assert result["possible_explanations"] == ["Unknown"]
    assert result["recommended_checks"] == ["Review logs"]


def test_fallback_analysis_does_not_claim_confirmed_root_cause():
    result = _fallback_analysis()

    assert "cannot be determined" in result["possible_explanations"].lower()
    assert "further evidence" in result["possible_explanations"].lower()


def test_synthetic_procedure_is_explicitly_labelled():
    evidence_text = _format_procedure_evidence(SYNTHETIC_EVIDENCE)

    assert "SYNTHETIC DEMONSTRATION ONLY" in evidence_text
    assert "DEMO-MTR-001" in evidence_text
    assert "sample_procedures.txt" in evidence_text


def test_no_evidence_does_not_claim_verified_procedure():
    evidence_text = _format_procedure_evidence([])

    assert "No procedure evidence was retrieved" in evidence_text
    assert "No procedure-based recommendation can be verified" in evidence_text


def test_safety_section_warns_when_evidence_is_synthetic():
    safety = _build_safety_section(ALARM, ASSET, SYNTHETIC_EVIDENCE)

    assert "CRITICAL" in safety
    assert "not approved maintenance guidance" in safety
    assert "root cause remain" in safety
    assert "Do not use this report as permission" in safety


def test_safety_section_warns_when_no_evidence_exists():
    safety = _build_safety_section(ALARM, ASSET, [])

    assert "No procedure evidence was retrieved" in safety
    assert "root cause remain" in safety
    assert "Do not use this report as permission" in safety


def test_report_assembles_deterministic_safety_and_evidence():
    with patch(
        "llm_service._generate_analysis",
        return_value={
            "possible_explanations": (
                "The root cause cannot be determined from the supplied data."
            ),
            "recommended_checks": (
                "1. Review the alarm timestamp [E1]"
            ),
        },
    ):
        report = generate_investigation_report(
            alarm_data=ALARM,
            asset_data=ASSET,
            related_alarms=[],
            procedure_evidence=SYNTHETIC_EVIDENCE,
        )

    assert "# 1. Alarm Summary" in report
    assert "# 4. Procedure Evidence" in report
    assert "# 5. Possible Explanations to Investigate" in report
    assert "# 7. Safety and Limitations" in report
    assert "DEMO-MTR-001" in report
    assert "SYNTHETIC DEMONSTRATION ONLY" in report
    assert "Do not use this report as permission" in report


def test_report_uses_safe_fallback_when_analysis_fails():
    with patch(
        "llm_service._generate_analysis",
        side_effect=RuntimeError("simulated model failure"),
    ):
        report = generate_investigation_report(
            alarm_data=ALARM,
            asset_data=ASSET,
            related_alarms=[],
            procedure_evidence=[],
        )

    assert "The root cause cannot be determined" in report
    assert "No procedure evidence was retrieved" in report
    assert "Do not use this report as permission" in report

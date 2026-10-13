
import json
from unittest.mock import MagicMock, patch

import pytest

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


@pytest.mark.parametrize(
    "response",
    [
        '{"possible_explanations": ["Unknown"]} trailing text',
        "Here is the result: {not valid JSON}",
        "[]",
        "null",
        "123",
    ],
)

def test_json_parser_rejects_invalid_or_non_object_responses(response):
    if response == '{"possible_explanations": ["Unknown"]} trailing text':
        result = _extract_json_object(response)
        assert result["possible_explanations"] == ["Unknown"]
    else:
        with pytest.raises((ValueError, TypeError)):
            _extract_json_object(response)

def test_json_parser_extracts_object_from_surrounding_text():
    response = (
        'Model output follows:\n'
        '{"possible_explanations": ["Inspect logs"], '
        '"recommended_checks": ["Check event history"]}\n'
        'End of response.'
    )

    result = _extract_json_object(response)

    assert result["possible_explanations"] == ["Inspect logs"]
    assert result["recommended_checks"] == ["Check event history"]


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
            "recommended_checks": "1. Review the alarm timestamp [E1]",
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


def test_report_includes_related_alarm_information():
    related_alarms = [{
        "alarm_id": "ALM-008",
        "alarm_name": "High discharge pressure",
        "severity": "high",
        "status": "active",
        "priority": 86,
    }]

    with patch(
        "llm_service._generate_analysis",
        return_value={
            "possible_explanations": "The cause remains unconfirmed.",
            "recommended_checks": "Review the event history.",
        },
    ):
        report = generate_investigation_report(
            alarm_data=ALARM,
            asset_data=ASSET,
            related_alarms=related_alarms,
            procedure_evidence=SYNTHETIC_EVIDENCE,
        )

    assert "ALM-008" in report
    assert "High discharge pressure" in report


def test_report_fallback_handles_empty_related_alarms():
    with patch(
        "llm_service._generate_analysis",
        side_effect=RuntimeError("simulated failure"),
    ):
        report = generate_investigation_report(
            alarm_data=ALARM,
            asset_data=ASSET,
            related_alarms=[],
            procedure_evidence=[],
        )

    assert "ALM-006" in report
    assert "Motor 504" in report


def test_analysis_failure_does_not_leak_exception_to_report():
    with patch(
        "llm_service._generate_analysis",
        side_effect=TimeoutError("simulated timeout"),
    ):
        report = generate_investigation_report(
            alarm_data=ALARM,
            asset_data=ASSET,
            related_alarms=[],
            procedure_evidence=[],
        )

    assert "simulated timeout" not in report
    assert "The root cause cannot be determined" in report


def test_json_parser_accepts_whitespace_around_object():
    result = _extract_json_object(
        '  \n {"possible_explanations": ["Unknown"]} \n '
    )

    assert result["possible_explanations"] == ["Unknown"]

def test_value_uses_first_non_empty_field():
    from llm_service import _value

    assert _value(
        {"first": " ", "second": "  Motor 504  "},
        "first",
        "second",
    ) == "Motor 504"


def test_value_returns_default_when_fields_missing():
    from llm_service import _value

    assert _value({}, "asset_name") == "Not supplied"


def test_unique_related_alarms_removes_current_and_duplicates():
    from llm_service import _unique_related_alarms

    alarms = [
        {"alarm_id": "ALM-006", "alarm_name": "Current alarm"},
        {"alarm_id": "ALM-008", "alarm_name": "Pressure high"},
        {"alarm_id": "ALM-008", "alarm_name": "Duplicate"},
        {"alarm_id": "", "alarm_name": "Missing ID"},
        {"alarm_id": "ALM-009", "alarm_name": "Temperature high"},
    ]

    result = _unique_related_alarms(ALARM, alarms)

    assert [item["alarm_id"] for item in result] == [
        "ALM-008",
        "ALM-009",
    ]


def test_related_alarm_formatter_handles_empty_list():
    from llm_service import _format_related_alarms

    result = _format_related_alarms([])

    assert "No additional related active alarms" in result


def test_related_alarm_formatter_includes_alarm_fields():
    from llm_service import _format_related_alarms

    result = _format_related_alarms([
        {
            "alarm_id": "ALM-008",
            "name": "High pressure",
            "severity": "high",
            "priority": 86,
        }
    ])

    assert "ALM-008" in result
    assert "High pressure" in result
    assert "high" in result
    assert "86" in result


def test_safety_section_handles_unknown_severity():
    safety = _build_safety_section(
        {"alarm_id": "ALM-X", "severity": "unknown"},
        ASSET,
        [],
    )

    assert "not supplied or is unrecognized" in safety
    assert "Do not assume a severity classification" in safety



def test_safety_section_distinguishes_high_severity_from_criticality():
    safety = _build_safety_section(
        {"alarm_id": "ALM-X", "severity": "high"},
        ASSET,
        [],
    )

    assert "HIGH" in safety
    assert "Asset criticality is high" in safety
    assert "Do not treat these as interchangeable classifications" in safety



def test_procedure_evidence_handles_missing_fields():
    result = _format_procedure_evidence([
        {"text": "Check the event history."}
    ])

    assert "Unknown source" in result
    assert "Not supplied" in result
    assert "Check the event history." in result


def test_analysis_uses_deterministic_explanation_and_procedure_checks():
    from llm_service import _generate_analysis

    fake_response = MagicMock()
    fake_response.message.content = json.dumps({
        "possible_explanations": ["The motor definitely failed."],
        "recommended_checks": ["Restart the motor immediately."],
    })

    with patch("llm_service.ollama.Client") as client_class:
        client_class.return_value.chat.return_value = fake_response

        result = _generate_analysis(
            alarm_data=ALARM,
            asset_data=ASSET,
            related_alarms=[],
            procedure_evidence=SYNTHETIC_EVIDENCE,
        )

    assert "cannot be determined" in result["possible_explanations"]
    assert "definitely failed" not in result["possible_explanations"]
    assert "Restart the motor immediately" not in result["recommended_checks"]
    assert "Review the alarm timestamp and event logs" in result["recommended_checks"]
    assert "[E1]" in result["recommended_checks"]


def test_analysis_uses_safe_checks_when_procedure_has_no_extractable_topics():
    from llm_service import _generate_analysis

    fake_response = MagicMock()
    fake_response.message.content = json.dumps({
        "possible_explanations": ["Unknown"],
        "recommended_checks": ["Unverified action"],
    })

    evidence = [{
        "source": "empty-procedure.txt",
        "approval_status": "SYNTHETIC DEMONSTRATION ONLY",
        "text": "",
    }]

    with patch("llm_service.ollama.Client") as client_class:
        client_class.return_value.chat.return_value = fake_response

        result = _generate_analysis(
            ALARM,
            ASSET,
            [],
            evidence,
        )

    assert "cannot be determined" in result["possible_explanations"]
    assert "Confirm the alarm timestamp" in result["recommended_checks"]
    assert "Unverified action" not in result["recommended_checks"]


def test_analysis_handles_model_response_with_invalid_json():
    from llm_service import _generate_analysis

    fake_response = MagicMock()
    fake_response.message.content = "not JSON"

    with patch("llm_service.ollama.Client") as client_class:
        client_class.return_value.chat.return_value = fake_response

        with pytest.raises(ValueError):
            _generate_analysis(
                ALARM,
                ASSET,
                [],
                [],
            )


def test_report_deduplicates_related_alarms():
    with patch(
        "llm_service._generate_analysis",
        return_value={
            "possible_explanations": "Cause not confirmed.",
            "recommended_checks": "Review available evidence.",
        },
    ):
        report = generate_investigation_report(
            alarm_data=ALARM,
            asset_data=ASSET,
            related_alarms=[
                {"alarm_id": "ALM-006", "alarm_name": "Duplicate current alarm"},
                {"alarm_id": "ALM-008", "alarm_name": "High pressure"},
                {"alarm_id": "ALM-008", "alarm_name": "Duplicate pressure"},
            ],
            procedure_evidence=[],
        )

    assert "Duplicate current alarm" not in report
    assert "High pressure" in report
    assert "Duplicate pressure" not in report

import pytest

from agents.financial_copilot import tools
from agents.grant_monitoring import (
    SYNTHETIC_GRANTS,
    create_review_case,
    forecast_grant_spending,
    generate_financial_review_report,
    monitor_grant_budget,
    monitor_grant_deadlines,
    transition_review_case,
)


def test_budget_monitoring_is_deterministic_and_thresholded():
    result = monitor_grant_budget("GRANT-A", "2026-11-03", warning_threshold=0.5)

    assert result["remaining_balance"] == 4800.0
    assert result["utilization_rate"] == 0.52
    assert result["status"] == "warning"
    assert result["calculation_inputs"]["spending_to_date"] == 5200.0


def test_forecast_uses_historical_average_and_projects_exhaustion():
    result = forecast_grant_spending("GRANT-A", "2026-11-03")

    assert result["average_monthly_spending"] == 1050.0
    assert result["months_to_projected_exhaustion"] == 5
    assert result["projected_exhaustion_date"] == "2027-04-03"
    assert result["funding_end_date"] == "2026-12-31"
    assert result["funding_end_comparison"] == "baseline_exhaustion_after_funding_end"
    assert result["projected_unspent_balance_at_funding_end"] == 2700.0
    assert result["risk_indicators"] == ["potential_unspent_funds_at_funding_end"]
    assert result["accelerated_spending_risk"]["status"] == "not_assessed"
    assert result["calculation_inputs"]["history_month_count"] == 4


def test_deadline_monitoring_identifies_overdue_and_upcoming_items():
    overdue = monitor_grant_deadlines("GRANT-B", "2026-11-03")
    upcoming = monitor_grant_deadlines("GRANT-A", "2026-11-03")

    assert {item["status"] for item in overdue["deadlines"]} == {"overdue"}
    assert {item["status"] for item in upcoming["risks"]} == {"upcoming"}


def test_review_case_transitions_preserve_notes_and_history():
    case = create_review_case("FR-TEST", "GRANT-A")
    reviewed = transition_review_case(case, "reviewed", "reviewer-1", "Checked receipts", "2026-11-04")
    resolved = transition_review_case(reviewed, "resolved", "reviewer-1", "Resolved with documentation", "2026-11-05")

    assert case["status"] == "pending"
    assert resolved["status"] == "resolved"
    assert [item["status"] for item in resolved["review_history"]] == ["pending", "reviewed", "resolved"]
    assert len(resolved["reviewer_notes"]) == 2
    with pytest.raises(ValueError):
        transition_review_case(case, "resolved", "reviewer-1", "Skipped review", "2026-11-04")


def test_report_combines_sources_and_registers_stage_d_tools():
    report = generate_financial_review_report(
        "data/sample_transactions.csv", "GRANT-A", "2026-11-03", "GRANT-A"
    )

    assert report["report_id"].startswith("FR-")
    assert report["source_transaction_ids"] == ["TX002"]
    assert report["financial_anomalies"]["records_checked"] == 2
    assert report["policy_references"]
    assert report["policy_query_source"] == "derived_from_transaction_categories"
    assert "GRANT-A" not in report["policy_query_used"]
    assert report["budget_indicators"]["grant_id"] == "GRANT-A"
    assert report["spending_forecast"]["calculation_inputs"]
    assert report["deadline_risks"]["deadlines"]
    assert report["review_case"]["status"] == "pending"
    assert monitor_grant_budget in tools
    assert forecast_grant_spending in tools
    assert monitor_grant_deadlines in tools
    assert generate_financial_review_report in tools
    assert create_review_case in tools
    assert transition_review_case in tools


def test_report_grant_only_request_uses_default_csv_and_filters_transactions():
    report = generate_financial_review_report(grant_id="GRANT-A", as_of_date="2026-11-03")

    assert report["financial_anomalies"]["records_checked"] == 2
    assert {flag["grant_id"] for flag in report["financial_anomalies"]["flags"]} == {"GRANT-A"}
    assert report["transaction_csv_path"].endswith("data/sample_transactions.csv")


def test_report_preserves_missing_csv_error_without_uncaught_file_error():
    report = generate_financial_review_report(
        "grants/GRANT-A.csv", "GRANT-A", "2026-11-03"
    )

    assert report["financial_anomalies"]["error"]["code"] == "missing_transaction_file"
    assert report["source_transaction_ids"] == []


def test_synthetic_grant_catalog_contains_required_fields():
    assert SYNTHETIC_GRANTS
    for grant in SYNTHETIC_GRANTS:
        assert {"grant_id", "approved_budget", "spending_to_date", "funding_start_date", "funding_end_date", "reporting_deadlines"} <= grant.keys()

"""Deterministic budget, deadline, reporting, and human-review helpers.

All records in this module are synthetic. Calculations use explicit ``as_of_date``
values so reports are reproducible and never depend on wall-clock time.
"""

import calendar
import hashlib
import json
import math
import re
from copy import deepcopy
from datetime import date, timedelta
from typing import Any

from agents.financial_tools import DEFAULT_TRANSACTION_CSV, review_transactions
from agents.grant_policies import search_grant_policies

SYNTHETIC_GRANTS: tuple[dict[str, Any], ...] = (
    {
        "grant_id": "GRANT-A",
        "approved_budget": 10000.0,
        "spending_to_date": 5200.0,
        "funding_start_date": "2026-01-01",
        "funding_end_date": "2026-12-31",
        "reporting_deadlines": [
            {"deadline_id": "GRANT-A-INTERIM", "label": "Interim financial report", "date": "2026-11-15"}
        ],
        "monthly_spending": [
            {"month": "2026-07", "amount": 900.0},
            {"month": "2026-08", "amount": 1100.0},
            {"month": "2026-09", "amount": 1000.0},
            {"month": "2026-10", "amount": 1200.0},
        ],
    },
    {
        "grant_id": "GRANT-B",
        "approved_budget": 20000.0,
        "spending_to_date": 18000.0,
        "funding_start_date": "2026-02-01",
        "funding_end_date": "2026-10-31",
        "reporting_deadlines": [
            {"deadline_id": "GRANT-B-FINAL", "label": "Final financial report", "date": "2026-10-15"}
        ],
        "monthly_spending": [
            {"month": "2026-07", "amount": 3500.0},
            {"month": "2026-08", "amount": 4000.0},
            {"month": "2026-09", "amount": 4500.0},
            {"month": "2026-10", "amount": 5000.0},
        ],
    },
)


def _grant(grant_id: str) -> dict[str, Any]:
    for grant in SYNTHETIC_GRANTS:
        if grant["grant_id"] == grant_id:
            return deepcopy(grant)
    raise ValueError(f"Unknown synthetic grant: {grant_id}")


def _date(value: str) -> date:
    return date.fromisoformat(value)


def _add_months(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 + months
    year, month_index = divmod(month_index, 12)
    month = month_index + 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


def monitor_grant_budget(
    grant_id: str,
    as_of_date: str,
    warning_threshold: float = 0.8,
    critical_threshold: float = 1.0,
) -> dict[str, Any]:
    """Return deterministic budget balances and utilization indicators."""
    if not 0 <= warning_threshold <= critical_threshold:
        raise ValueError("warning_threshold must be between 0 and critical_threshold")
    grant = _grant(grant_id)
    approved = float(grant["approved_budget"])
    spent = float(grant["spending_to_date"])
    remaining = approved - spent
    utilization = spent / approved if approved else math.inf
    status = "critical" if utilization >= critical_threshold else "warning" if utilization >= warning_threshold else "on_track"
    return {
        "grant_id": grant_id,
        "as_of_date": as_of_date,
        "approved_budget": approved,
        "spending_to_date": spent,
        "remaining_balance": remaining,
        "utilization_rate": utilization,
        "warning_threshold": warning_threshold,
        "critical_threshold": critical_threshold,
        "status": status,
        "calculation_inputs": {
            "approved_budget": approved,
            "spending_to_date": spent,
            "thresholds": {"warning": warning_threshold, "critical": critical_threshold},
        },
    }


def forecast_grant_spending(grant_id: str, as_of_date: str) -> dict[str, Any]:
    """Forecast exhaustion from the mean of the supplied synthetic monthly history."""
    grant = _grant(grant_id)
    budget = monitor_grant_budget(grant_id, as_of_date)
    history = grant["monthly_spending"]
    funding_end_date = grant["funding_end_date"]
    total_history = sum(float(item["amount"]) for item in history)
    average_monthly = total_history / len(history) if history else 0.0
    remaining = budget["remaining_balance"]
    if remaining <= 0:
        months_to_exhaustion = 0
        exhaustion_date = as_of_date
    elif average_monthly <= 0:
        months_to_exhaustion = None
        exhaustion_date = None
    else:
        months_to_exhaustion = math.ceil(remaining / average_monthly)
        exhaustion_date = _add_months(_date(as_of_date), months_to_exhaustion).isoformat()
    funding_end = _date(funding_end_date)
    reference = _date(as_of_date)
    months_through_funding_end = max(
        0,
        (funding_end.year - reference.year) * 12 + funding_end.month - reference.month + 1,
    )
    projected_spend_through_funding_end = min(
        max(0.0, remaining), average_monthly * months_through_funding_end
    )
    projected_unspent_balance = max(0.0, remaining - projected_spend_through_funding_end)
    if exhaustion_date is None:
        comparison = "no_baseline_exhaustion_date"
    elif _date(exhaustion_date) > funding_end:
        comparison = "baseline_exhaustion_after_funding_end"
    else:
        comparison = "baseline_exhaustion_by_funding_end"
    return {
        "grant_id": grant_id,
        "as_of_date": as_of_date,
        "average_monthly_spending": average_monthly,
        "months_to_projected_exhaustion": months_to_exhaustion,
        "projected_exhaustion_date": exhaustion_date,
        "funding_end_date": funding_end_date,
        "funding_end_comparison": comparison,
        "projected_spend_through_funding_end": projected_spend_through_funding_end,
        "projected_unspent_balance_at_funding_end": projected_unspent_balance,
        "risk_indicators": (
            ["potential_unspent_funds_at_funding_end"]
            if comparison == "baseline_exhaustion_after_funding_end" and projected_unspent_balance > 0
            else []
        ),
        "accelerated_spending_risk": {
            "status": "not_assessed",
            "explanation": "No accelerated-spending scenario was supplied; the baseline forecast is not an overspending prediction.",
        },
        "assumptions": [
            "The forecast uses the arithmetic mean of the supplied monthly spending history.",
            "Future monthly spending is assumed to equal that historical average.",
            "Funding-end projections count the remaining calendar months inclusively.",
            "The forecast is not a commitment, award modification, or compliance conclusion.",
        ],
        "calculation_inputs": {
            "remaining_balance": remaining,
            "monthly_spending_history": history,
            "history_month_count": len(history),
        },
    }


def monitor_grant_deadlines(
    grant_id: str,
    as_of_date: str,
    upcoming_days: int = 30,
) -> dict[str, Any]:
    """Classify funding and reporting deadlines as overdue, upcoming, or not due."""
    if upcoming_days < 0:
        raise ValueError("upcoming_days must not be negative")
    grant = _grant(grant_id)
    reference = _date(as_of_date)
    horizon = reference + timedelta(days=upcoming_days)
    deadlines = [
        {"deadline_id": f"{grant_id}-FUNDING-END", "label": "Funding end date", "date": grant["funding_end_date"], "type": "funding"},
        *[{**item, "type": "reporting"} for item in grant["reporting_deadlines"]],
    ]
    monitored = []
    for item in deadlines:
        due = _date(item["date"])
        days_until = (due - reference).days
        status = "overdue" if due < reference else "due_today" if due == reference else "upcoming" if due <= horizon else "not_due"
        monitored.append({**item, "days_until": days_until, "status": status})
    return {
        "grant_id": grant_id,
        "as_of_date": as_of_date,
        "upcoming_window_days": upcoming_days,
        "deadlines": monitored,
        "risks": [item for item in monitored if item["status"] in {"overdue", "upcoming", "due_today"}],
    }


def _report_id(grant_id: str, as_of_date: str, transaction_ids: list[str]) -> str:
    payload = json.dumps([grant_id, as_of_date, transaction_ids], separators=(",", ":"))
    return f"FR-{hashlib.sha256(payload.encode()).hexdigest()[:12].upper()}"


def create_review_case(report_id: str, subject_id: str) -> dict[str, Any]:
    """Create a pending human-review case with an auditable initial history entry."""
    return {
        "case_id": f"CASE-{report_id}",
        "report_id": report_id,
        "subject_id": subject_id,
        "status": "pending",
        "reviewer_notes": [],
        "review_history": [{"status": "pending", "reviewer": "system", "note": "Case created", "timestamp": None}],
    }


def transition_review_case(
    case: dict[str, Any],
    status: str,
    reviewer: str,
    note: str,
    timestamp: str,
) -> dict[str, Any]:
    """Advance a review case through pending → reviewed → resolved."""
    allowed = {"pending", "reviewed", "resolved"}
    if status not in allowed:
        raise ValueError(f"Unsupported review status: {status}")
    if not reviewer.strip() or not note.strip():
        raise ValueError("reviewer and note are required")
    current = case.get("status")
    transitions = {
        "pending": {"pending", "reviewed"},
        "reviewed": {"reviewed", "resolved"},
        "resolved": {"resolved"},
    }
    if current not in transitions or status not in transitions[current]:
        raise ValueError(f"Invalid review transition: {current} -> {status}")
    updated = deepcopy(case)
    updated["status"] = status
    updated.setdefault("reviewer_notes", []).append({"reviewer": reviewer, "note": note, "timestamp": timestamp})
    updated.setdefault("review_history", []).append({"status": status, "reviewer": reviewer, "note": note, "timestamp": timestamp})
    return updated


def generate_financial_review_report(
    csv_path: str | None = None,
    grant_id: str = "",
    as_of_date: str = "2026-11-03",
    policy_query: str = "",
    review_case: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Combine evidence without conflating a grant ID with a CSV path.

    ``csv_path`` is optional and defaults to the synthetic repository dataset;
    it is never constructed from ``grant_id``.
    """
    resolved_csv_path = csv_path or DEFAULT_TRANSACTION_CSV
    financial = review_transactions(resolved_csv_path, grant_id=grant_id or None)
    transaction_ids = [flag["transaction_id"] for flag in financial.get("flags", [])]
    report_id = _report_id(grant_id, as_of_date, transaction_ids)
    cleaned_query = re.sub(rf"\b{re.escape(grant_id)}\b", " ", policy_query, flags=re.IGNORECASE)
    cleaned_query = " ".join(cleaned_query.split())
    if cleaned_query:
        policy_query_used = cleaned_query
        policy_query_source = "user_query_without_grant_identifier"
    else:
        categories = " ".join(financial.get("categories_reviewed", []))
        policy_query_used = f"{categories} allowable cost documentation budget".strip()
        policy_query_source = "derived_from_transaction_categories"
    policy = search_grant_policies(policy_query_used)
    case = deepcopy(review_case) if review_case else create_review_case(report_id, grant_id)
    return {
        "report_id": report_id,
        "grant_id": grant_id,
        "as_of_date": as_of_date,
        "financial_anomalies": financial,
        "transaction_csv_path": resolved_csv_path,
        "budget_indicators": monitor_grant_budget(grant_id, as_of_date),
        "spending_forecast": forecast_grant_spending(grant_id, as_of_date),
        "deadline_risks": monitor_grant_deadlines(grant_id, as_of_date),
        "policy_evidence": policy,
        "policy_query_input": policy_query,
        "policy_query_used": policy_query_used,
        "policy_query_source": policy_query_source,
        "source_transaction_ids": transaction_ids,
        "policy_references": [
            {"section": item["section"], "source_url": item["source_url"]}
            for item in policy["matches"]
        ],
        "review_case": case,
        "disclaimer": (
            "Financial anomalies and deadline risks are indicators for human review. "
            "Policy evidence does not establish a compliance violation."
        ),
    }

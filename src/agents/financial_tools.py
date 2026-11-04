"""Deterministic, explainable transaction screening for synthetic data.

The screening rules are intentionally conservative indicators for human review,
not fraud or compliance determinations.
"""

import csv
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from statistics import median
from typing import Any

REQUIRED = ("transaction_id", "grant_id", "date", "category", "amount", "budget_limit")
DEFAULT_TRANSACTION_CSV = str(Path(__file__).resolve().parents[2] / "data" / "sample_transactions.csv")

DEFAULT_SCREENING_RULES: dict[str, float] = {
    "duplicate_score": 20.0,
    "missing_field_score": 10.0,
    "invalid_date_score": 15.0,
    "invalid_number_score": 20.0,
    "negative_amount_score": 20.0,
    "negative_budget_score": 20.0,
    "over_budget_score": 25.0,
    "budget_warning_score": 5.0,
    "unusual_amount_score": 15.0,
    "budget_warning_ratio": 0.9,
    "unusual_amount_multiplier": 3.0,
    "unusual_amount_minimum": 1000.0,
}


def _rules(config: dict[str, float] | None) -> dict[str, float]:
    rules = DEFAULT_SCREENING_RULES.copy()
    if config:
        for name, value in config.items():
            if name in rules:
                numeric_value = float(value)
                if numeric_value < 0:
                    raise ValueError(f"Screening rule '{name}' must not be negative")
                rules[name] = numeric_value
    if rules["unusual_amount_multiplier"] <= 1:
        raise ValueError("unusual_amount_multiplier must be greater than 1")
    if rules["budget_warning_ratio"] > 1:
        raise ValueError("budget_warning_ratio must not exceed 1")
    return rules


def _risk_level(score: int) -> str:
    if score >= 50:
        return "high"
    if score >= 25:
        return "medium"
    if score:
        return "low"
    return "none"


def _add_indicator(
    indicators: list[dict[str, Any]],
    issues: list[str],
    code: str,
    explanation: str,
    score: float,
) -> None:
    indicators.append({"code": code, "score": int(score), "explanation": explanation})
    issues.append(explanation)


def review_transactions(
    csv_path: str | None = DEFAULT_TRANSACTION_CSV,
    rules: dict[str, float] | None = None,
    grant_id: str | None = None,
) -> dict[str, Any]:
    """Screen CSV transactions and return explainable risk indicators.

    ``csv_path`` is an optional transaction-data file path, not a grant ID. If
    omitted, the repository's synthetic sample dataset is used. The grant is
    selected independently with ``grant_id``.
    ``rules`` may override numeric keys in ``DEFAULT_SCREENING_RULES``. Unknown
    keys are ignored so callers can carry broader configuration safely. When
    ``grant_id`` is supplied, only records for that grant are screened.
    """
    screening_rules = _rules(rules)
    path = Path(csv_path or DEFAULT_TRANSACTION_CSV)
    if not path.is_file():
        return {
            "records_checked": 0,
            "flagged_records": 0,
            "flags": [],
            "grant_id_filter": grant_id,
            "categories_reviewed": [],
            "rules": screening_rules,
            "error": {
                "code": "missing_transaction_file",
                "message": f"Transaction CSV file does not exist: {path}",
                "csv_path": str(path),
            },
            "disclaimer": "Screening only; not a compliance determination.",
        }
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing_columns = [name for name in REQUIRED if name not in (reader.fieldnames or [])]
        if missing_columns:
            raise ValueError(f"Missing required columns: {missing_columns}")
        records = list(reader)

    selected_records = [
        (row_number, row)
        for row_number, row in enumerate(records, start=2)
        if grant_id is None or (row.get("grant_id") or "").strip() == grant_id
    ]
    ids = Counter((row.get("transaction_id") or "").strip() for _, row in selected_records)
    amounts_by_category: defaultdict[str, list[float]] = defaultdict(list)
    categories = set()
    for _, row in selected_records:
        category = (row.get("category") or "").strip()
        if category:
            categories.add(category)
        try:
            amount = float(row.get("amount", ""))
        except (TypeError, ValueError):
            continue
        if category and amount >= 0:
            amounts_by_category[category].append(amount)

    flags = []
    for row_number, row in selected_records:
        transaction_id = (row.get("transaction_id") or "").strip() or f"row-{row_number}"
        grant_id = (row.get("grant_id") or "").strip()
        category = (row.get("category") or "").strip()
        issues: list[str] = []
        indicators: list[dict[str, Any]] = []

        def add(code: str, explanation: str, rule_name: str) -> None:
            _add_indicator(indicators, issues, code, explanation, screening_rules[rule_name])

        if not (row.get("transaction_id") or "").strip():
            add("missing_transaction_id", "missing transaction ID", "missing_field_score")
        transaction_value = (row.get("transaction_id") or "").strip()
        if ids.get(transaction_value, 0) > 1 and transaction_value:
            add("duplicate_transaction_id", "duplicate transaction ID", "duplicate_score")
        for key in ("grant_id", "date", "category"):
            if not (row.get(key) or "").strip():
                add(f"missing_{key}", f"missing {key}", "missing_field_score")

        raw_date = (row.get("date") or "").strip()
        if raw_date:
            try:
                date.fromisoformat(raw_date)
            except ValueError:
                add("invalid_date", "invalid date; expected YYYY-MM-DD", "invalid_date_score")

        try:
            amount = float(row.get("amount", ""))
            amount_valid = True
        except (TypeError, ValueError):
            amount = None
            amount_valid = False
        try:
            budget_limit = float(row.get("budget_limit", ""))
            budget_valid = True
        except (TypeError, ValueError):
            budget_limit = None
            budget_valid = False

        if not amount_valid or not budget_valid:
            add("invalid_number", "invalid amount or budget limit", "invalid_number_score")
        if amount_valid and amount is not None and amount < 0:
            add("negative_amount", "negative amount; verify whether credit/refund", "negative_amount_score")
        if budget_valid and budget_limit is not None and budget_limit < 0:
            add("negative_budget_limit", "negative budget limit", "negative_budget_score")
        if (
            amount_valid
            and budget_valid
            and amount is not None
            and budget_limit is not None
            and amount >= 0
            and budget_limit >= 0
        ):
            if amount > budget_limit:
                add(
                    "over_budget",
                    "transaction amount exceeds supplied budget limit",
                    "over_budget_score",
                )
            elif budget_limit and amount / budget_limit >= screening_rules["budget_warning_ratio"]:
                add(
                    "near_budget_limit",
                    f"transaction uses at least {screening_rules['budget_warning_ratio']:.0%} of its budget limit",
                    "budget_warning_score",
                )

            peer_amounts = amounts_by_category.get(category, [])
            if (
                amount >= screening_rules["unusual_amount_minimum"]
                and len(peer_amounts) >= 3
                and amount > median(peer_amounts) * screening_rules["unusual_amount_multiplier"]
            ):
                add(
                    "unusual_amount",
                    f"amount is unusually high for category '{category}' compared with its median",
                    "unusual_amount_score",
                )

        score = min(100, sum(indicator["score"] for indicator in indicators))
        if indicators:
            flags.append(
                {
                    "row": row_number,
                    "transaction_id": transaction_id,
                    "grant_id": grant_id,
                    "risk_score": score,
                    "risk_level": _risk_level(score),
                    "issues": issues,
                    "indicators": indicators,
                }
            )

    return {
        "records_checked": len(selected_records),
        "flagged_records": len(flags),
        "flags": flags,
        "grant_id_filter": grant_id,
        "categories_reviewed": sorted(categories),
        "rules": screening_rules,
        "disclaimer": "Screening only; not a compliance determination.",
    }


if __name__ == "__main__":
    import json

    print(json.dumps(review_transactions(), indent=2))

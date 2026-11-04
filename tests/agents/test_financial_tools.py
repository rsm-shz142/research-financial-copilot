import csv

from agents.financial_tools import DEFAULT_TRANSACTION_CSV, review_transactions


def test_grant_only_request_uses_synthetic_default_and_filters_other_grants():
    result = review_transactions(grant_id="GRANT-A")

    assert DEFAULT_TRANSACTION_CSV.endswith("data/sample_transactions.csv")
    assert result["records_checked"] == 2
    assert {flag["grant_id"] for flag in result["flags"]} == {"GRANT-A"}


def test_missing_transaction_path_returns_structured_error():
    result = review_transactions("grants/GRANT-A.csv", grant_id="GRANT-A")

    assert result["error"]["code"] == "missing_transaction_file"
    assert result["error"]["csv_path"] == "grants/GRANT-A.csv"
    assert result["flags"] == []


def test_review_transactions_returns_explainable_risk_indicators():
    result = review_transactions("data/sample_transactions.csv")

    assert result["records_checked"] == 5
    assert result["flagged_records"] == 4
    assert [flag["transaction_id"] for flag in result["flags"]] == [
        "TX002",
        "TX003",
        "TX003",
        "TX005",
    ]
    assert result["flags"][0]["risk_score"] == 25
    assert result["flags"][0]["risk_level"] == "medium"
    assert result["flags"][0]["indicators"][0]["code"] == "over_budget"


def test_review_transactions_supports_configurable_rules(tmp_path):
    path = tmp_path / "transactions.csv"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "transaction_id",
                "grant_id",
                "date",
                "category",
                "amount",
                "budget_limit",
            ],
        )
        writer.writeheader()
        writer.writerows(
            [
                {"transaction_id": "A", "grant_id": "G", "date": "2026-01-01", "category": "Travel", "amount": "100", "budget_limit": "1000"},
                {"transaction_id": "B", "grant_id": "G", "date": "2026-01-02", "category": "Travel", "amount": "950", "budget_limit": "1000"},
                {"transaction_id": "C", "grant_id": "G", "date": "2026-01-03", "category": "Travel", "amount": "5000", "budget_limit": "6000"},
            ]
        )

    result = review_transactions(
        str(path),
        {"budget_warning_ratio": 0.8, "unusual_amount_multiplier": 2.0},
    )

    by_id = {flag["transaction_id"]: flag for flag in result["flags"]}
    assert "near_budget_limit" in {item["code"] for item in by_id["B"]["indicators"]}
    assert "unusual_amount" in {item["code"] for item in by_id["C"]["indicators"]}
    assert any("unusually high" in item["explanation"] for item in by_id["C"]["indicators"])


def test_review_transactions_filters_to_requested_grant():
    result = review_transactions("data/sample_transactions.csv", grant_id="GRANT-A")

    assert result["grant_id_filter"] == "GRANT-A"
    assert result["records_checked"] == 2
    assert {flag["grant_id"] for flag in result["flags"]} == {"GRANT-A"}
    assert [flag["transaction_id"] for flag in result["flags"]] == ["TX002"]

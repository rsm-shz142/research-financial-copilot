from agents.financial_copilot import tools
from agents.grant_policies import (
    POLICY_KNOWLEDGE_BASE,
    screen_grant_transactions,
    search_grant_policies,
    verify_policy_claim,
)


def test_policy_search_preserves_authoritative_citations():
    result = search_grant_policies("travel costs require written policy and documentation")

    assert result["matches"]
    match = result["matches"][0]
    assert match["section"] == "2 CFR 200.475"
    assert match["source_url"].startswith("https://www.ecfr.gov/")
    assert match["evidence_status"] == "source-grounded"
    assert result["verification"]["status"] in {"supported", "ambiguous_match"}


def test_grant_identifier_is_not_treated_as_policy_evidence():
    result = search_grant_policies("GRANT-A")

    assert result["matches"] == []
    assert result["verification"]["status"] == "missing_evidence"


def test_policy_validation_detects_missing_and_unsupported_evidence():
    missing = verify_policy_claim("This cost is allowable")
    unsupported = verify_policy_claim("The award permits an automatic 50 percent increase", ["2 CFR 200.403"])

    assert missing["status"] == "missing_evidence"
    assert not missing["supported"]
    assert unsupported["status"] == "unsupported_claim"
    assert not unsupported["supported"]


def test_policy_validation_marks_ambiguous_citations():
    result = verify_policy_claim(
        "The cost is reasonable and allocable",
        ["2 CFR 200.403", "2 CFR 200.405"],
    )

    assert result["status"] == "ambiguous_match"
    assert not result["supported"]


def test_screening_keeps_financial_anomalies_separate_from_policy_leads():
    result = screen_grant_transactions("data/sample_transactions.csv", "over budget allowable cost")

    assert result["financial_screening"]["flagged_records"] == 4
    assert result["policy_review"]["matches"]
    assert result["compliance_status"] == "potential_compliance_issue_research_required"
    assert "not compliance violations" in result["disclaimer"]
    assert search_grant_policies in tools
    assert screen_grant_transactions in tools


def test_screening_tool_applies_grant_filter():
    result = screen_grant_transactions(
        "data/sample_transactions.csv", "GRANT-A", grant_id="GRANT-A"
    )

    assert result["financial_screening"]["records_checked"] == 2
    assert [flag["transaction_id"] for flag in result["financial_screening"]["flags"]] == ["TX002"]


def test_screening_tool_defaults_csv_path_without_using_grant_id_as_path():
    result = screen_grant_transactions(grant_id="GRANT-A")

    assert result["financial_screening"]["records_checked"] == 2
    assert {flag["grant_id"] for flag in result["financial_screening"]["flags"]} == {"GRANT-A"}


def test_screening_tool_reports_missing_csv_path():
    result = screen_grant_transactions("grants/GRANT-A.csv", grant_id="GRANT-A")

    assert result["financial_screening"]["error"]["code"] == "missing_transaction_file"


def test_policy_corpus_has_verifiable_metadata():
    assert len(POLICY_KNOWLEDGE_BASE) >= 4
    assert all(policy["section"].startswith("2 CFR 200.") for policy in POLICY_KNOWLEDGE_BASE)
    assert all(policy["source_url"].startswith("https://www.ecfr.gov/") for policy in POLICY_KNOWLEDGE_BASE)

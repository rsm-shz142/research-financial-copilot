"""Local, source-grounded policy retrieval for synthetic grant transactions."""

import re
from collections.abc import Iterable
from typing import Any

POLICY_KNOWLEDGE_BASE: tuple[dict[str, Any], ...] = (
    {
        "policy_id": "2-cfr-200.403",
        "section": "2 CFR 200.403",
        "title": "Factors affecting allowability of costs",
        "source_name": "Electronic Code of Federal Regulations",
        "source_url": "https://www.ecfr.gov/current/title-2/subtitle-A/chapter-II/part-200/section-200.403",
        "authority": "U.S. federal regulation; eCFR authoritative but unofficial edition",
        "excerpt": (
            "Costs must be necessary and reasonable for the performance of the Federal award, "
            "allocable thereto, conform to applicable limitations, and be adequately documented."
        ),
        "keywords": ("allowable", "allowability", "necessary", "reasonable", "allocable", "documented", "budget"),
    },
    {
        "policy_id": "2-cfr-200.405",
        "section": "2 CFR 200.405",
        "title": "Allocable costs",
        "source_name": "Electronic Code of Federal Regulations",
        "source_url": "https://www.ecfr.gov/current/title-2/subtitle-A/chapter-II/part-200/section-200.405",
        "authority": "U.S. federal regulation; eCFR authoritative but unofficial edition",
        "excerpt": (
            "A cost is allocable if it is assignable to the Federal award in accordance with the "
            "relative benefits received; a cost allocable to one Federal award may not be charged "
            "to another to overcome fund deficiencies or avoid restrictions."
        ),
        "keywords": ("allocable", "allocation", "relative", "benefit", "charge", "award", "fund", "deficiency"),
    },
    {
        "policy_id": "2-cfr-200.430",
        "section": "2 CFR 200.430",
        "title": "Compensation—personal services",
        "source_name": "Electronic Code of Federal Regulations",
        "source_url": "https://www.ecfr.gov/current/title-2/subtitle-A/chapter-II/part-200/section-200.430",
        "authority": "U.S. federal regulation; eCFR authoritative but unofficial edition",
        "excerpt": (
            "Compensation costs are allowable to the extent they satisfy the requirements of this "
            "part, are reasonable, conform to established written policy applied consistently, "
            "and are supported as required."
        ),
        "keywords": ("compensation", "salary", "personal", "services", "employee", "reasonable", "written", "policy", "supported"),
    },
    {
        "policy_id": "2-cfr-200.453",
        "section": "2 CFR 200.453",
        "title": "Materials and supplies costs, including computing devices",
        "source_name": "Electronic Code of Federal Regulations",
        "source_url": "https://www.ecfr.gov/current/title-2/subtitle-A/chapter-II/part-200/section-200.453",
        "authority": "U.S. federal regulation; eCFR authoritative but unofficial edition",
        "excerpt": (
            "Materials, supplies, and fabricated parts necessary for performance of a Federal award "
            "are allowable; purchased materials and supplies must be charged at actual prices, net "
            "of applicable credits."
        ),
        "keywords": ("materials", "supplies", "equipment", "computing", "devices", "necessary", "actual", "prices"),
    },
    {
        "policy_id": "2-cfr-200.475",
        "section": "2 CFR 200.475",
        "title": "Travel costs",
        "source_name": "Electronic Code of Federal Regulations",
        "source_url": "https://www.ecfr.gov/current/title-2/subtitle-A/chapter-II/part-200/section-200.475",
        "authority": "U.S. federal regulation; eCFR authoritative but unofficial edition",
        "excerpt": (
            "Travel costs for official business may be charged on an actual-cost, per-diem, or "
            "mileage basis when applied consistently; directly charged travel must be justified as "
            "necessary and reasonable and consistent with written policy."
        ),
        "keywords": ("travel", "transportation", "lodging", "subsistence", "official", "business", "per diem", "mileage", "justified"),
    },
)

_STOP_WORDS = {
    "a", "an", "and", "are", "be", "by", "for", "from", "in", "is", "of", "on", "or", "the", "to", "with"
}


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", value.lower()) if token not in _STOP_WORDS}


def _citation(policy: dict[str, Any], matched_terms: Iterable[str], relevance: int) -> dict[str, Any]:
    return {
        "policy_id": policy["policy_id"],
        "section": policy["section"],
        "title": policy["title"],
        "source_name": policy["source_name"],
        "source_url": policy["source_url"],
        "authority": policy["authority"],
        "excerpt": policy["excerpt"],
        "matched_terms": sorted(matched_terms),
        "relevance": relevance,
        "evidence_status": "source-grounded",
    }


def search_grant_policies(query: str, max_results: int = 3) -> dict[str, Any]:
    """Search policy concepts, expenditure categories, or regulatory questions.

    Grant identifiers are not policy concepts and will not be treated as evidence.
    """
    if not query or not query.strip():
        return {
            "query": query,
            "matches": [],
            "verification": {
                "status": "missing_evidence",
                "missing_evidence": ["A non-empty policy query is required."],
                "unsupported_claims": [],
                "ambiguous_matches": [],
            },
        }

    query_tokens = _tokens(query)
    scored = []
    for policy in POLICY_KNOWLEDGE_BASE:
        keyword_tokens = _tokens(" ".join(policy["keywords"]))
        title_tokens = _tokens(policy["title"])
        matched = query_tokens & (keyword_tokens | title_tokens | _tokens(policy["excerpt"]))
        section_match = policy["section"].lower() in query.lower()
        relevance = len(matched) + (3 if section_match else 0)
        if relevance:
            scored.append((relevance, policy, matched))
    scored.sort(key=lambda item: (-item[0], item[1]["section"]))
    matches = [_citation(policy, matched, relevance) for relevance, policy, matched in scored[: max(1, max_results)]]
    top_score = scored[0][0] if scored else 0
    tied = [policy["section"] for relevance, policy, _ in scored if relevance == top_score]
    ambiguous = tied if len(tied) > 1 and top_score == scored[0][0] else []
    status = "supported" if matches and not ambiguous else "ambiguous_match" if matches else "missing_evidence"
    return {
        "query": query,
        "matches": matches,
        "verification": {
            "status": status,
            "missing_evidence": [] if matches else ["No indexed policy provision matched the query."],
            "unsupported_claims": [],
            "ambiguous_matches": ambiguous,
        },
        "disclaimer": "Policy matches are research leads, not legal advice or a compliance determination.",
    }


def verify_policy_claim(claim: str, cited_sections: list[str] | None = None) -> dict[str, Any]:
    """Check whether a claim has cited, locally indexed evidence without endorsing it."""
    if not claim or not claim.strip() or not cited_sections:
        return {
            "claim": claim,
            "status": "missing_evidence",
            "supported": False,
            "citations": [],
            "explanation": "A claim and at least one indexed policy section are required.",
        }

    policies = [policy for policy in POLICY_KNOWLEDGE_BASE if policy["section"] in cited_sections]
    if not policies:
        return {
            "claim": claim,
            "status": "unsupported_claim",
            "supported": False,
            "citations": [],
            "explanation": "The cited policy sections are not present in the local source corpus.",
        }

    claim_tokens = _tokens(claim)
    evidence = [_citation(policy, claim_tokens & _tokens(policy["excerpt"]), 0) for policy in policies]
    overlaps = [item for item in evidence if item["matched_terms"]]
    best_coverage = max(
        (len(item["matched_terms"]) / len(claim_tokens) for item in overlaps),
        default=0.0,
    )
    if not overlaps or best_coverage < 0.5:
        status = "unsupported_claim"
        supported = False
        explanation = "The cited excerpts do not contain sufficient lexical evidence for the claim."
    elif len(overlaps) > 1 and len({item["matched_terms"][0] for item in overlaps}) == 1:
        status = "ambiguous_match"
        supported = False
        explanation = "Multiple cited provisions overlap, so the claim requires narrower evidence."
    else:
        status = "evidence_found"
        supported = True
        explanation = "The cited excerpt contains terms related to the claim; human review is still required."
    return {
        "claim": claim,
        "status": status,
        "supported": supported,
        "citations": evidence,
        "explanation": explanation,
    }


def screen_grant_transactions(
    csv_path: str | None = None,
    policy_query: str = "",
    rules: dict[str, float] | None = None,
    grant_id: str | None = None,
) -> dict[str, Any]:
    """Combine screening and policy leads.

    ``csv_path`` is an optional transaction CSV path and is never derived from
    ``grant_id``. When omitted, the repository's synthetic sample dataset is
    used; ``grant_id`` independently filters its records.
    """
    from agents.financial_tools import review_transactions

    financial_screening = review_transactions(csv_path, rules, grant_id=grant_id)
    query = policy_query or "research grant allowable cost documentation budget"
    policy_review = search_grant_policies(query)
    return {
        "financial_screening": financial_screening,
        "policy_review": policy_review,
        "compliance_status": "potential_compliance_issue_research_required",
        "disclaimer": (
            "Financial anomalies are not compliance violations. Policy matches are potential "
            "issues for evidence review and are not definitive findings."
        ),
    }

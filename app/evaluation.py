from __future__ import annotations

import json
from pathlib import Path

from app.intelligence import CandidateOpportunity, has_capability_match, market_relevance_for_candidate


def load_evaluation_cases(path: str | Path) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def classify_evaluation_case(case: dict) -> dict:
    candidate = CandidateOpportunity(
        title=case.get("title", ""),
        buyer_name=case.get("buyer_name", ""),
        notice_identifier=case.get("notice_identifier", case.get("title", "")),
        summary=case.get("summary", ""),
        cpv_codes="; ".join(case.get("cpv_codes", [])) if isinstance(case.get("cpv_codes"), list) else str(case.get("cpv_codes", "")),
    )
    score, rationale = market_relevance_for_candidate(candidate)
    relevant = score >= 44 and has_capability_match(candidate)
    return {
        "title": candidate.title,
        "buyer_name": candidate.buyer_name,
        "score": score,
        "rationale": rationale,
        "relevant": relevant,
        "status": "matched" if relevant else "rejected",
    }


def evaluate_cases(cases: list[dict]) -> dict:
    false_positives = []
    false_negatives = []
    true_positive = 0
    true_negative = 0
    for case in cases:
        result = classify_evaluation_case(case)
        expected = bool(case.get("expected_relevant"))
        if result["relevant"] and expected:
            true_positive += 1
        elif result["relevant"] and not expected:
            false_positives.append({"case": case, "result": result})
        elif not result["relevant"] and expected:
            false_negatives.append({"case": case, "result": result})
        else:
            true_negative += 1
    precision = true_positive / (true_positive + len(false_positives)) if true_positive + len(false_positives) else 1
    recall = true_positive / (true_positive + len(false_negatives)) if true_positive + len(false_negatives) else 1
    return {
        "total": len(cases),
        "precision": precision,
        "recall": recall,
        "true_positive": true_positive,
        "true_negative": true_negative,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "buyer_mismatch_count": sum(1 for case in cases if case.get("expected_customer") and case.get("buyer_name") and case["expected_customer"].lower() not in case["buyer_name"].lower()),
    }

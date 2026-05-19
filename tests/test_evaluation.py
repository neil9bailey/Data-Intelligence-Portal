from app.evaluation import classify_evaluation_case, evaluate_cases, load_evaluation_cases


def test_evaluation_fixture_covers_required_quality_cases():
    cases = load_evaluation_cases("tests/fixtures/evaluation/opportunity_matching.json")
    notes = " ".join(case.get("notes", "").lower() for case in cases)

    assert "short alias" in notes
    assert "award notice" in notes
    assert "buyer mismatch" in notes
    assert "generic public-sector cyber" in notes
    assert any(case.get("expected_customer") == "National Highways" for case in cases)


def test_evaluation_case_expected_statuses_match_current_classifier():
    cases = load_evaluation_cases("tests/fixtures/evaluation/opportunity_matching.json")

    for case in cases:
        result = classify_evaluation_case(case)
        assert result["status"] == case["expected_status"], case["notes"]
        assert result["relevant"] is bool(case["expected_relevant"]), case["notes"]


def test_evaluation_report_includes_buyer_mismatch_metric():
    cases = load_evaluation_cases("tests/fixtures/evaluation/opportunity_matching.json")
    report = evaluate_cases(cases)

    assert report["precision"] >= 0.9
    assert report["recall"] >= 0.9
    assert report["buyer_mismatch_count"] >= 1

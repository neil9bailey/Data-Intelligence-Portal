# Matching Evaluation

The evaluation harness provides an offline quality check for opportunity matching rules. It does not call live procurement sources.

Run:

```powershell
python scripts/run-evaluation.py
```

Fixture cases live in:

```text
tests/fixtures/evaluation/opportunity_matching.json
```

Each case captures title, buyer, summary, CPV codes, expected relevance and notes. Cases can also include `notice_type`, `procurement_stage`, `expected_customer` and `expected_status`.

Keep the fixture set balanced across:

- true relevant public-sector technology opportunities
- irrelevant noisy opportunities
- award or closed notices that should not be promoted as current opportunities
- short-alias false positives, for example `HE`
- buyer/customer mismatch cases
- relevant opportunities that are not yet tied to a configured customer

Add new false-positive and false-negative examples whenever the matching rules change.

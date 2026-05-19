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

Each case captures title, buyer, summary, CPV codes, expected relevance and notes. Add new false-positive and false-negative examples whenever the matching rules change.

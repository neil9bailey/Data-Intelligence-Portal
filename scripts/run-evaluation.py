from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.evaluation import evaluate_cases, load_evaluation_cases  # noqa: E402


if __name__ == "__main__":
    fixture_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "tests" / "fixtures" / "evaluation" / "opportunity_matching.json"
    report = evaluate_cases(load_evaluation_cases(fixture_path))
    print(json.dumps(report, indent=2, default=str))

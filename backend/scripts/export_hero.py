"""Export one seeded gripper run for the offline dashboard."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings  # noqa: E402
from app.models.schemas import RunConfig  # noqa: E402
from app.orchestration.run import execute_run  # noqa: E402


def main() -> None:
    config = RunConfig(
        domain="gripper_2d",
        seed=42,
        budget={"total_simulator_calls": 1200, "adversarial_fraction": 0.2, "playback_ms": 0},
        scenarios={"train_count": 8, "holdout_count": 24},
        model_provider="mock",
    )
    report, candidates, failures = execute_run(config, Settings(enable_meta=False, model_api_key=""), "hero")
    bundle = {
        "report": report.model_dump(mode="json"),
        "candidates": [row.model_dump(mode="json") for row in candidates],
        "failures": [row.model_dump(mode="json") for row in failures],
    }
    encoded = json.dumps(bundle, indent=2)
    targets = [
        ROOT / "experiments" / "hero_run.json",
        ROOT / "frontend" / "public" / "demo" / "hero.json",
    ]
    for path in targets:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(encoded, encoding="utf-8")
        print(f"wrote {path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()

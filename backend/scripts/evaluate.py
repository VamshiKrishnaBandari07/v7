"""Holdout ablation across seeds. Writes the numbers the report is allowed to claim."""

from __future__ import annotations

import csv
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings  # noqa: E402
from app.models.schemas import RunConfig  # noqa: E402
from app.orchestration.run import execute_run  # noqa: E402

SEEDS = [42, 43, 44]
METHODS = ["random", "evolutionary", "adversarial"]


def main() -> None:
    settings = Settings(enable_meta=False, model_api_key="")
    records: list[dict[str, float | int | str]] = []
    for seed in SEEDS:
        config = RunConfig(
            domain="gripper_2d",
            seed=seed,
            budget={"total_simulator_calls": 900, "adversarial_fraction": 0.2, "playback_ms": 0},
            scenarios={"train_count": 8, "holdout_count": 24},
            model_provider="mock",
        )
        report, _, _ = execute_run(config, settings, f"eval-{seed}")
        for row in report.holdout:
            if not row.preregistered:
                continue
            records.append(
                {
                    "seed": seed,
                    "method": row.method,
                    "success_rate": row.success_rate,
                    "worst_margin_n": row.worst_margin_n,
                    "mean_margin_n": row.mean_margin_n,
                    "material_proxy": row.material_proxy,
                    "search_calls": report.search_budget_per_method[row.method],
                    "holdout_fingerprint": report.holdout_fingerprint,
                    "simulator_version": report.simulator_version,
                }
            )
        print(f"seed {seed} search_calls={report.total_search_calls} validation={report.validation_calls}")

    out = ROOT / "experiments" / "out"
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / "ablation.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    (out / "ablation.json").write_text(json.dumps(records, indent=2), encoding="utf-8")

    lines = [
        "# Holdout evaluation",
        "",
        "Pre-registered finalists only. Each method receives the same search-call budget.",
        "The finalist is the best design on the train-core slice. Holdout scores are computed after that choice.",
        "The adversarial arm is also seeded by the deterministic mock planner, so this is not a live Meta model result.",
        "",
        f"Simulator `{records[0]['simulator_version']}`. Seeds {SEEDS}. "
        "Budget 900 simulator calls split across the three methods. "
        "8 training scenarios per design, 24 holdout scenarios.",
        "",
        "| Method | Mean holdout success | Spread | Mean worst margin (N) | Mean material proxy |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    summary: dict[str, dict[str, float]] = {}
    for method in METHODS:
        subset = [row for row in records if row["method"] == method]
        success = [float(row["success_rate"]) for row in subset]
        margin = [float(row["worst_margin_n"]) for row in subset]
        material = [float(row["material_proxy"]) for row in subset]
        spread = statistics.pstdev(success) if len(success) > 1 else 0.0
        summary[method] = {
            "mean_success": statistics.fmean(success),
            "spread": spread,
            "mean_worst_margin": statistics.fmean(margin),
            "mean_material": statistics.fmean(material),
        }
        lines.append(
            f"| {method} | {summary[method]['mean_success']:.3f} | {spread:.3f} | "
            f"{summary[method]['mean_worst_margin']:.2f} | {summary[method]['mean_material']:.1f} |"
        )
    lines.extend(
        [
            "",
            "## What this does and does not show",
            "",
            "A higher holdout success rate is the claim that matters. Material and worst-case margin are trade-offs, not a second chance to pick the winner.",
            "Three seeds is a small sample. The spread column is the population standard deviation of holdout success, not a confidence interval.",
            "The holdout envelope is shifted, but it is still drawn from the same analytic surrogate, so this is not evidence about a physical gripper.",
            "If the adversarial arm does not lead on holdout success, that negative result stands. Adversarial search spends part of its budget on stress cases, so it evaluates fewer designs.",
            "",
            "Machine-readable copy: `experiments/out/ablation.csv`.",
            "",
        ]
    )
    text = "\n".join(lines)
    (ROOT / "docs" / "evaluation.md").write_text(text, encoding="utf-8")
    (out / "evaluation.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()

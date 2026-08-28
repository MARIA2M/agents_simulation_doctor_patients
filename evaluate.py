# evaluate.py
# ─────────────────────────────────────────────
# A batch's reports against patients/*.json, and nothing else (4.1, 4.7).
# Post-process: no server and no graph, so it runs over any arm's batch.
# ─────────────────────────────────────────────

from __future__ import annotations

import argparse
import dataclasses
import json
from pathlib import Path

from ahead_agent import corpus, report
from ahead_agent.causes import score_causes
from ahead_agent.config import load_config
from ahead_agent.evaluation import evaluate_batch


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score a batch's reports against the ground truth in patients/*.json"
    )
    parser.add_argument("batch", help="a run directory, e.g. runs/e4-1")
    parser.add_argument("--profile", default="local", help="run profile, for paths")
    parser.add_argument(
        "--causes",
        action="store_true",
        help="also score the causes. Needs a server, and costs ~3 calls per report",
    )
    return parser.parse_args()


# ── What it reads ────────────────────────────


# 4.1
def load_truth(patients_dir: Path) -> dict:
    """patient_id → belief_profile, from patients/*.json and nowhere else.
    Through corpus.load_corpus, so the BMQ arrives on the same 1-5 scale the
    reports are written on (0.6)."""
    return {patient_id: profile["belief_profile"]
            for patient_id, profile in corpus.load_corpus(patients_dir).items()}


def load_reports(batch: Path):
    """(patient_id, Report) per consultation, and the runs that had no report."""
    reports, unparsed = [], []

    for path in sorted(batch.glob("*/report.json")):
        payload = json.loads(path.read_text())
        patient_id = payload.get("patient_id") or path.parent.name

        # The stored document has the shape parse() reads, so the NA policy of
        # 4.4 is re-applied here rather than taken on trust.
        parsed = (
            report.parse(json.dumps(payload["report"]), patient_id)
            if payload.get("report")
            else None
        )

        if parsed is None:
            unparsed.append(path.parent.name)
        else:
            reports.append((patient_id, parsed))

    return reports, unparsed


# ── Causes, when asked for (4.3) ─────────────


def score_all_causes(config, reports, truth) -> list:
    """Open text, so they are matched by similarity and stay out of the MAE.

    The ground truth of one patient is classified again for every repeat. That
    is wasteful and left alone on purpose: caching it is a change to
    `score_causes`, not to this script.
    """
    results = []
    for patient_id, parsed in reports:
        believed = (truth[patient_id].get("b_ipq") or {}).get("causes")
        results.append((patient_id, score_causes(config, parsed.causes, believed)))
    return results


def causes_text(results: list) -> str:
    methods = sorted({score.method for _, score in results if score.method})
    lines = [
        "",
        f"{'causes coverage':22}{_cell(_mean(s.coverage_score for _, s in results)):>8}",
        f"{'mean similarity':22}{_cell(_mean(s.mean_similarity for _, s in results)):>8}",
        f"{'method':22}{', '.join(methods) or '-':>8}",
    ]
    # 4.3 — the old module switched metric silently, so a mixed batch is a finding
    if len(methods) > 1:
        lines.append("! two methods in one batch: the numbers are not comparable")
    return "\n".join(lines)


def _mean(values):
    present = [v for v in values if v is not None]
    return round(sum(present) / len(present), 3) if present else None


# ── What it prints ───────────────────────────


def report_text(batch_id: str, metrics, reports: int, patients: int, unparsed: list) -> str:
    lines = [
        f"{batch_id}: {reports} reports over {patients} patients",
        "",
        f"{'dimension':22}{'MAE':>8}{'bias':>8}{'cover':>9}{'r':>8}",
    ]
    for name, d in metrics.by_dimension.items():
        lines.append(
            f"{name:22}{_cell(d.mae):>8}{_cell(d.bias, sign=True):>8}"
            f"{f'{d.scored}/{d.scored + d.na}':>9}{_cell(d.between_patient_r):>8}"
        )

    lines += [
        "",
        f"{'overall MAE':22}{_cell(metrics.mae):>8}",
        f"{'coverage':22}{metrics.coverage_rate:>8.0%}",
    ]

    # 2.5 needs patients to discriminate between. On a single-patient batch the
    # correlation runs over that patient's repeats, and what moves it is which
    # dimensions happened to come back NA — so it flips sign between arms of the
    # same patient. The number is real arithmetic on the wrong thing (D12).
    if patients < 2:
        lines.append(f"{'between-patient r':22}{'-':>8}   ({patients} patient: nothing to "
                     f"discriminate between)")
    else:
        lines.append(f"{'between-patient r':22}{_cell(metrics.between_patient_r):>8}")
    if unparsed:
        lines += ["", f"! {len(unparsed)} without a usable report: {', '.join(unparsed)}"]
    return "\n".join(lines)


def _cell(value, sign: bool = False) -> str:
    if value is None:
        return "-"
    return f"{value:+.2f}" if sign else f"{value:.2f}"


# ── What it leaves behind ────────────────────


def write_evaluation(
    batch: Path, batch_id: str, metrics, reports, unparsed: list, causes=None
) -> Path:
    payload = {
        "batch": batch_id,
        "reports": len(reports),
        "patients": len({pid for pid, _ in reports}),
        "unparsed": unparsed,
        "ground_truth_source": "patients/*.json",
        "overall": {
            "mae": metrics.mae,
            "coverage_rate": metrics.coverage_rate,
            "between_patient_r": metrics.between_patient_r,
        },
        # the properties are not dataclass fields, so they are added by hand
        "by_dimension": {
            name: {**dataclasses.asdict(d), "coverage_rate": d.coverage_rate}
            for name, d in metrics.by_dimension.items()
        },
        "by_report": [
            {**dataclasses.asdict(p), "coverage_rate": p.coverage_rate}
            for p in metrics.patients
        ],
    }

    if causes is not None:
        payload["causes"] = {
            "coverage_score": _mean(s.coverage_score for _, s in causes),
            "mean_similarity": _mean(s.mean_similarity for _, s in causes),
            "methods": sorted({s.method for _, s in causes if s.method}),
            "by_report": [
                {"patient_id": patient_id, **dataclasses.asdict(score)}
                for patient_id, score in causes
            ],
        }

    path = batch / "evaluation.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return path


def main() -> None:
    args = parse_args()
    config = load_config(args.profile)
    batch = Path(args.batch)

    truth = load_truth(config["paths"]["patients"])
    reports, unparsed = load_reports(batch)
    if not reports:
        raise SystemExit(f"{batch}: no usable report.json found")

    missing = sorted({pid for pid, _ in reports if pid not in truth})
    if missing:
        raise SystemExit(f"no ground truth for: {', '.join(missing)}")

    metrics = evaluate_batch([(parsed, truth[pid]) for pid, parsed in reports])

    print(report_text(batch.name, metrics, len(reports),
                      len({pid for pid, _ in reports}), unparsed))

    causes = None
    if args.causes:
        print(f"\nscoring causes over {len(reports)} reports — this calls the model…")
        causes = score_all_causes(config, reports, truth)
        print(causes_text(causes))

    print("\nwritten:",
          write_evaluation(batch, batch.name, metrics, reports, unparsed, causes))


if __name__ == "__main__":
    main()

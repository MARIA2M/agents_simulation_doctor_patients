#!/usr/bin/env python3
# fidel.py
# ─────────────────────────────────────────────
# 3.5 / F1 — did the patient play its profile? A quality-control screen over a
# batch, run before the scores are read.
#
#   python fidel.py runs/demos_patient_CLL-003_base
#   python fidel.py runs/demos_patient_CLL-003_base --profile hpc --quotes
#
# No server and no model: string and number comparison only. Unlike cover.py it
# **does** open patients/*.json, because the question is whether the transcript
# contradicts the profile.
#
# It does not touch a single clinical score. A run that fails here keeps its
# report; what changes is whether you should believe it.
#
# Named fidel.py for the reason cover.py is not coverage.py: the module is
# ahead_agent/fidelity.py and a second `fidelity` at the repo root would shadow
# nothing but confuse everyone.
# ─────────────────────────────────────────────

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ahead_agent import corpus, fidelity
from ahead_agent.config import load_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check each consultation's patient against its profile (3.5)"
    )
    parser.add_argument("batch", help="a run directory, e.g. runs/demos_patient_HIV-005_base")
    parser.add_argument("--profile", default="local", help="run profile, for paths")
    parser.add_argument("--quotes", action="store_true",
                        help="print the sentence behind every finding")
    return parser.parse_args()


# ── What it prints ───────────────────────────


def report_text(batch: fidelity.BatchFidelity, quotes: bool) -> str:
    runs = sorted(batch.runs, key=lambda r: (r.patient_id, r.repeat))

    lines = [
        f"{batch.batch_id}: {len(runs)} consultations checked against patients/*.json",
        "",
        f"{'run':24}{'verdict':>10}{'hard':>7}{'soft':>7}  findings",
    ]

    for run in runs:
        verdict = "PASS" if run.passed else "FAIL"
        summary = ", ".join(
            sorted({f"{f.kind}:{f.claim}" for f in run.findings})
        )[:52] or "—"
        lines.append(
            f"{run.run:24}{verdict:>10}{len(run.contradictions):>7}"
            f"{len(run.unsupported):>7}  {summary}"
        )

    lines += [
        "",
        f"{'fidelity rate':26}{_pct(batch.fidelity_rate)}"
        "   runs with no unsupported claim at all",
        f"{'contradiction-free rate':26}{_pct(batch.contradiction_free_rate)}"
        "   runs with no hard finding",
        "",
        "hard = the profile says otherwise (no-treatment regimen, wrong age).",
        "soft = named but unsupported; elaboration looks like this too, so read it.",
        "",
        "UPPER BOUND, not a score: this reads named entities, not meaning, so an",
        "invented narrative in unlisted words passes. Every miss is a false pass.",
    ]

    if quotes:
        lines += ["", "─" * 62]
        for run in runs:
            if not run.findings:
                continue
            lines.append(f"\n{run.run}")
            for finding in run.findings:
                lines.append(f"  [{finding.severity[:4]}] {finding.kind}: {finding.claim}"
                             f"  (turn {finding.turn})")
                lines.append(f'      "{finding.quote[:88]}"')

    return "\n".join(lines)


def _pct(value) -> str:
    return "     -" if value is None else f"{value:>6.0%}"


# ── What it leaves behind ────────────────────


def write_fidelity(batch_dir: Path, batch: fidelity.BatchFidelity) -> Path:
    payload = {
        "batch": batch.batch_id,
        "consultations": len(batch.runs),
        "reads_ground_truth": True,   # the opposite of coverage.json, on purpose
        "method": "deterministic string and number comparison, no model",
        "caveat": (
            "Precision-first screen over named entities. The rate is an upper "
            "bound on fidelity, never a measurement of it."
        ),
        "overall": {
            "fidelity_rate": batch.fidelity_rate,
            "contradiction_free_rate": batch.contradiction_free_rate,
        },
        "by_run": [
            {
                "run": run.run,
                "patient_id": run.patient_id,
                "repeat": run.repeat,
                "passed": run.passed,
                "contradictions": len(run.contradictions),
                "unsupported": len(run.unsupported),
                "findings": [f.as_dict() for f in run.findings],
            }
            for run in sorted(batch.runs, key=lambda r: (r.patient_id, r.repeat))
        ],
    }

    path = batch_dir / "fidelity.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return path


def main() -> None:
    args = parse_args()
    config = load_config(args.profile)
    batch_dir = Path(args.batch)

    checked = fidelity.read_batch(batch_dir, corpus.load_corpus(config["paths"]["patients"]))

    print(report_text(checked, args.quotes))
    print("\nwritten:", write_fidelity(batch_dir, checked))


if __name__ == "__main__":
    main()

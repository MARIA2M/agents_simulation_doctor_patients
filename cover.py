#!/usr/bin/env python3
# cover.py
# ─────────────────────────────────────────────
# A batch's coverage: what each report can point at in its own transcript, and
# how far the score moves across repeats (3.2, 2.4).
#
# Post-process, like evaluate.py: no server, no graph, no ground truth. It runs
# over any arm's batch, `coverage_hint: off` included.
#
#   python cover.py runs/e4-1
#
# Not named coverage.py on purpose: at the repo root that would shadow the
# installed `coverage` package and break pytest-cov. The module is
# ahead_agent/coverage.py, which does not.
# ─────────────────────────────────────────────

from __future__ import annotations

import argparse
import dataclasses
import json
from pathlib import Path

from ahead_agent import coverage
from ahead_agent.coverage import (
    CITED_UNSCORED,
    GROUNDED,
    SILENT,
    UNGROUNDED,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evidence integrity, ungrounded scores and spread over a batch"
    )
    parser.add_argument("batch", help="a run directory, e.g. runs/e4-1")
    parser.add_argument("--sample", metavar="N", type=int, default=0,
                        help="print N quotes that did not verify, and why")
    return parser.parse_args()


# ── What it prints ───────────────────────────

GLYPH = {GROUNDED: "●", UNGROUNDED: "○", CITED_UNSCORED: "◐", SILENT: "·"}


def report_text(batch: coverage.BatchCoverage) -> str:
    """The map: one row per dimension, one glyph per consultation, patients apart."""
    runs = sorted(batch.consultations, key=lambda c: (c.patient_id, c.repeat))
    patients = sorted({c.patient_id for c in runs})
    width = len(runs) + len(patients) + 2

    lines = [
        f"{batch.batch_id}: {len(runs)} consultations over {len(patients)} patients",
        "",
        f"{'dimension':22}{'map':{width}}{'ungr':>6}{'SD':>7}",
    ]

    for name in coverage.DIMENSIONS:
        lines.append(
            f"{name:22}{_map_row(name, runs, patients):{width}}"
            f"{_ungrounded(name, runs):>6}{_cell(_mean_sd(name, batch)):>7}"
        )

    lines += [
        "",
        "● grounded   ○ ungrounded   ◐ cited, unscored   · silent",
        "SD: the spread within one patient across repeats (2.4), averaged over",
        "    patients. Per patient it is in coverage.json, never collapsed there.",
        "",
        _consistency_text(batch),
        "",
        _quote_text(batch),
        "",
        f"{'ungrounded rate':22}{_cell(batch.ungrounded_rate)}"
        "   (of the scores emitted)",
    ]

    reuse = sum(len(c.turn_reuse) for c in runs)
    lines.append(
        # padded to the width _cell gives, so this line's parenthetical starts
        # where the one above it does
        f"{'reused turns':22}{reuse:<4}   ({reuse / len(runs):.1f} per consultation, "
        "cited by 2+ dimensions — V3 candidates)"
    )

    if batch.unparsed:
        lines += ["", f"! {len(batch.unparsed)} without a usable report: "
                      f"{', '.join(batch.unparsed)}"]
    return "\n".join(lines)


def _quote_text(batch: coverage.BatchCoverage) -> str:
    """The three checks apart. Which one fails is the whole diagnosis: quotes
    that are real but misplaced and quotes that were never said are opposite
    findings, and a single `verified` rate hides that."""
    checks = coverage.quote_checks(batch.consultations)
    if not checks:
        return f"{'quotes':22}none — no report cited anything"

    def rate(predicate) -> str:
        hits = sum(1 for check in checks if predicate(check))
        return f"{hits:>5}  {hits / len(checks):>4.0%}"

    return "\n".join([
        f"{'quotes':22}{len(checks):>5}  checked",
        f"{'  verbatim':22}{rate(lambda c: c.verbatim)}",
        f"{'  in the named turn':22}{rate(lambda c: c.in_named_turn)}",
        f"{'  from the patient':22}{rate(lambda c: c.from_patient)}",
        f"{'  all three':22}{rate(lambda c: c.verified)}",
    ])


def sample_text(batch: coverage.BatchCoverage, limit: int) -> str:
    """A few quotes that did not verify, with where the words actually are."""
    failed = [c for c in coverage.quote_checks(batch.consultations) if not c.verified][:limit]
    if not failed:
        return "\nevery quote verified."

    lines = ["", f"{len(failed)} quotes that did not verify:"]
    for check in failed:
        lines += [f'  "{check.quote[:70]}"', f"    {_why(check)}"]
    return "\n".join(lines)


def _why(check) -> str:
    """One reason, the first that applies. Saying `not the patient` about words
    that are nowhere in the transcript is noise, not a diagnosis."""
    if not check.verbatim:
        return f"says turn {check.turn} — these words are nowhere in the transcript"

    where = ", ".join(str(turn) for turn in sorted(set(check.found_in)))
    if not check.in_named_turn:
        return f"says turn {check.turn}, but the words are in turn {where}"
    return f"in turn {where}, and spoken by the doctor, not the patient"


def _consistency_text(batch: coverage.BatchCoverage) -> str:
    """2.4 — mean and SD per patient per dimension, and the one number over them.

    Printed per patient rather than pooled: two patients whose scores sit at
    opposite ends of the scale are perfectly consistent individually, and
    pooling them first would report that as noise.
    """
    scored = [s for s in batch.spreads if s.scores]
    if not scored:
        return f"{'consistency (2.4)':22}nothing scored to compare"

    patients = sorted({s.patient_id for s in scored})
    lines = [
        f"{'consistency (2.4)':22}mean ± SD per patient, over {coverage.MIN_REPEATS}+ repeats",
        "",
        f"{'dimension':22}" + "".join(f"{p:>18}" for p in patients),
    ]

    for name in coverage.DIMENSIONS:
        if name in coverage.UNSCORED_DIMENSIONS:
            continue
        cells = ""
        for patient in patients:
            spread = next((s for s in scored
                           if s.dimension == name and s.patient_id == patient), None)
            cells += f"{_mean_sd_cell(spread):>18}"
        lines.append(f"{name:22}{cells}")

    overall = batch.mean_within_patient_sd
    lines += [
        "",
        # 26, not 22: the label is itself 22 characters, so a 22-wide field puts
        # the number flush against the "SD" and it reads as "SD0.56".
        f"{'mean within-patient SD':26}{_cell(overall):>6}"
        "   ← the overall consistency measure (lower = steadier)",
    ]
    if overall is None:
        lines.append(
            f"  no cell reached {coverage.MIN_REPEATS} scored repeats, so no SD is "
            "reported. Below that a spread says nothing (TASKS 2.4)."
        )
    return "\n".join(lines)


def _mean_sd_cell(spread) -> str:
    """`4.20 ± 0.84`, or the mean alone while the sample is too small for an SD."""
    if spread is None or spread.mean is None:
        return "-"
    if spread.sd is None:
        # `± ?(1)` read as a broken number rather than as "one observation, no
        # spread": a ± with nothing after it sends the reader looking for the
        # missing figure.
        return f"{spread.mean:.2f} (n={spread.n})"
    return f"{spread.mean:.2f} ± {spread.sd:.2f}"


def _map_row(name: str, runs, patients: list) -> str:
    """Glyphs grouped by patient, so a hole in one patient reads as a hole."""
    return " ".join(
        "".join(GLYPH[c.dimensions[name].state] for c in runs if c.patient_id == patient)
        for patient in patients
    )


def _ungrounded(name: str, runs) -> int:
    return sum(1 for c in runs if c.dimensions[name].state == UNGROUNDED)


def _mean_sd(name: str, batch: coverage.BatchCoverage):
    return batch.within_patient_sd_by_dimension.get(name)


def _cell(value) -> str:
    return "-" if value is None else f"{value:.2f}"


# ── What it leaves behind ────────────────────


def write_coverage(batch_dir: Path, batch: coverage.BatchCoverage) -> Path:
    """Every cell auditable: each quote keeps the three checks that judged it."""
    payload = {
        "batch": batch.batch_id,
        "consultations": len(batch.consultations),
        "patients": len({c.patient_id for c in batch.consultations}),
        "unparsed": batch.unparsed,
        "quote_normalisation": coverage.NORMALISATION,
        "min_repeats_for_spread": coverage.MIN_REPEATS,
        "reads_ground_truth": False,   # 4.1 — coverage is truth-blind by design
        "overall": {
            "ungrounded_rate": batch.ungrounded_rate,
            # 2.4 — the average of the per-(patient, dimension) SDs
            "mean_within_patient_sd": batch.mean_within_patient_sd,
        },
        "within_patient_sd_by_dimension": batch.within_patient_sd_by_dimension,
        "by_consultation": [dataclasses.asdict(c) for c in batch.consultations],
        "by_patient_dimension": [
            {**dataclasses.asdict(s), "n": s.n} for s in batch.spreads
        ],
    }

    path = batch_dir / "coverage.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return path


def main() -> None:
    args = parse_args()
    batch_dir = Path(args.batch)

    batch = coverage.read_batch(batch_dir)

    print(report_text(batch))
    if args.sample:
        print(sample_text(batch, args.sample))
    print("\nwritten:", write_coverage(batch_dir, batch))


if __name__ == "__main__":
    main()

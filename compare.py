#!/usr/bin/env python3
# compare.py
# ─────────────────────────────────────────────
# Two arms side by side. Post-process, like cover.py and evaluate.py: no server,
# no graph, no queue.
#
#   python compare.py runs/s52-nb-1 runs/s52-bps-1
#
# Reads whatever each batch has: transcripts and reports always, and the
# evaluation.json of `evaluate.py` when it has been run. Arms are compared
# **against each other and never against their own declared budget** — every
# style overshoots the sentence count in its own file, so the number in the file
# discriminates nothing (skills/styles/README.md).
#
# Turn length is here as a between-arm signal only. On its own it measures
# verbosity, not breadth, which is why PENDING.md threw out the word-count gate
# reader; what makes it legitimate is gate B, which was fixed before the run and
# is paired by patient.
# ─────────────────────────────────────────────

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from ahead_agent import coverage
from ahead_agent.coverage import CITED_UNSCORED, GROUNDED, SILENT, UNGROUNDED


# ── One arm ──────────────────────────────────


@dataclass
class Arm:
    name: str
    batch: coverage.BatchCoverage
    turns: Dict[str, List[int]]          # patient → turns per consultation
    doctor_words: Dict[str, List[float]] # patient → mean words per doctor turn
    stop_reasons: Dict[str, int]
    evaluation: Optional[dict]

    @property
    def patients(self) -> set:
        return {c.patient_id for c in self.batch.consultations}


def read_arm(batch_dir: Path) -> Arm:
    batch = coverage.read_batch(batch_dir)

    turns: Dict[str, List[int]] = {}
    words: Dict[str, List[float]] = {}
    stops: Dict[str, int] = {}

    for consultation in batch.consultations:
        transcript = json.loads((batch_dir / consultation.run / "transcript.json").read_text())
        conversation = transcript.get("conversation") or []
        said = [line for line in conversation if line.get("role") == "doctor"]

        turns.setdefault(consultation.patient_id, []).append(transcript.get("turns") or len(said))
        if said:
            words.setdefault(consultation.patient_id, []).append(
                sum(len((line.get("content") or "").split()) for line in said) / len(said)
            )
        reason = transcript.get("stop_reason") or "?"
        stops[reason] = stops.get(reason, 0) + 1

    evaluation_path = batch_dir / "evaluation.json"
    return Arm(
        name=batch_dir.name,
        batch=batch,
        turns=turns,
        doctor_words=words,
        stop_reasons=stops,
        evaluation=json.loads(evaluation_path.read_text()) if evaluation_path.exists() else None,
    )


# ── The gates, before any number is read ─────


def gates_text(arms: List[Arm]) -> str:
    """Gate D of skills/styles/README.md: every consultation closes `doctor`.
    A style that changed the stopping rule changed something other than its
    questioning, and everything below inherits that."""
    lines = ["how the consultations ended", ""]
    passed = True

    for arm in arms:
        summary = ", ".join(f"{reason} × {n}" for reason, n in sorted(arm.stop_reasons.items()))
        ok = set(arm.stop_reasons) == {"doctor"}
        passed &= ok
        lines.append(f"  {arm.name:22}{summary}{'' if ok else '   ← not all closed by the doctor'}")
        if arm.batch.unparsed:
            lines.append(f"  {'':22}! {len(arm.batch.unparsed)} without a usable report")
            passed = False

    if not passed:
        lines += ["", "  Gate D fails. Read nothing below it as a style effect."]
    return "\n".join(lines)


# ── How each arm talked ──────────────────────


def conversation_text(arms: List[Arm]) -> str:
    lines = ["how each arm talked", "",
             f"  {'':22}{arms[0].name:>16}{arms[1].name:>16}"]

    for label, attribute in (("turns per consultation", "turns"),
                             ("words per doctor turn", "doctor_words")):
        values = [_mean(v for series in getattr(arm, attribute).values() for v in series)
                  for arm in arms]
        lines.append(f"  {label:22}{_cell(values[0]):>16}{_cell(values[1]):>16}")

    lines += ["", _gate_b(arms)]
    return "\n".join(lines)


def _gate_b(arms: List[Arm]) -> str:
    """Paired by patient, which is the whole point: the same patient under both
    arms, counted as a win or a loss, not averaged into a single number."""
    shared = sorted(arms[0].patients & arms[1].patients)
    if not shared:
        return "  no patient is in both arms, so nothing can be paired"

    wins = sum(
        1 for patient in shared
        if _mean(arms[1].doctor_words.get(patient, [])) is not None
        and _mean(arms[0].doctor_words.get(patient, [])) is not None
        and _mean(arms[1].doctor_words[patient]) > _mean(arms[0].doctor_words[patient])
    )
    # Gate B was fixed for the style pair. Between a baseline and a feature arm
    # it is just a count, and calling it a gate would borrow authority it has
    # not got here.
    return (f"  {arms[1].name} has the longer doctor turn in {wins} of {len(shared)} patients"
            f"{'   (gate B asks for 8 of 10)' if len(shared) >= 10 else ''}")


# ── What each arm reached ────────────────────


def coverage_text(arms: List[Arm]) -> str:
    header = f"{'scored':>7}{'ungr':>6}{'cited':>7}{'silent':>7}"
    lines = [
        "what each arm reached",
        "",
        f"  {'dimension':22}{header}{'  ':3}{header}{'Δreached':>10}",
        f"  {'':22}{arms[0].name:>27}{'  ':3}{arms[1].name:>27}",
    ]

    for name in coverage.DIMENSIONS:
        counts = [_states(arm, name) for arm in arms]
        # `causes` is never scored, so counting only scores would call an arm
        # that cited it five times identical to one that never mentioned it.
        delta = counts[1]["reached"] - counts[0]["reached"]
        lines.append(
            f"  {name:22}"
            + "".join(f"{c['scored']:>7}{c['ungrounded']:>6}{c['cited']:>7}{c['silent']:>7}{'  ':3}"
                      for c in counts).rstrip()
            + f"{delta:>+10}"
        )

    lines += ["", "  scored = a number came out.  ungr = a number with no verified quote.",
              "  cited = quoted but not scored.  silent = neither.",
              "  Δreached = (scored + cited), arm 2 minus arm 1."]
    return "\n".join(lines)


def _states(arm: Arm, name: str) -> Dict[str, int]:
    states = [c.dimensions[name].state for c in arm.batch.consultations]
    counts = {
        "scored": sum(1 for s in states if s in (GROUNDED, UNGROUNDED)),
        "ungrounded": sum(1 for s in states if s == UNGROUNDED),
        "cited": sum(1 for s in states if s == CITED_UNSCORED),
        "silent": sum(1 for s in states if s == SILENT),
    }
    counts["reached"] = counts["scored"] + counts["cited"]
    return counts


# ── What each arm got right, when evaluated ──


def accuracy_text(arms: List[Arm]) -> str:
    if not all(arm.evaluation for arm in arms):
        missing = [arm.name for arm in arms if not arm.evaluation]
        return ("how accurate each arm was\n\n"
                f"  no evaluation.json in: {', '.join(missing)}\n"
                "  run evaluate.py on both arms first")

    lines = [
        "how accurate each arm was",
        "",
        f"  {'dimension':22}{'MAE':>8}{'bias':>8}{'  ':4}{'MAE':>8}{'bias':>8}{'ΔMAE':>9}",
        f"  {'':22}{arms[0].name:>16}{'  ':4}{arms[1].name:>16}",
    ]

    for name in coverage.DIMENSIONS:
        cells, maes = [], []
        for arm in arms:
            entry = (arm.evaluation.get("by_dimension") or {}).get(name) or {}
            maes.append(entry.get("mae"))
            cells.append(f"{_cell(entry.get('mae')):>8}{_cell(entry.get('bias'), sign=True):>8}")
        if all(m is None for m in maes):
            continue
        delta = None if None in maes else maes[1] - maes[0]
        lines.append(f"  {name:22}{cells[0]}{'  ':4}{cells[1]}{_cell(delta, sign=True):>9}")

    overall = [(arm.evaluation.get("overall") or {}).get("mae") for arm in arms]
    lines += ["", f"  {'overall MAE':22}{_cell(overall[0]):>8}{'':8}{'  ':4}{_cell(overall[1]):>8}"]
    return "\n".join(lines)


# ── Arithmetic and formatting ────────────────


def _mean(values):
    present = [v for v in values if v is not None]
    return round(sum(present) / len(present), 2) if present else None


def _cell(value, sign: bool = False) -> str:
    if value is None:
        return "-"
    return f"{value:+.2f}" if sign else f"{value:.2f}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Two arms side by side")
    parser.add_argument("first", help="a run directory, e.g. runs/s52-nb-1")
    parser.add_argument("second", help="the arm to compare it against")
    args = parser.parse_args()

    arms = [read_arm(Path(args.first)), read_arm(Path(args.second))]

    print(f"{arms[0].name}  vs  {arms[1].name}\n")
    for block in (gates_text, conversation_text, coverage_text, accuracy_text):
        print(block(arms))
        print()

    print("Arms are compared against each other, never against the budget declared\n"
          "in their own style file — every style overshoots its own sentence count.")


if __name__ == "__main__":
    main()

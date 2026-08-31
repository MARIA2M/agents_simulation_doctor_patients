#!/usr/bin/env python3
# tools/make_dummy_batch.py
# ─────────────────────────────────────────────
# A batch with a known answer, for exercising cover.py without a model.
#
# Every cell of the coverage map is planted on purpose, so what comes out can be
# checked against what went in. Two patients × five repeats — five because below
# that there is no spread to compute (coverage.MIN_REPEATS).
#
# It was three until 2026-08-31, from when the floor was three. Against a floor
# of five that produced a batch whose every SD was null, while the text below
# promised numbers: the generator quietly stopped exercising the thing it exists
# to exercise.
#
#   python tools/make_dummy_batch.py
#   python cover.py /tmp/ahead-dummy-batch --sample 6
#
# It writes outside runs/ by default and on purpose: a fabricated batch sitting
# next to the real ones is the kind of thing that gets analysed by accident.
# ─────────────────────────────────────────────

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from ahead_agent.config import BIPQ_DIMENSIONS, BMQ_SUBSCALES  # noqa: E402


# ── The consultation ─────────────────────────
# A turn is an EXCHANGE: the doctor's line and the patient's reply share a
# number, exactly as nodes.py writes them.

CONVERSATION = [
    {"turn": 1, "role": "doctor", "content": "Good morning. What brings you in today?"},
    {"turn": 1, "role": "patient",
     "content": "I can barely get through a shift any more. The tiredness is constant."},
    {"turn": 2, "role": "doctor", "content": "And how are you getting on with the tablets?"},
    {"turn": 2, "role": "patient",
     "content": "I'd not miss a dose, whatever else happens. They frighten me a little, though."},
    {"turn": 3, "role": "doctor", "content": "What do you think caused it?"},
    {"turn": 3, "role": "patient",
     "content": "My father had the same thing. I have always thought it ran in the family."},
]

SHIFT = "I can barely get through a shift any more."
DOSE = "I'd not miss a dose, whatever else happens."
FATHER = "My father had the same thing."
DOCTOR_LINE = "And how are you getting on with the tablets?"


def quote(text: str, turn: int) -> dict:
    return {"quote": text, "turn": turn}


def dimension(evidence: list, score, confidence: float = 0.8) -> dict:
    return {"evidence": evidence, "reasoning": "planted by make_dummy_batch",
            "score": score, "confidence": confidence}


def body(dimensions: dict, causes: list = (), causes_evidence: list = ()) -> dict:
    """Only the dimensions named; the rest come back NA through report.parse."""
    report = {"clinical_summary": "A fabricated consultation.",
              "bipq": {}, "bmq": {},
              "causes": list(causes), "causes_evidence": list(causes_evidence)}
    for name, value in dimensions.items():
        block = "bipq" if name in BIPQ_DIMENSIONS else "bmq"
        report[block][name] = value
    return report


# ── What is planted where ────────────────────

# One repeat carrying every failure mode at once, so the map has something in
# each cell and --sample has something to explain.
PLANTED = body(
    {
        # ● grounded — real words, right turn, patient's line
        "consequences": dimension([quote(SHIFT, 1)], 8),
        # ● and turn 1 is now cited twice: a reuse candidate for V3
        "identity": dimension([quote(SHIFT, 1)], 6),
        "specific_necessity": dimension([quote(DOSE, 2)], 4.5),
        # ○ a number with no evidence at all
        "concern": dimension([], 7),
        # ○ a quote nobody said
        "emotional_response": dimension([quote("I lie awake terrified every night", 1)], 8),
        # ○ real words, wrong turn — the 8.8 failure
        "timeline": dimension([quote(SHIFT, 3)], 5),
        # ○ the doctor quoting itself
        "coherence": dimension([quote(DOCTOR_LINE, 2)], 4),
        # ◐ quoted, then declined to score
        "personal_control": dimension([quote(FATHER, 3)], None),
        # treatment_control, specific_concerns, general_harm, general_overuse
        # are absent → · silent
    },
    causes=["family history"],
    causes_evidence=[quote(FATHER, 3)],   # ◐ causes is never scored
)


def clean(consequences, identity, necessity, concern, timeline) -> dict:
    """A repeat with nothing wrong in it, so the planted one stands out."""
    return body(
        {
            "consequences": dimension([quote(SHIFT, 1)], consequences),
            "identity": dimension([quote(SHIFT, 1)], identity),
            "specific_necessity": dimension([quote(DOSE, 2)], necessity),
            "concern": dimension([quote(SHIFT, 1)], concern),
            "timeline": dimension([quote(FATHER, 3)], timeline),
        },
        causes=["family history"],
        causes_evidence=[quote(FATHER, 3)],
    )


# Scores chosen so the spread is a number worth reading, not zero. Five repeats
# each: MIN_REPEATS is the floor, so four would put every cell back to null.
PATIENTS = {
    "DUMMY-001": [PLANTED,
                  clean(5, 6, 4.0, 6, 4),
                  clean(6, 7, 4.5, 6, 5),
                  clean(6, 6, 4.0, 7, 5),
                  clean(5, 7, 4.5, 6, 4)],
    "DUMMY-002": [clean(4, 3, 2.0, 3, 8),
                  clean(4, 3, 2.5, 3, 8),
                  clean(5, 4, 2.0, 4, 7),
                  clean(4, 3, 2.5, 3, 8),
                  clean(5, 4, 2.0, 4, 7)],
}


# ── Writing it out ───────────────────────────


def write_batch(out: Path) -> None:
    index = {"batch_id": out.name, "repeats": 5, "consultations": []}

    for patient_id, reports in PATIENTS.items():
        for repeat, report in enumerate(reports, start=1):
            name = f"{patient_id}-r{repeat}"
            run_dir = out / name
            run_dir.mkdir(parents=True, exist_ok=True)

            (run_dir / "transcript.json").write_text(json.dumps({
                "patient_id": patient_id,
                "turns": 3,
                "stop_reason": "doctor",
                "conversation": CONVERSATION,
                "coverage_hint": {},
                "working_notes": [],
                "events": [],
                "usage": [],
            }, indent=2) + "\n")

            (run_dir / "report.json").write_text(json.dumps({
                "patient_id": patient_id, "attempts": 1, "parsed": True,
                "report": {"patient_id": patient_id, **report},
            }, indent=2) + "\n")

            index["consultations"].append({
                "run": name, "patient_id": patient_id, "repeat": repeat,
                "status": "ok", "turns": 3, "stop_reason": "doctor",
            })

    (out / "batch.json").write_text(json.dumps(index, indent=2) + "\n")


EXPECTED = """
What went in, so you can check what comes out:

  DUMMY-001-r1 carries one of every failure, the other nine runs are clean.

  ●  consequences, identity, specific_necessity   real words, right turn, patient
  ○  concern              a score with no evidence at all
  ○  emotional_response   a quote nobody said        → "nowhere in the transcript"
  ○  timeline             real words, wrong turn     → "the words are in turn 1"
  ○  coherence            the doctor quoting itself  → "spoken by the doctor"
  ◐  personal_control     quoted, then not scored
  ◐  causes               never scorable by design
  ·  treatment_control, specific_concerns, general_harm, general_overuse

  quotes            62 checked, 59 verify (95%). Only THREE fail, not four:
                    `concern` is ungrounded with no quote at all, so it puts
                    nothing in the denominator. A missing citation and a bad
                    one are different failures and are counted apart.
  ungrounded rate   4 of the 52 scores emitted = 0.077
  reused turns      20, which is 2 per consultation — turn 1 (consequences +
                    identity) and turn 3 (causes + personal_control)
  SD                the column is the mean over patients. `timeline` reads 0.55,
                    which is 0.548 on each patient; `consequences` is the widest,
                    because DUMMY-001-r1 plants an 8 among fives and sixes. Per
                    patient the mean and the SD are both in coverage.json, and
                    they are real numbers at all — unlike e4-1 — only because
                    there are five repeats.

  mean within-patient SD    0.561, the average of the ten (patient, dimension)
                    cells that have an SD. It is the 2.4 headline, and averaging
                    per-patient SDs is what keeps it consistency: pooling the
                    scores first would let the gap between DUMMY-001 and
                    DUMMY-002 inflate it, and that gap is 2.5's question.

  And the thing worth looking at twice: `timeline` has a tight spread (0.55) and
  is ungrounded in DUMMY-001-r1. Consistency and grounding are independent —
  a score can be perfectly stable across repeats and stand on nothing.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="A fabricated batch for cover.py")
    parser.add_argument("--out", default="/tmp/ahead-dummy-batch",
                        help="where to write it. Default: /tmp/ahead-dummy-batch")
    args = parser.parse_args()

    out = Path(args.out)
    write_batch(out)

    print(f"written: {out}  (2 patients × 5 repeats)")
    print(EXPECTED)
    print(f"  python cover.py {out} --sample 6")


if __name__ == "__main__":
    main()

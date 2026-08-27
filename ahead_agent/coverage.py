# ahead_agent/coverage.py
# ─────────────────────────────────────────────
# V1 — what a report can point at in its own transcript, and how much the score
# moves when the same patient is run again (3.2, 2.4).
#
# Deterministic: string comparison and a standard deviation, no model call.
# Post-process only — nothing here imports from nodes or graph, so it runs over
# any arm's batch (§2). And it never opens patients/*.json: coverage is
# truth-blind, which is what stops the map being contaminated by the answer.
#
# What it does NOT do is say whether the doctor asked. That needs a judgement
# about language and is deliberately out of V1.
# ─────────────────────────────────────────────

from __future__ import annotations

import json
import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import report as report_module
from .config import BIPQ_DIMENSIONS, BMQ_SUBSCALES, CAUSES_DIMENSION

DIMENSIONS: List[str] = list(BIPQ_DIMENSIONS) + list(BMQ_SUBSCALES) + [CAUSES_DIMENSION]

# The four cells of score × verified evidence.
GROUNDED = "GROUNDED"                # a number, and something real behind it
UNGROUNDED = "UNGROUNDED"            # a number from nothing — the alarm
CITED_UNSCORED = "CITED_UNSCORED"    # it quoted and then declined to score
SILENT = "SILENT"                    # neither

# `causes` is never scored (4.3), so it can only ever land in the bottom row.
UNSCORED_DIMENSIONS = frozenset({CAUSES_DIMENSION})

# Below three present values a spread is noise, so it is None rather than a
# number nobody should read (2.4).
MIN_REPEATS = 3


# ── Reading a quote back (objective 3) ───────

_SPACE = re.compile(r"\s+")
_TYPOGRAPHY = str.maketrans(
    {"‘": "'", "’": "'", "“": '"', "”": '"',
     "–": "-", "—": "-", "…": "..."}
)

# Recorded in the output: a rate is only reproducible next to the rule that made it.
NORMALISATION = "whitespace collapsed, quotes and dashes unified, case folded"


def _normalise(text: str) -> str:
    return _SPACE.sub(" ", text.translate(_TYPOGRAPHY)).strip().casefold()


@dataclass
class QuoteCheck:
    """One `Evidence` against the conversation it claims to come from.

    Three questions, kept apart: a quote can be real and still be filed under
    the wrong turn, or be the doctor quoting itself. Collapsing them into one
    verdict loses which one failed, and those are different findings.
    """

    quote: str
    turn: int                # the turn the report named
    found_in: List[int]      # the turns the words are actually in
    verbatim: bool           # E0 — the words are somewhere in the transcript
    in_named_turn: bool      # E1 — in a line carrying the turn that was named
    from_patient: bool       # E1 — in a line the patient spoke
    verified: bool           # both at once: the patient's line, at that turn


def check_quote(evidence, conversation: List[Dict[str, Any]]) -> QuoteCheck:
    """Where a quote does and does not hold up. No model: `in` and nothing else.

    A turn is an exchange, not an intervention: `nodes.py` gives the doctor's
    line and the patient's reply the same number. So the line has to be found by
    matching turn *and* speaker together — picking the first line with that
    number lands on the doctor every time.
    """
    needle = _normalise(evidence.quote)
    matches = [
        line
        for line in conversation
        if needle and needle in _normalise(line.get("content") or "")
    ]
    at_named_turn = [line for line in matches if line.get("turn") == evidence.turn]

    return QuoteCheck(
        quote=evidence.quote,
        turn=evidence.turn,
        found_in=[line.get("turn") for line in matches],
        verbatim=bool(matches),
        in_named_turn=bool(at_named_turn),
        from_patient=any(line.get("role") == "patient" for line in matches),
        verified=any(line.get("role") == "patient" for line in at_named_turn),
    )


def quote_checks(consultations: List["ConsultationCoverage"]) -> List[QuoteCheck]:
    return [q for c in consultations for d in c.dimensions.values() for q in d.quotes]


# ── One dimension of one consultation ────────


@dataclass
class DimensionCoverage:
    dimension: str
    score: Optional[float]
    confidence: float
    quotes: List[QuoteCheck]
    state: str

    @property
    def verified(self) -> int:
        return sum(1 for quote in self.quotes if quote.verified)


def _state(score: Optional[float], quotes: List[QuoteCheck]) -> str:
    """A score standing on no verified quote is the finding this module exists for.

    Unverified evidence counts as none: a quote that is not in the transcript
    supports nothing, whatever it was meant to say.
    """
    grounded = any(quote.verified for quote in quotes)
    if score is None:
        return CITED_UNSCORED if grounded else SILENT
    return GROUNDED if grounded else UNGROUNDED


def _dimension(name: str, scored, conversation) -> DimensionCoverage:
    quotes = [check_quote(evidence, conversation) for evidence in scored.evidence]
    score = None if name in UNSCORED_DIMENSIONS else scored.score
    return DimensionCoverage(
        dimension=name,
        score=score,
        confidence=scored.confidence,
        quotes=quotes,
        state=_state(score, quotes),
    )


# ── One consultation ─────────────────────────


@dataclass
class ConsultationCoverage:
    run: str
    patient_id: str
    repeat: int
    dimensions: Dict[str, DimensionCoverage]
    turn_reuse: Dict[int, List[str]] = field(default_factory=dict)
    # copied through: empty in the `off` arm, the doctor's own claim in the others
    coverage_hint: Dict[str, str] = field(default_factory=dict)
    working_notes: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def ungrounded(self) -> List[str]:
        return [name for name, d in self.dimensions.items() if d.state == UNGROUNDED]


def _turn_reuse(dimensions: Dict[str, DimensionCoverage]) -> Dict[int, List[str]]:
    """Patient turns that several dimensions were read out of.

    A turn cited for k dimensions carried more than one thing, so at most one of
    them answers whatever was asked. These are the candidates for information
    the patient added unprompted — candidates, not a measurement: the styles
    stack several questions into one turn, so which was asked is not readable
    here. V3 gets the shortlist instead of the whole conversation.
    """
    per_turn: Dict[int, List[str]] = {}
    for name, dimension in dimensions.items():
        for turn in {q.turn for q in dimension.quotes if q.verified}:
            per_turn.setdefault(turn, []).append(name)

    return {turn: sorted(names) for turn, names in sorted(per_turn.items()) if len(names) > 1}


def read_consultation(run_dir: Path, patient_id: str, repeat: int) -> Optional[ConsultationCoverage]:
    """One consultation's coverage, or None when it left no usable report."""
    transcript = json.loads((run_dir / "transcript.json").read_text())
    payload = json.loads((run_dir / "report.json").read_text())

    # Re-parsed rather than taken on trust, so the NA policy of 4.4 is applied
    # here too — the same thing evaluate.py does with the stored document.
    parsed = (
        report_module.parse(json.dumps(payload["report"]), patient_id)
        if payload.get("report")
        else None
    )
    if parsed is None:
        return None

    conversation = transcript.get("conversation") or []

    # `causes` has evidence and no score, so it is given the same shape as the
    # twelve and lands in the unscored row by construction.
    scored = {
        **parsed.bipq,
        **parsed.bmq,
        CAUSES_DIMENSION: report_module.DimensionScore(
            CAUSES_DIMENSION, parsed.causes_evidence, "", None, 0.0
        ),
    }

    dimensions = {name: _dimension(name, scored[name], conversation) for name in DIMENSIONS}

    return ConsultationCoverage(
        run=run_dir.name,
        patient_id=patient_id,
        repeat=repeat,
        dimensions=dimensions,
        turn_reuse=_turn_reuse(dimensions),
        coverage_hint=transcript.get("coverage_hint") or {},
        working_notes=transcript.get("working_notes") or [],
    )


# ── The same patient, run again (2.4) ────────


@dataclass
class Spread:
    """How far one patient's score moves across repeats of the same consultation."""

    patient_id: str
    dimension: str
    scores: List[float]
    na: int
    sd: Optional[float]

    @property
    def n(self) -> int:
        return len(self.scores)


def spreads(consultations: List[ConsultationCoverage]) -> List[Spread]:
    """One entry per (patient, dimension). Grouped by patient on purpose: a
    repeat is not another patient, which is what 2.4 and 2.5 turn on."""
    by_patient: Dict[str, List[ConsultationCoverage]] = {}
    for consultation in consultations:
        by_patient.setdefault(consultation.patient_id, []).append(consultation)

    results = []
    for patient_id, runs in sorted(by_patient.items()):
        for name in DIMENSIONS:
            if name in UNSCORED_DIMENSIONS:
                continue
            values = [c.dimensions[name].score for c in runs]
            present = [v for v in values if v is not None]
            results.append(
                Spread(
                    patient_id=patient_id,
                    dimension=name,
                    scores=present,
                    na=len(values) - len(present),
                    # sample sd, and only once there is enough of a sample
                    sd=round(statistics.stdev(present), 3) if len(present) >= MIN_REPEATS else None,
                )
            )
    return results


# ── The batch ────────────────────────────────


@dataclass
class BatchCoverage:
    batch_id: str
    consultations: List[ConsultationCoverage]
    spreads: List[Spread]
    unparsed: List[str]

    @property
    def ungrounded_rate(self) -> Optional[float]:
        """Of the scores actually emitted, how many stand on nothing."""
        states = [d.state for c in self.consultations for d in c.dimensions.values()]
        emitted = sum(1 for s in states if s in (GROUNDED, UNGROUNDED))
        if not emitted:
            return None
        return round(sum(1 for s in states if s == UNGROUNDED) / emitted, 3)


def _index(batch: Path) -> List[Dict[str, Any]]:
    """Which consultation is which. `batch.json` when it is there — run_batch
    rewrites it after every consultation, so it survives a walltime kill — and
    the directory names when it is not."""
    manifest = batch / "batch.json"
    if manifest.exists():
        return [
            {"run": c["run"], "patient_id": c["patient_id"], "repeat": c["repeat"]}
            for c in json.loads(manifest.read_text()).get("consultations", [])
            if c.get("status") == "ok"
        ]

    entries = []
    for path in sorted(batch.glob("*/transcript.json")):
        name = path.parent.name
        patient_id, _, repeat = name.rpartition("-r")
        entries.append({
            "run": name,
            "patient_id": patient_id or name,
            "repeat": int(repeat) if repeat.isdigit() else 1,
        })
    return entries


def read_batch(batch: Path) -> BatchCoverage:
    """Every consultation of a batch, grouped by patient."""
    if not batch.is_dir():
        raise SystemExit(f"{batch}: no such directory")

    index = _index(batch)
    consultations, unparsed, incomplete = [], [], []

    for entry in index:
        run_dir = batch / entry["run"]
        # Both, and checked here: a consultation missing either is a fact about
        # the batch, not an exception halfway through reading it.
        if not all((run_dir / f).exists() for f in ("transcript.json", "report.json")):
            incomplete.append(entry["run"])
            continue

        coverage = read_consultation(run_dir, entry["patient_id"], entry["repeat"])
        if coverage is None:
            unparsed.append(entry["run"])
        else:
            consultations.append(coverage)

    if not consultations:
        raise SystemExit(_nothing_to_read(batch, index, incomplete, unparsed))

    return BatchCoverage(
        batch_id=batch.name,
        consultations=consultations,
        spreads=spreads(consultations),
        unparsed=unparsed,
    )


def _nothing_to_read(batch: Path, index, incomplete, unparsed) -> str:
    """Why the batch came out empty, in enough detail to fix it without guessing."""
    source = "batch.json" if (batch / "batch.json").exists() else "directory names"
    present = sorted(p.name for p in batch.iterdir() if p.is_dir())

    lines = [
        f"{batch}: nothing to read.",
        f"  index built from : {source}  ({len(index)} consultations)",
        f"  missing a file   : {len(incomplete)}" + (f"  {', '.join(incomplete[:5])}" if incomplete else ""),
        f"  no usable report : {len(unparsed)}" + (f"  {', '.join(unparsed[:5])}" if unparsed else ""),
        f"  directories here : {', '.join(present[:8]) or 'none'}",
    ]
    if index and incomplete == [entry["run"] for entry in index]:
        lines.append("  → the index names directories that are not there, or they hold "
                     "other filenames than transcript.json / report.json")
    return "\n".join(lines)

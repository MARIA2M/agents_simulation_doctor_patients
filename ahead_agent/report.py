# ahead_agent/report.py
# ─────────────────────────────────────────────
# What the doctor hands in at the end, and what a run leaves behind.
# The field order of DimensionScore is the specification (2.1).
# ─────────────────────────────────────────────

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import BIPQ_DIMENSIONS, BMQ_SUBSCALES


# ── The contract (2.1) ───────────────────────


@dataclass
class Evidence:
    """A line the doctor is quoting, and the turn it came from."""

    quote: str
    turn: int


@dataclass
class DimensionScore:
    dimension: str
    evidence: List[Evidence]      # FIRST
    reasoning: str                # SECOND
    score: Optional[float]        # THIRD — None is NA, never a default (4.4)
    confidence: float             # 0–1, declared by the doctor (2.3)


@dataclass
class Report:
    patient_id: str
    clinical_summary: str
    bipq: Dict[str, DimensionScore] = field(default_factory=dict)   # 8 dimensions
    bmq: Dict[str, DimensionScore] = field(default_factory=dict)    # 4 sub-scales
    causes: List[str] = field(default_factory=list)                 # open, ranked
    causes_evidence: List[Evidence] = field(default_factory=list)


# ── Reading what came back (4.4) ─────────────

BIPQ_RANGE = (0.0, 10.0)   # the B-IPQ scale
BMQ_RANGE = (1.0, 5.0)     # the BMQ scale

# asked for in REPORT.md and ignored: GLM fences the object anyway
FENCES = re.compile(r"\A\s*```(?:json)?\s*|\s*```\s*\Z")


def parse(raw: Optional[str], patient_id: str) -> Optional[Report]:
    """The doctor's reply as a Report, or None if there is no object in it."""
    data = _json_object(raw)
    if data is None:
        return None

    # N3 — a cause it cannot quote for is dropped, like a score it cannot quote for
    causes_evidence = _quotes(data.get("causes_evidence"))
    causes = [_as_text(cause) for cause in _as_list(data.get("causes")) if _as_text(cause)]

    return Report(
        patient_id=patient_id,
        clinical_summary=_as_text(data.get("clinical_summary")),
        bipq=_all_dimensions(data.get("bipq"), BIPQ_DIMENSIONS, BIPQ_RANGE),
        bmq=_all_dimensions(data.get("bmq"), BMQ_SUBSCALES, BMQ_RANGE),
        causes=causes if causes_evidence else [],
        causes_evidence=causes_evidence,
    )


def _json_object(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    try:
        parsed = json.loads(FENCES.sub("", raw).strip())
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _all_dimensions(data: Any, names: List[str], scale) -> Dict[str, "DimensionScore"]:
    """Every name is present, whether or not the doctor reported it."""
    reported = data if isinstance(data, dict) else {}
    return {name: _one_dimension(name, reported.get(name), scale) for name in names}


def _one_dimension(name: str, data: Any, scale) -> "DimensionScore":
    if not isinstance(data, dict):
        return DimensionScore(name, [], "", None, 0.0)

    return DimensionScore(
        dimension=name,
        evidence=_quotes(data.get("evidence")),
        reasoning=_as_text(data.get("reasoning")),
        score=_score_or_na(data.get("score"), scale),
        confidence=_confidence_or_zero(data.get("confidence")),
    )


def _score_or_na(value: Any, scale) -> Optional[float]:
    """Off the scale is NA, never clamped: the old arm's min/max made an illegal
    value look legal, and it counted as a hit."""
    low, high = scale
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if low <= value <= high else None


def _confidence_or_zero(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return min(1.0, max(0.0, float(value)))


def _quotes(data: Any) -> List["Evidence"]:
    quotes = []
    for item in _as_list(data):
        if not isinstance(item, dict):
            continue
        quote, turn = _as_text(item.get("quote")), item.get("turn")
        if quote:
            quotes.append(Evidence(quote=quote, turn=turn if isinstance(turn, int) else -1))
    return quotes


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _as_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


# ── Is it finished? (1.13) ───────────────────


def gaps(report: Optional[Report]) -> List[str]:
    """Dimensions the doctor never accounted for.

    A declared NA has a reasoning and is an answer; one the parser filled in has
    none, and that silence is the only thing worth asking about twice.
    """
    if report is None:
        return list(BIPQ_DIMENSIONS) + list(BMQ_SUBSCALES)

    return [
        name
        for scored in (report.bipq, report.bmq)
        for name, dimension in scored.items()
        if not dimension.reasoning
    ]


def retry_note(missing: List[str]) -> str:
    """What the doctor is told on a second pass."""
    return (
        "Your report did not account for: " + ", ".join(missing) + ".\n\n"
        "Write it out again in full. For each of those, either quote what the "
        "patient said and score it, or set the score to null and say in the "
        "reasoning why you cannot — that you did not explore it, or that what "
        "they said will not carry a number. Do not reach for evidence to fill a "
        "gap: a declared null is the right answer and costs you nothing."
    )


# ── What the report prompt is shown ──────────


def transcript_text(conversation: List[Dict[str, Any]]) -> str:
    """The consultation, numbered — Evidence.turn points back into this."""
    return "\n\n".join(
        f"[turn {line['turn']}] {line['role'].capitalize()}: {line['content']}"
        for line in conversation
    )


# ── What a run leaves behind ─────────────────


# 4.1
def write_transcript(final_state, outdir: Path) -> Path:
    """The consultation as it happened, without the patient's belief_profile."""
    transcript = {
        "patient_id": final_state.patient.get("patient_id"),
        "turns": final_state.turn_count,
        "stop_reason": final_state.stop_reason,
        "conversation": final_state.conversation,
        "coverage_hint": final_state.coverage_hint,   # what it believed it had covered
        "working_notes": final_state.working_notes,   # in order, with their turn
        "events": final_state.events,
        "usage": final_state.usage,
    }

    path = outdir / "transcript.json"
    path.write_text(json.dumps(transcript, indent=2) + "\n")
    return path


# D7
def write_report(final_state, outdir: Path) -> Path:
    """The report as a document. Only what could not be parsed is kept as text."""
    if final_state.report is None and final_state.report_raw:
        (outdir / "report_raw.txt").write_text(final_state.report_raw + "\n")

    payload = {
        "patient_id": final_state.patient.get("patient_id"),
        "attempts": final_state.report_attempts,
        "parsed": final_state.report is not None,
        "report": asdict(final_state.report) if final_state.report else None,
    }

    path = outdir / "report.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return path

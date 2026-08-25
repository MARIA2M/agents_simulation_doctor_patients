# ahead_agent/reproducibility.py
# ─────────────────────────────────────────────
# What a batch says about itself, without ground truth (3.3).
#
# Two numbers, and they only mean something together (2.5):
#
#   dispersion (2.4)     how much one patient's score moves between repeats
#   discrimination (2.5) how far apart the patients are from each other
#
# Apart, either one lies. llama3.2 answering 8 to everything had perfect
# dispersion and was useless (P4); a model that scattered at random would look
# discriminating and be noise. Low dispersion + high discrimination is the only
# pair that means the doctor read the patient.
#
# No ground truth is read here on purpose — that is evaluation.py (4.2). This
# module compares reports against each other, so it runs on any arm's batch,
# including the elicitation one (5.2).
# ─────────────────────────────────────────────

from __future__ import annotations

import json
import statistics as st
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import BIPQ_DIMENSIONS, BMQ_SUBSCALES

DIMENSIONS = list(BIPQ_DIMENSIONS) + list(BMQ_SUBSCALES)

# 2.4: "por debajo de N=5 la dispersión no significa nada". Below it the numbers
# are still computed — they are what a smoke batch has — but they are marked.
MEANINGFUL_REPEATS = 5


@dataclass
class DimensionSpread:
    """One dimension, across every patient and every repeat of a batch."""

    dimension: str
    dispersion: Optional[float]      # 2.4 — mean sd of a patient across repeats
    discrimination: Optional[float]  # 2.5 — sd of the patient means
    scored: int                      # how many scores went into the two above
    na: int                          # and how many were NA, never imputed (4.4)

    @property
    def ratio(self) -> Optional[float]:
        """Discrimination over dispersion: how much signal per unit of noise.

        Below 1 the distance between two patients is smaller than the distance
        between two runs of the same one, and the dimension cannot separate them.
        """
        if not self.dispersion or self.discrimination is None:
            return None
        return self.discrimination / self.dispersion


@dataclass
class Spread:
    batch_id: str
    patients: int
    repeats: int
    dimensions: Dict[str, DimensionSpread] = field(default_factory=dict)
    # The same dispersion read per patient rather than per dimension: it is what
    # says which patient the doctor is least stable about.
    per_patient: Dict[str, Optional[float]] = field(default_factory=dict)

    @property
    def underpowered(self) -> bool:
        return self.repeats < MEANINGFUL_REPEATS


# ── Reading a batch ──────────────────────────

def load(batch_dir: Path | str) -> Dict[str, List[Dict[str, Optional[float]]]]:
    """patient_id → one dict of scores per repeat, in run order.

    A report that never parsed contributes a row of NA rather than being
    dropped: it happened, and a batch that silently ignores it looks cleaner
    than it was.
    """
    batch_dir = Path(batch_dir)
    runs: Dict[str, List[Dict[str, Optional[float]]]] = {}

    for path in sorted(batch_dir.glob("*/report.json")):
        payload = json.loads(path.read_text())
        patient_id = payload.get("patient_id") or path.parent.name
        runs.setdefault(patient_id, []).append(_scores(payload.get("report")))

    return runs


def _scores(report: Optional[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    """One report flattened to dimension → score. NA stays None."""
    if not report:
        return {name: None for name in DIMENSIONS}

    flat = {}
    for section in ("bipq", "bmq"):
        for name, scored in (report.get(section) or {}).items():
            flat[name] = scored.get("score") if isinstance(scored, dict) else None

    return {name: flat.get(name) for name in DIMENSIONS}


# ── The two numbers ──────────────────────────

def spread(runs: Dict[str, List[Dict[str, Optional[float]]]], batch_id: str) -> Spread:
    """Dispersion and discrimination, always in the same object (2.5)."""
    repeats = min((len(rows) for rows in runs.values()), default=0)

    result = Spread(
        batch_id=batch_id,
        patients=len(runs),
        repeats=repeats,
        dimensions={name: _dimension(runs, name) for name in DIMENSIONS},
        per_patient={
            patient_id: _sd([_mean(_present(row.values())) for row in rows])
            for patient_id, rows in sorted(runs.items())
        },
    )
    return result


def _dimension(runs, name: str) -> DimensionSpread:
    within, means, scored, na = [], [], 0, 0

    for rows in runs.values():
        values = [row.get(name) for row in rows]
        present = _present(values)

        scored += len(present)
        na += len(values) - len(present)

        # A patient scored once cannot disperse; it can still discriminate.
        if len(present) > 1:
            within.append(st.stdev(present))
        if present:
            means.append(_mean(present))

    return DimensionSpread(
        dimension=name,
        dispersion=_mean(within),
        discrimination=_sd(means),
        scored=scored,
        na=na,
    )


def _present(values) -> List[float]:
    """NA is excluded from every statistic and counted separately (4.4).

    Imputing it would be the old arm's default of 5 wearing a different hat.
    """
    return [float(v) for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]


def _mean(values: List[float]) -> Optional[float]:
    return round(st.mean(values), 3) if values else None


def _sd(values) -> Optional[float]:
    values = [v for v in values if v is not None]
    return round(st.stdev(values), 3) if len(values) > 1 else None


# ── What it leaves behind ────────────────────

def write(result: Spread, outdir: Path | str) -> Path:
    """reproducibility.json, next to the batch it describes."""
    payload = asdict(result)
    payload["underpowered"] = result.underpowered
    for name, dimension in result.dimensions.items():
        payload["dimensions"][name]["ratio"] = dimension.ratio

    path = Path(outdir) / "reproducibility.json"
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path


def report_text(result: Spread) -> str:
    """The two columns side by side, because neither is read alone (2.5)."""
    lines = [
        f"{result.batch_id}: {result.patients} patients x {result.repeats} repeats",
        "",
        f"{'dimension':22}{'dispersion':>12}{'discrim.':>11}{'ratio':>8}{'NA':>5}",
    ]
    for name, d in result.dimensions.items():
        lines.append(
            f"{name:22}{_cell(d.dispersion):>12}{_cell(d.discrimination):>11}"
            f"{_cell(d.ratio):>8}{d.na:>5}"
        )

    if result.underpowered:
        lines += ["", f"! {result.repeats} repeats: below {MEANINGFUL_REPEATS} the "
                      "dispersion is not worth reading (2.4)"]
    return "\n".join(lines)


def _cell(value: Optional[float]) -> str:
    return "-" if value is None else f"{value:.2f}"


if __name__ == "__main__":
    import sys

    batch = Path(sys.argv[1])
    result = spread(load(batch), batch.name)
    print(report_text(result))
    print("\nwritten:", write(result, batch))

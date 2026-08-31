# ahead_agent/evaluation.py
# ─────────────────────────────────────────────
# Reports against ground truth. Post-process only: nothing here imports from
# nodes or graph, so it runs over any arm's runs, elicitation included (§2).
# The two correlations never share a name — see STATUS 4.2.
# ─────────────────────────────────────────────

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .config import BIPQ_DIMENSIONS, BMQ_SUBSCALES

# how close counts as close (4.2); the thresholds differ because the scales do
BIPQ_TOLERANCES: Tuple[Tuple[str, float], ...] = (("within_1", 1.0), ("within_2", 2.0))
BMQ_TOLERANCES: Tuple[Tuple[str, float], ...] = (("within_half", 0.5), ("within_one", 1.0))

# 2.5 needs distinct people, not distinct reports (D12). Two points always
# correlate at ±1, so three is the floor at which the number says anything.
MIN_PATIENTS = 3


# ── PORTADO: Pearson in pure Python ──────────


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    """None rather than 0.0 when it cannot be computed."""
    n = len(xs)
    if n < 2:
        return None

    mx, my = sum(xs) / n, sum(ys) / n
    numerator = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))

    return round(numerator / (dx * dy), 3) if dx * dy > 0 else None


# ── One dimension ────────────────────────────


@dataclass
class DimensionMetrics:
    """PORTADO, except that absolute_error and bias may be None (NUEVO)."""

    dimension: str
    ground_truth: Optional[float]
    inferred: Optional[float]
    absolute_error: Optional[float]
    bias: Optional[float]                       # inferred − truth, + = overscored
    bands: Dict[str, bool] = field(default_factory=dict)

    # 4.4
    @property
    def scored(self) -> bool:
        """No number on either side is not an error of zero."""
        return self.absolute_error is not None


def _dimension_metrics(name: str, truth: Any, inferred: Any, tolerances) -> DimensionMetrics:
    truth = truth if isinstance(truth, (int, float)) and not isinstance(truth, bool) else None
    inferred = inferred if isinstance(inferred, (int, float)) else None

    if truth is None or inferred is None:
        return DimensionMetrics(name, truth, inferred, None, None, {})

    error = abs(inferred - truth)
    return DimensionMetrics(
        dimension=name,
        ground_truth=float(truth),
        inferred=float(inferred),
        absolute_error=round(error, 3),
        bias=round(inferred - truth, 3),
        bands={label: error <= threshold for label, threshold in tolerances},
    )


# ── One patient ──────────────────────────────


@dataclass
class PatientMetrics:
    patient_id: str
    dimensions: List[DimensionMetrics]

    # PORTADO
    mae: Optional[float]
    median_ae: Optional[float]
    mean_bias: Optional[float]
    exact_matches: int
    band_counts: Dict[str, int]

    # NUEVO
    scored: int
    na: int
    within_patient_r: Optional[float]

    # 4.4
    @property
    def coverage_rate(self) -> float:
        """An NA is reported, never silently dropped."""
        total = self.scored + self.na
        return round(self.scored / total, 3) if total else 0.0


def evaluate_patient(report, truth: Dict[str, Any]) -> PatientMetrics:
    """One report against one patient's belief_profile."""
    dimensions = [
        _dimension_metrics(name, (truth.get("b_ipq") or {}).get(name),
                           _reported_score(report.bipq, name), BIPQ_TOLERANCES)
        for name in BIPQ_DIMENSIONS
    ] + [
        _dimension_metrics(name, (truth.get("bmq") or {}).get(name),
                           _reported_score(report.bmq, name), BMQ_TOLERANCES)
        for name in BMQ_SUBSCALES
    ]

    scored = [d for d in dimensions if d.scored]
    band_counts = {
        label: sum(1 for d in scored if d.bands.get(label))
        for label, _ in BIPQ_TOLERANCES + BMQ_TOLERANCES
    }

    return PatientMetrics(
        patient_id=report.patient_id,
        dimensions=dimensions,
        mae=_mean(d.absolute_error for d in scored),
        median_ae=_median([d.absolute_error for d in scored]),
        mean_bias=_mean(d.bias for d in scored),
        exact_matches=sum(1 for d in scored if d.absolute_error == 0),
        band_counts=band_counts,
        scored=len(scored),
        na=len(dimensions) - len(scored),
        # the ported correlation: is this person's profile the right shape?
        within_patient_r=_pearson([d.ground_truth for d in scored],
                                  [d.inferred for d in scored]),
    )


def _reported_score(scored: Dict[str, Any], name: str) -> Optional[float]:
    dimension = scored.get(name)
    return dimension.score if dimension is not None else None


# ── NUEVO: the whole batch ───────────────────


@dataclass
class DimensionSummary:
    """One dimension across the patients — what 4.5 asks for."""

    dimension: str
    mae: Optional[float]
    bias: Optional[float]
    scored: int
    na: int
    between_patient_r: Optional[float]

    @property
    def coverage_rate(self) -> float:
        total = self.scored + self.na
        return round(self.scored / total, 3) if total else 0.0


@dataclass
class BatchMetrics:
    patients: List[PatientMetrics]
    by_dimension: Dict[str, DimensionSummary]
    mae: Optional[float]
    coverage_rate: float
    between_patient_r: Optional[float]


# 4.5
def evaluate_batch(pairs: Sequence[Tuple[Any, Dict[str, Any]]]) -> BatchMetrics:
    """Every (report, belief_profile) of a batch, aggregated per dimension."""
    patients = [evaluate_patient(report, truth) for report, truth in pairs]

    by_dimension = {}
    for name in list(BIPQ_DIMENSIONS) + list(BMQ_SUBSCALES):
        entries = [d for p in patients for d in p.dimensions if d.dimension == name]
        scored = [d for d in entries if d.scored]
        by_dimension[name] = DimensionSummary(
            dimension=name,
            mae=_mean(d.absolute_error for d in scored),
            bias=_mean(d.bias for d in scored),
            scored=len(scored),
            na=len(entries) - len(scored),
            # across patients, on this one dimension: does it rank them right?
            between_patient_r=_between_patients(
                _per_patient_pairs(patients, dimension=name)
            ),
        )

    all_scored = [d for p in patients for d in p.dimensions if d.scored]
    total = sum(len(p.dimensions) for p in patients)

    return BatchMetrics(
        patients=patients,
        by_dimension=by_dimension,
        mae=_mean(d.absolute_error for d in all_scored),
        coverage_rate=round(len(all_scored) / total, 3) if total else 0.0,
        # 2.5 — on the patient means: a scorer that gives everyone the same
        # profile lands near zero here however good its MAE
        between_patient_r=_between_patients(_per_patient_pairs(patients)),
    )


# ── 2.5: one point per person, not per report (D12) ──


def _per_patient_pairs(
    patients: Sequence[PatientMetrics], dimension: Optional[str] = None
) -> List[Tuple[float, float]]:
    """One (truth, inferred) per patient, averaging that patient's repeats.

    A batch of 10 × 5 holds fifty PatientMetrics and ten people. Correlating the
    reports counts each person five times and reads their repeat-to-repeat noise
    as agreement between patients, which is the opposite of what 2.5 asks.
    """
    by_patient: Dict[str, List[DimensionMetrics]] = {}
    for patient in patients:
        entries = [
            d for d in patient.dimensions
            if d.scored and (dimension is None or d.dimension == dimension)
        ]
        by_patient.setdefault(patient.patient_id, []).extend(entries)

    pairs = []
    for _, entries in sorted(by_patient.items()):
        truth = _mean(d.ground_truth for d in entries)
        inferred = _mean(d.inferred for d in entries)
        if truth is not None and inferred is not None:
            pairs.append((truth, inferred))
    return pairs


def _between_patients(pairs: Sequence[Tuple[float, float]]) -> Optional[float]:
    """None below MIN_PATIENTS: two people always correlate at ±1."""
    if len(pairs) < MIN_PATIENTS:
        return None
    return _pearson([t for t, _ in pairs], [i for _, i in pairs])


# ── Arithmetic ───────────────────────────────


def _mean(values) -> Optional[float]:
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 3) if values else None


def _median(values: List[float]) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return round(ordered[middle], 3)
    return round((ordered[middle - 1] + ordered[middle]) / 2, 3)

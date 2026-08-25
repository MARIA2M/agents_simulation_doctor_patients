# ahead_agent/causes/similarity.py
# ─────────────────────────────────────────────
# PORTADO from the Python arm. Cosine, matrix, greedy matching and metrics.
# The only change: with no data it returns None, not 0.0.
# ─────────────────────────────────────────────

from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

from .types import CauseMatch, ClassifiedCause

# PORTADO as-is, and **never justified in the original**. It decides what counts
# as a hit, so it moves `coverage_score` directly. It travels in the result
# (`CausesScore.threshold`) so a number can be read knowing which threshold
# produced it, and so it can be swept when needed.
MATCH_THRESHOLD = 0.72   # cosine at which a pairing counts as a hit


# ── Comparing two vectors ────────────────────


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """How closely two embeddings point the same way. 0.0 if either has no length."""
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm > 0 else 0.0


def build_sim_matrix(
    ground_truth: Sequence[Sequence[float]], inferred: Sequence[Sequence[float]]
) -> List[List[float]]:
    """Every true cause against every inferred one, as rows × columns."""
    return [[cosine_similarity(g, i) for i in inferred] for g in ground_truth]


# ── Pairing them up ──────────────────────────


def greedy_match(
    ground_truth: List[ClassifiedCause],
    inferred: List[ClassifiedCause],
    sim_matrix: List[List[float]],
    threshold: float = MATCH_THRESHOLD,
) -> Tuple[List[CauseMatch], List[ClassifiedCause]]:
    """Each true cause, in order of importance, takes the closest free inferred one."""
    used = set()
    matches: List[CauseMatch] = []

    for row, truth in enumerate(ground_truth):
        best, best_similarity = -1, -1.0
        for column in range(len(inferred)):
            if column not in used and sim_matrix[row][column] > best_similarity:
                best, best_similarity = column, sim_matrix[row][column]

        if best < 0:
            matches.append(CauseMatch(truth, None, 0.0, False))
            continue

        used.add(best)
        matches.append(
            CauseMatch(
                ground_truth=truth,
                inferred=inferred[best],
                similarity=round(best_similarity, 3),
                matched=best_similarity >= threshold,
            )
        )

    return matches, [c for j, c in enumerate(inferred) if j not in used]


# ── What the pairing scored ──────────────────


def coverage_score(matches: List[CauseMatch]) -> Optional[float]:
    """How many of the true causes were found. None, not 0.0, when there are none."""
    return round(sum(1 for m in matches if m.matched) / len(matches), 3) if matches else None


def mean_similarity(matches: List[CauseMatch]) -> Optional[float]:
    """How close the pairings came on average, counting only those that paired."""
    paired = [m for m in matches if m.inferred is not None]
    return round(sum(m.similarity for m in paired) / len(paired), 3) if paired else None

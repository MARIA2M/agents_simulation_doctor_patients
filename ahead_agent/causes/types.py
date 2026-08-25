# ahead_agent/causes/types.py
# ─────────────────────────────────────────────
# What the causes pipeline passes around. PORTADO, with two NUEVO fields.
# ─────────────────────────────────────────────

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

# PORTADO — the seven buckets a cause can fall into. `unknown` is a real one:
# a patient saying they do not know is a finding, not a failure.
CAUSE_CATEGORIES = (
    "biological",
    "behavioural",
    "psychological",
    "social",
    "medical",
    "chance",
    "unknown",
)


# ── One cause ────────────────────────────────


@dataclass
class ClassifiedCause:
    """A cause as it was written, and the bucket it was sorted into."""

    text: str
    # None when the classifier's reply could not be read. The old module
    # returned "unknown", which is a real category, so a parsing failure ended
    # up counting as "the patient does not know" (4.4).
    category: Optional[str]


# ── One pairing ──────────────────────────────


@dataclass
class CauseMatch:
    """One true cause set against the inferred cause that came closest."""

    ground_truth: ClassifiedCause
    inferred: Optional[ClassifiedCause]   # None = no inferred cause was free
    similarity: float                     # cosine 0–1
    matched: bool                         # similarity >= the threshold


# ── The whole result ─────────────────────────


@dataclass
class CausesScore:
    """Everything one report's causes produced, and how it was measured."""

    inferred_causes: List[ClassifiedCause]
    category_diversity: Optional[float]

    ground_truth_causes: List[ClassifiedCause] = field(default_factory=list)
    matches: List[CauseMatch] = field(default_factory=list)
    coverage_score: Optional[float] = None
    mean_similarity: Optional[float] = None
    unmatched_inferred: List[ClassifiedCause] = field(default_factory=list)

    # `coverage_score` can be computed by semantic similarity or by
    # category overlap — two different metrics under one name. The old module
    # switched between them silently when embeddings failed, so a batch's
    # number could be half one and half the other.
    method: Optional[str] = None          # "embeddings" | "categories"
    threshold: Optional[float] = None     # the threshold that decided the matches
    events: List[dict] = field(default_factory=list)

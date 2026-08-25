# ahead_agent/causes/scorer.py
# PORTADO from the Python arm: classify, match by similarity, score.
#
# NUEVO: the method used is recorded in the result. The original fell back from
# semantic similarity to category overlap when embeddings failed, printed a
# warning and returned the number in the same field — so one batch could carry
# `coverage_score` computed two different ways with nothing to say so (4.3, 4.4).

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from .. import llm
from .embeddings import EmbeddingError, embedding_model_available, get_embeddings
from .similarity import (
    MATCH_THRESHOLD,
    build_sim_matrix,
    coverage_score,
    greedy_match,
    mean_similarity,
)
from .taxonomy import build_classify_prompt, parse_category
from .types import CAUSE_CATEGORIES, CausesScore, ClassifiedCause


# ── Scoring one report's causes ──────────────


def score_causes(
    config: Dict[str, Any],
    inferred_raw: Sequence[Optional[str]],
    ground_truth: Optional[Sequence[str]] = None,
    threshold: float = MATCH_THRESHOLD,
) -> CausesScore:
    """A report's causes against the profile's, saying in `method` how it scored them."""
    events: List[dict] = []
    inferred = _classify_all(config, inferred_raw, events)

    score = CausesScore(
        inferred_causes=inferred,
        category_diversity=_category_diversity(inferred),
        threshold=threshold,
        events=events,
    )

    if not ground_truth:
        return score

    score.ground_truth_causes = _classify_all(config, ground_truth, events)

    if not embedding_model_available(config):
        events.append({"event": "embeddings_unavailable", "model": config["models"]["embed"]})
        return _by_categories(score)

    try:
        return _by_embeddings(config, score, threshold)
    except EmbeddingError as error:
        events.append({"event": "embeddings_failed", "detail": str(error)})
        return _by_categories(score)


# ── The two methods, each one naming itself ──

def _by_embeddings(config, score: CausesScore, threshold: float) -> CausesScore:
    """Semantic similarity: the real measure, when the embed model is there."""
    truth_vectors = get_embeddings(config, [c.text for c in score.ground_truth_causes])
    inferred_vectors = get_embeddings(config, [c.text for c in score.inferred_causes])

    matches, unmatched = greedy_match(
        score.ground_truth_causes,
        score.inferred_causes,
        build_sim_matrix(truth_vectors, inferred_vectors),
        threshold,
    )

    score.matches = matches
    score.unmatched_inferred = unmatched
    score.coverage_score = coverage_score(matches)
    score.mean_similarity = mean_similarity(matches)
    score.method = "embeddings"
    return score


def _by_categories(score: CausesScore) -> CausesScore:
    """Far coarser: landing in the same one of seven categories counts as a hit."""
    truth = {c.category for c in score.ground_truth_causes if c.category}
    inferred = {c.category for c in score.inferred_causes if c.category}

    score.coverage_score = round(len(truth & inferred) / len(truth), 3) if truth else None
    score.mean_similarity = None
    score.method = "categories"
    return score


# ── Classification ───────────────────────────

def _classify_all(config, causes: Sequence[Optional[str]], events: List[dict]) -> List[ClassifiedCause]:
    """Every non-empty cause, sorted into a category. Blanks are dropped first."""
    return [_classify(config, cause, events) for cause in causes if cause and cause.strip()]


def _classify(config, cause: str, events: List[dict]) -> ClassifiedCause:
    """At temperature 0 on the doctor's model, through llm.chat so it retries (3.1)."""
    reply = llm.chat(
        config,
        "report",
        [{"role": "user", "content": build_classify_prompt(cause)}],
        events=events,
    )
    category = parse_category(reply.get("content") or "")

    if category is None:
        events.append({"event": "cause_unclassified", "cause": cause})

    return ClassifiedCause(text=cause.strip(), category=category)


def _category_diversity(causes: List[ClassifiedCause]) -> Optional[float]:
    """How much of the taxonomy the causes span. None when none could be read."""
    classified = [c for c in causes if c.category]
    if not classified:
        return None
    return round(len({c.category for c in classified}) / len(CAUSE_CATEGORIES), 3)

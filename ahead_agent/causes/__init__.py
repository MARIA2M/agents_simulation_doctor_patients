# ahead_agent/causes/
# ─────────────────────────────────────────────
# PORTADO from the Python arm (4.3). Causes are open text, so they stay out of
# the MAE: they are scored by semantic similarity against the profile.
# ─────────────────────────────────────────────

from .scorer import score_causes
from .similarity import MATCH_THRESHOLD, cosine_similarity
from .types import CAUSE_CATEGORIES, CauseMatch, CausesScore, ClassifiedCause

__all__ = [
    "score_causes",
    "MATCH_THRESHOLD",
    "cosine_similarity",
    "CAUSE_CATEGORIES",
    "CauseMatch",
    "CausesScore",
    "ClassifiedCause",
]

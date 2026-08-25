# ahead_agent/causes/taxonomy.py
# ─────────────────────────────────────────────
# PORTADO from the Python arm. The seven categories, and the prompt that sorts
# a cause into one of them.
# ─────────────────────────────────────────────

from __future__ import annotations

from typing import Optional

from .types import CAUSE_CATEGORIES

# what each category covers, as the classifier reads it
DESCRIPTIONS = {
    "biological": "Genetic predisposition, immune system failure, inherited traits, viral or bacterial infection",
    "behavioural": "Lifestyle choices, sexual behaviour, substance use, diet, risk-taking, not using protection",
    "psychological": "Chronic stress, anxiety, mental health, emotional trauma, grief",
    "social": "Relationships, workplace conditions, socioeconomic factors, exposure through others",
    "medical": "Previous medical treatment, healthcare failure, iatrogenic causes, delayed diagnosis",
    "chance": "Chance, bad luck, 'it only takes once', no specific identifiable cause",
    "unknown": "Patient does not know, cause unclear or unspecified",
}


# ── Asking the model ─────────────────────────


def build_classify_prompt(cause: str) -> str:
    """The classification prompt for one cause, with every category spelled out."""
    lines = "\n".join(f"- {key}: {DESCRIPTIONS[key]}" for key in CAUSE_CATEGORIES)
    return (
        "Classify the following reported cause of a chronic illness into exactly "
        f'one category.\n\nCause: "{cause}"\n\nCategories:\n{lines}\n\n'
        "Respond ONLY with one word — the category key. Do not add any explanation."
    )


# ── Reading the answer ───────────────────────


def parse_category(raw: str) -> Optional[str]:
    """The category, or None when the reply cannot be read."""
    cleaned = raw.strip().lower().replace("-", "").replace(" ", "")
    if cleaned in CAUSE_CATEGORIES:
        return cleaned

    # PORTADO: a small model sometimes answers "biological." or "Category:
    # social", so one category contained in the reply is accepted.
    found = [key for key in CAUSE_CATEGORIES if key in cleaned]
    return found[0] if len(found) == 1 else None

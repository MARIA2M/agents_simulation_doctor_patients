# corpus.py
# ─────────────────────────────────────────────
# Reading patients/*.json (0.6). One loader, because the scale is applied on the
# way in and three entry points reading the corpus their own way would drift.
#
# The BMQ is stored as CK wrote it — a raw sum over the subscale maximum, as a
# string because "21/25" is not a JSON number. The denominator is the item
# count, since each item scores 1-5, so the file keeps what the file said and
# the 1-5 scale the bands and the evaluation use is derived here.
# ─────────────────────────────────────────────

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

BMQ_MAXIMUM = {"specific_necessity": 25, "specific_concerns": 25,
               "general_harm": 20, "general_overuse": 20}


def bmq_mean(raw: str, subscale: str) -> float:
    """'21/25' -> 4.2. A denominator this subscale does not use is refused."""
    numerator, maximum = (int(part) for part in raw.split("/"))
    if maximum != BMQ_MAXIMUM[subscale]:
        raise ValueError(
            f"{subscale} = {raw}: maximum {maximum}, expected {BMQ_MAXIMUM[subscale]}"
        )
    return round(numerator / (maximum / 5), 2)


def normalize_beliefs(profile: Dict[str, Any]) -> Dict[str, Any]:
    """The scale is applied here, not on disk. Already-numeric values pass
    through, so the frozen version1 corpus still loads."""
    bmq = profile.get("belief_profile", {}).get("bmq") or {}
    for subscale, raw in bmq.items():
        if isinstance(raw, str):
            bmq[subscale] = bmq_mean(raw, subscale)
    return profile


def load_patient(path: Path | str) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Patient profile not found: {path}")
    return normalize_beliefs(json.loads(p.read_text()))


def load_patients(paths: Iterable[Path | str]) -> List[Dict[str, Any]]:
    """In the order given, so two batches line up."""
    return [load_patient(p) for p in paths]


def load_corpus(patients_dir: Path | str) -> Dict[str, Dict[str, Any]]:
    """patient_id → profile, for everything that wants the whole corpus."""
    return {profile["patient_id"]: profile
            for profile in load_patients(sorted(Path(patients_dir).glob("*.json")))}

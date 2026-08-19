# ahead_agent/config.py
# ─────────────────────────────────────────────
# Run profiles (§6) and the dimension schema.
#
# A profile is a file, not a code branch: config/local.yaml for smoke runs,
# config/hpc.yaml for batches. Same code either way — what changes is the
# models, the scale and the machine.
#
# What is deliberately NOT here: the questionnaire. The old config carried
# the B-IPQ and BMQ item wording, and the graph walked that list — that is
# elicitation, and it is the paradigm being replaced. What survives are the
# dimension ids, because they are the schema of the report, not a script:
# report.py validates against them, coverage.py builds its map from them and
# evaluation.py keys its ground truth by them.
# ─────────────────────────────────────────────

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

import yaml

PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parent
PROFILES_DIR = REPO_ROOT / "config"

# Empty until load_config() runs. There are no module-level constants derived
# from it on purpose: they would be evaluated at import time, before --profile
# has chosen anything, and would silently freeze another profile's values.
CONFIG: Dict[str, Any] = {}

# Settings whose absence would change results silently. A profile missing any
# of these is rejected rather than defaulted: a server applying its own
# temperature is the known way to compare two runs that were never comparable
# (§12).
REQUIRED_KEYS = (
    "profile",
    "models.doctor",
    "models.patient",
    "models.embed",
    "sampling.temperature",
    "server.ollama_url",
)

# ── Dimension schema ─────────────────────────
# Ids only, matching the keys of belief_profile in patients/*.json. If these
# drift apart, the ground truth of 4.1 stops lining up with the report.

BIPQ_DIMENSIONS: List[str] = [
    "consequences",
    "timeline",
    "personal_control",
    "treatment_control",
    "identity",
    "concern",
    "coherence",
    "emotional_response",
]

BMQ_SUBSCALES: List[str] = [
    "specific_necessity",
    "specific_concerns",
    "general_harm",
    "general_overuse",
]

# `causes` is scored, but not on a scale: it is open-ended, matched by
# semantic similarity and kept out of the MAE (4.3). Listing it alongside the
# numeric dimensions is what would make evaluation.py try to average it.
CAUSES_DIMENSION = "causes"


# ── Loading ──────────────────────────────────


def load_config(profile: str = "local") -> Dict[str, Any]:
    """Read config/<profile>.yaml, validate it and fill CONFIG in place.

    CONFIG is mutated rather than rebound so that modules which imported it
    at start-up see the loaded values.
    """
    path = profile_path(profile)
    if not path.exists():
        raise FileNotFoundError(f"Run profile not found: {path}")

    with open(path) as f:
        data = yaml.safe_load(f) or {}

    _validate(data, path)

    # The endpoint may be redirected per machine — an Ollama on a compute node
    # answers on a different host than the one on a laptop. Everything else
    # comes from the profile so that it stays reproducible from the file alone.
    if os.getenv("OLLAMA_URL"):
        data["server"]["ollama_url"] = os.environ["OLLAMA_URL"]

    CONFIG.clear()
    CONFIG.update(data)
    return CONFIG


def profile_path(profile: str) -> Path:
    """Accept either a profile name (`hpc`) or a path to a YAML file."""
    if profile.endswith((".yaml", ".yml")):
        return Path(profile)
    return PROFILES_DIR / f"{profile}.yaml"


def path_for(key: str) -> Path:
    """Resolve one of the `paths:` entries against the repository root."""
    return REPO_ROOT / CONFIG["paths"][key]


# ── Validation ───────────────────────────────


def _validate(data: Dict[str, Any], path: Path) -> None:
    missing = [key for key in REQUIRED_KEYS if _lookup(data, key) is None]
    if missing:
        raise KeyError(f"{path.name} is missing required settings: {', '.join(missing)}")

    # The profile name is copied verbatim into run_meta (0.4). If the file
    # disagrees with its own name, every run it produces is mislabelled.
    declared = data["profile"]
    if path.stem != declared:
        raise ValueError(
            f"{path.name} declares profile {declared!r}, which does not match its filename"
        )


def _lookup(data: Dict[str, Any], dotted: str) -> Any:
    value: Any = data
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value

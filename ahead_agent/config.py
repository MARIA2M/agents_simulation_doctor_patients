# ahead_agent/config.py
# ─────────────────────────────────────────────
# Run profiles and the dimension schema.
# ─────────────────────────────────────────────

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

import yaml

PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parent
PROFILES_DIR = REPO_ROOT / "config"

# Empty until load_config() runs.
CONFIG: Dict[str, Any] = {}

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
# semantic similarity and kept out of the MAE (4.3)
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
    """A profile missing any of these is rejected rather than defaulted."""
    models = data.get("models") or {}
    sampling = data.get("sampling") or {}
    server = data.get("server") or {}
    limits = data.get("limits") or {}
    paths = data.get("paths") or {}

    missing = []
    if not data.get("profile"):
        missing.append("profile")
    if not models.get("doctor"):
        missing.append("models.doctor")
    if not models.get("patient"):
        missing.append("models.patient")
    if not models.get("embed"):
        missing.append("models.embed")
    if sampling.get("temperature") is None:   # 0.0 is a valid temperature
        missing.append("sampling.temperature")
    if not server.get("ollama_url"):
        missing.append("server.ollama_url")
    # max_turns is the only thing that stops a doctor who never closes the
    # consultation (1.5); a default here would be a silent infinite loop.
    if limits.get("max_turns") is None:
        missing.append("limits.max_turns")
    if limits.get("report_retries") is None:
        missing.append("limits.report_retries")
    # Validated here rather than where path_for() uses them, which would raise
    # a bare KeyError far from the profile that caused it.
    for key in ("patients", "runs"):
        if not paths.get(key):
            missing.append(f"paths.{key}")

    if missing:
        raise KeyError(f"{path.name} is missing required settings: {', '.join(missing)}")

    # The profile name is copied verbatim into run_meta (0.4). If the file
    # disagrees with its own name, every run it produces is mislabelled.
    declared = data["profile"]
    if path.stem != declared:
        raise ValueError(
            f"{path.name} declares profile {declared!r}, which does not match its filename"
        )

# ahead_agent/config.py
# ─────────────────────────────────────────────
# Run profiles (config/*.yaml) and the names of the scored dimensions.
# ─────────────────────────────────────────────

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

import yaml

PACKAGE_ROOT = Path(__file__).resolve().parent   # ahead_agent/
REPO_ROOT = PACKAGE_ROOT.parent                  # the repo
RUN_PROFILES_DIR = REPO_ROOT / "config"          # config/*.yaml


# ── Dimensions ───────────────────────────────

# the eight illness beliefs
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

# the four treatment beliefs
BMQ_SUBSCALES: List[str] = [
    "specific_necessity",
    "specific_concerns",
    "general_harm",
    "general_overuse",
]

CAUSES_DIMENSION = "causes"   # open-ended, not scored (4.3)


# ── Conversation Features (§4.1) ──────────────────────

COVERAGE_MODES = ("off", "show")   


def coverage_mode(config: Dict[str, Any]) -> str:
    return (config.get("features") or {}).get("coverage_hint", "off")


def takes_notes(config: Dict[str, Any]) -> bool:
    return (config.get("features") or {}).get("working_notes", False)


# ── Loading ──────────────────────────────────

# every profile must set these (§12)
REQUIRED = {
    "models": ("doctor", "patient", "embed"),
    "sampling": (
        "doctor_temperature",
        "patient_temperature",
        "report_temperature",
        "context_length",
    ),
    "server": ("ollama_url", "request_timeout", "keep_alive"),
    "limits": ("max_turns", "report_attempts"),      # 1.5
    "features": ("coverage_hint", "working_notes"),  # §4.1
    "paths": ("patients", "runs"),
}


def load_config(profile: str = "local") -> Dict[str, Any]:
    """Read a run profile with whatever it extends, and resolve its paths."""
    path = _profile_path(profile)
    if not path.exists():
        raise FileNotFoundError(f"Run profile not found: {path}")

    data = _inherited(path, [])
    _validate_yaml(data, path)

    # 0.4 — the address belongs to the machine, not to the profile
    if os.getenv("OLLAMA_URL"):
        data["server"]["ollama_url"] = os.environ["OLLAMA_URL"]

    data["paths"] = {key: REPO_ROOT / value for key, value in data["paths"].items()}

    return data


# ── Inheritance (0.5) ────────────────────────

# What a profile declares to inherit from. Explicit rather than an implicit
# base underneath everything: a profile with no `extends` loads on its own,
# which is what lets a test leave a key out and see it rejected.
INHERITS_KEY = "extends"


def _inherited(path: Path, seen: List[Path]) -> Dict[str, Any]:
    """A profile merged over what it extends, block by block, child last.

    Not a shallow update: `models: {doctor: …}` in a profile must complete the
    inherited block, not replace it and lose `embed`.
    """
    resolved = path.resolve()
    if resolved in seen:
        chain = " → ".join(p.name for p in seen + [resolved])
        raise ValueError(f"Run profiles inherit in a cycle: {chain}")

    with open(path) as f:
        data = yaml.safe_load(f) or {}

    parent = data.get(INHERITS_KEY)
    if parent is None:
        return data

    parent_path = _parent_path(str(parent), path)
    if not parent_path.exists():
        raise FileNotFoundError(
            f"{path.name} extends '{parent}', which is not at {parent_path}"
        )

    merged = _inherited(parent_path, seen + [resolved])
    for block, value in data.items():
        if isinstance(value, dict) and isinstance(merged.get(block), dict):
            merged[block] = {**merged[block], **value}
        else:
            merged[block] = value
    return merged


def _parent_path(parent: str, child: Path) -> Path:
    """A name resolves next to the child first, then in config/; a path as given."""
    if parent.endswith((".yaml", ".yml")):
        candidate = Path(parent)
        return candidate if candidate.is_absolute() else child.parent / candidate

    sibling = child.parent / f"{parent}.yaml"
    return sibling if sibling.exists() else RUN_PROFILES_DIR / f"{parent}.yaml"


def _profile_path(profile: str) -> Path:
    """Accept either a profile name (`hpc`) or a path to a YAML file."""
    if profile.endswith((".yaml", ".yml")):
        return Path(profile)
    return RUN_PROFILES_DIR / f"{profile}.yaml"


# ── Validation ───────────────────────────────


def _validate_yaml(data: Dict[str, Any], path: Path) -> None:
    """Reject a profile with settings missing."""
    missing = []
    for block, keys in REQUIRED.items():
        for key in keys:
            # against None, not falsy: 0.0 is a temperature
            if (data.get(block) or {}).get(key) is None:
                missing.append(f"{block}.{key}")

    if missing:
        raise KeyError(f"{path.name} is missing: {', '.join(missing)}")

    if data.get("profile") != path.stem:
        raise ValueError(f"{path.name} must declare `profile: {path.stem}`")

    mode = coverage_mode(data)
    if mode not in COVERAGE_MODES:
        raise ValueError(
            f"{path.name}: features.coverage_hint is {mode!r}, not one of "
            f"{', '.join(COVERAGE_MODES)}. Quote it — bare `off` is a YAML boolean."
        )

    notes = (data.get("features") or {}).get("working_notes")
    if not isinstance(notes, bool):
        raise ValueError(
            f"{path.name}: features.working_notes is {notes!r}, not true or false. "
            f"Do not quote it — every non-empty string is true."
        )

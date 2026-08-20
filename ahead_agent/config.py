# ahead_agent/config.py
# Run profiles (config/*.yaml) and the names of the scored dimensions.

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

import yaml

PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parent
RUN_PROFILES_DIR = REPO_ROOT / "config"

# Same names as the keys of belief_profile in patients/*.json.
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

# Open-ended and matched by similarity, so it is kept out of the MAE (4.3).
CAUSES_DIMENSION = "causes"


# Leaving any of these out means the server decides it instead (§12).
REQUIRED = {
    "models": ("doctor", "patient", "embed"),
    "sampling": (
        "doctor_temperature",
        "patient_temperature",
        "report_temperature",
        "context_length",
    ),
    "server": ("ollama_url", "request_timeout", "keep_alive"),
    # Without max_turns nothing stops a doctor who never closes (1.5).
    "limits": ("max_turns", "report_retries"),
    "paths": ("patients", "runs"),
}


def load_config(profile: str = "local") -> Dict[str, Any]:
    """Read config/<profile>.yaml and return it."""
    path = profile_path(profile)
    if not path.exists():
        raise FileNotFoundError(f"Run profile not found: {path}")
    
    with open(path) as f:
        data = yaml.safe_load(f) or {}

    _validate_yaml(data, path)

    # 
    if os.getenv("OLLAMA_URL"):
        data["server"]["ollama_url"] = os.environ["OLLAMA_URL"]

    # Relative paths
    data["paths"] = {key: REPO_ROOT / value for key, value in data["paths"].items()}

    return data


def profile_path(profile: str) -> Path:
    """Accept either a profile name (`hpc`) or a path to a YAML file."""
    if profile.endswith((".yaml", ".yml")):
        return Path(profile)
    return RUN_PROFILES_DIR / f"{profile}.yaml"


def _validate_yaml(data: Dict[str, Any], path: Path) -> None:
    """Reject a profile with settings missing."""
    missing = []
    for block, keys in REQUIRED.items():
        for key in keys:
            # Against None, not falsy: 0.0 is a temperature.
            if (data.get(block) or {}).get(key) is None:
                missing.append(f"{block}.{key}")

    if missing:
        raise KeyError(f"{path.name} is missing: {', '.join(missing)}")

    # The name is stored in the run metadata; a mismatch mislabels every run.
    if data.get("profile") != path.stem:
        raise ValueError(f"{path.name} must declare `profile: {path.stem}`")

# ahead_agent/config.py
# Run profiles (config/*.yaml) and the names of the scored dimensions.

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

# The doctor asks and infers the scores; writing the report is a separate step.
SAMPLING_ROLES = ("doctor", "patient", "report")


def load_config(profile: str = "local") -> Dict[str, Any]:
    """Read config/<profile>.yaml and fill CONFIG with it."""
    path = profile_path(profile)
    if not path.exists():
        raise FileNotFoundError(f"Run profile not found: {path}")

    with open(path) as f:
        data = yaml.safe_load(f) or {}

    _validate(data, path)

    # Only the address moves between machines; the rest comes from the file.
    if os.getenv("OLLAMA_URL"):
        data["server"]["ollama_url"] = os.environ["OLLAMA_URL"]

    # Filled rather than replaced, so `from .config import CONFIG` still works.
    CONFIG.clear()
    CONFIG.update(data)
    return CONFIG


def profile_path(profile: str) -> Path:
    """Accept either a profile name (`hpc`) or a path to a YAML file."""
    if profile.endswith((".yaml", ".yml")):
        return Path(profile)
    return PROFILES_DIR / f"{profile}.yaml"


def path_for(key: str) -> Path:
    """Turn one of the `paths:` entries into a full path."""
    return REPO_ROOT / CONFIG["paths"][key]


def _validate(data: Dict[str, Any], path: Path) -> None:
    """Reject a profile that would leave a setting up to the server (§12)."""
    models = data.get("models") or {}
    sampling = data.get("sampling") or {}
    server = data.get("server") or {}
    limits = data.get("limits") or {}
    paths = data.get("paths") or {}

    required = {
        "profile": data.get("profile"),
        "models.doctor": models.get("doctor"),
        "models.patient": models.get("patient"),
        "models.embed": models.get("embed"),
        "server.ollama_url": server.get("ollama_url"),
        # Without max_turns nothing stops a doctor who never closes (1.5).
        "limits.max_turns": limits.get("max_turns"),
        "limits.report_retries": limits.get("report_retries"),
        "paths.patients": paths.get("patients"),
        "paths.runs": paths.get("runs"),
    }
    missing = [key for key, value in required.items() if value is None]

    temperatures = sampling.get("temperature")
    if not isinstance(temperatures, dict):
        missing.append("sampling.temperature (one per role)")
    else:
        for role in SAMPLING_ROLES:
            if temperatures.get(role) is None:   # 0.0 is a temperature
                missing.append(f"sampling.temperature.{role}")

    if missing:
        raise KeyError(f"{path.name} is missing required settings: {', '.join(missing)}")

    # The name is stored in the run metadata; a mismatch mislabels every run.
    if path.stem != data["profile"]:
        raise ValueError(
            f"{path.name} declares profile {data['profile']!r}, "
            "which does not match its filename"
        )

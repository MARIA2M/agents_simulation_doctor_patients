# ahead_agent/prompts.py
# Builds a system prompt from files on disk: base role + skills + resources.
# The profile decides what is loaded, not the model (1.6, 1.7).

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .metadata import hash_text

SEPARATOR = "\n\n---\n\n"


def compose(config: Dict[str, Any], role: str) -> str:
    """The whole system prompt for `doctor` or `patient`."""
    parts = [_read(config["paths"]["prompts"] / config["prompts"][role])]

    print(parts)
    parts += [
        _read(config["paths"]["skills"] / f"{name}.md")
        for name in _listed(config, "skills", role)
    ]
    parts += [
        _read(config["paths"]["resources"] / f"{name}.md")
        for name in _listed(config, "resources", role)
    ]
    return SEPARATOR.join(parts)


def hashes(config: Dict[str, Any]) -> Dict[str, Any]:
    """Fingerprints of the composed prompts, for the run metadata (0.4)."""
    return {
        "doctor": hash_text(compose(config, "doctor")),
        "patient": hash_text(compose(config, "patient")),
        "skills": {role: _listed(config, "skills", role) for role in ("doctor", "patient")},
    }


def _listed(config: Dict[str, Any], block: str, role: str) -> list:
    return list((config.get(block) or {}).get(role) or [])


def _read(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text().strip()

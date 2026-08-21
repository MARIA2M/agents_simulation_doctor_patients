# ahead_agent/prompts.py
# ─────────────────────────────────────────────
# Builds a system prompt from files on disk: base role + skills + resources,
# and for the report, the doctor's scoring rubric.
# The profile decides what is loaded, not the model (1.6, 1.7).
# ─────────────────────────────────────────────

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .metadata import hash_text

SEPARATOR = "\n\n---\n\n"


def compose(config: Dict[str, Any], role: str) -> str:
    """The whole prompt for `doctor`, `patient` or `report`."""
    parts = [_read(config["paths"]["prompts"] / config["prompts"][role])]

    # Only the report scores anything, so only the report carries the scale.
    if role == "report":
        parts += [
            render_rubric(_load_json(config["paths"]["prompts"] / name))
            for name in _doctor_rubric(config)
        ]

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
        "report": hash_text(compose(config, "report")),
        # Separately from the report it is part of, so a change of anchors can
        # be told apart from a change of instructions.
        "doctor_rubric": hash_text(
            SEPARATOR.join(
                json.dumps(_load_json(config["paths"]["prompts"] / name), sort_keys=True)
                for name in _doctor_rubric(config)
            )
        ),
        "skills": {role: _listed(config, "skills", role) for role in ("doctor", "patient")},
    }


# ── The doctor's scale ───────────────────────
# Held as JSON, in the same shape as the bands of patient_profile.py, so the
# two ladders can be compared. They must not be each other's inverse: that is
# what would make part of the accuracy a decoding of our own code (5.5).


def render_rubric(rubric: Dict[str, Any]) -> str:
    """One instrument's anchors, as the doctor reads them."""
    low, high = rubric["range"]
    lines = [f"# Scale — {rubric['title']} ({low}–{high})", "", rubric["guidance"], ""]
    lines += [f"- {rule}" for rule in rubric.get("rules", [])]

    for name, dimension in rubric["dimensions"].items():
        lines += [
            "",
            f"## {name} — {dimension['label']}",
            f"*{low} = {dimension['low']} · {high} = {dimension['high']}*",
            "",
        ]
        lines += [f"  - {score} · {text}" for score, text in dimension["anchors"]]
        if dimension.get("note"):
            lines += ["", dimension["note"]]

    for name, text in (rubric.get("unscored") or {}).items():
        lines += ["", f"## {name}", "", f"Not scored. {text}"]

    return "\n".join(lines)


def _doctor_rubric(config: Dict[str, Any]) -> List[str]:
    return list((config.get("prompts") or {}).get("doctor_rubric") or [])


def _listed(config: Dict[str, Any], block: str, role: str) -> list:
    return list((config.get(block) or {}).get(role) or [])


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Rubric file not found: {path}")
    return json.loads(path.read_text())


def _read(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text().strip()

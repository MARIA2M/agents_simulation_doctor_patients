# ahead_agent/prompts.py
# ─────────────────────────────────────────────
# Builds a system prompt from files on disk: base role + skills + resources,
# and for the report, the doctor's scoring rubric.
# The profile decides what is loaded, not the model (1.6, 1.7).
# Also fingerprints all of it for run_meta, tool descriptions included (0.4).
# ─────────────────────────────────────────────

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .metadata import hash_text
from .patient_profile import BIPQ_BANDS, BMQ_BANDS
from .tools import doctor_tools

SEPARATOR = "\n\n---\n\n"   # between fragments


# ── Composing a prompt (1.6, 1.7) ────────────


def compose_prompt(config: Dict[str, Any], role: str) -> str:
    """The whole prompt for `doctor`, `patient` or `report`."""
    prompts_dir = config["paths"]["prompts"]

    role_prompt = _read_prompts(prompts_dir / config["prompts"][role])

    # only the report scores, so only the report carries the scale
    rubrics = [
        _rubric_as_markdown(json.loads(_read_prompts(prompts_dir / name)))
        for name in _listed_files(config, "prompts", "doctor_rubric")
    ] if role == "report" else []

    skills = [
        _read_prompts(config["paths"]["skills"] / f"{name}.md")
        for name in _listed_files(config, "skills", role)
    ]

    resources = [
        _read_prompts(config["paths"]["resources"] / f"{name}.md")
        for name in _listed_files(config, "resources", role)
    ]

    return SEPARATOR.join([role_prompt, *rubrics, *skills, *resources])


# ── Fingerprints (0.4) ───────────────────────


def hashes(config: Dict[str, Any]) -> Dict[str, Any]:
    """Fingerprints of the composed prompts, for the run metadata."""
    rubric_files = _listed_files(config, "prompts", "doctor_rubric")

    return {
        "doctor": hash_text(compose_prompt(config, "doctor")),
        "patient": hash_text(compose_prompt(config, "patient")),
        "report": hash_text(compose_prompt(config, "report")),
        # apart from the report, so moving an anchor is not read as a
        # change of instructions
        "doctor_rubric": hash_text(
            SEPARATOR.join(
                json.dumps(
                    json.loads(_read_prompts(config["paths"]["prompts"] / name)), sort_keys=True
                )
                for name in rubric_files
            )
        ),
        # the tool descriptions are instructions too, and the arms change them
        "tools": hash_text(json.dumps(doctor_tools(config), sort_keys=True)),
        # reaches the patient through describe_patient, not through PATIENT.md
        "patient_bands": hash_text(json.dumps([BIPQ_BANDS, BMQ_BANDS], sort_keys=True)),
        "skills": {role: _listed_files(config, "skills", role) for role in ("doctor", "patient")},
    }


# ── The doctor's scale (2.2, 5.5) ────────────

#     # Scale — beliefs about the illness (0–10)
#
#     Score what this person's life shows, not how they phrased it.
#
#     - Where words and conduct disagree, weigh the conduct.
RUBRIC_HEADER = """# Scale — {title} ({low}–{high})

{guidance}

{rules}"""

#     ## consequences — impact on their life
#     *0 = no effect at all · 10 = depends on others for daily functioning*
#
#       - 2 · Keeps every usual role and activity, with no adaptation.
#       - 8 · A major role is lost or substantially reduced.
#
#     Not the words they use.
RUBRIC_DIMENSION = """## {name} — {label}
*{low} = {low_text} · {high} = {high_text}*

{anchors}{note}"""

#     ## causes
#
#     Not scored. Record what they believe caused it, in their own terms.
RUBRIC_UNSCORED = """## {name}

Not scored. {text}"""


def _rubric_as_markdown(rubric: Dict[str, Any]) -> str:
    """One instrument's anchors, as the doctor reads them."""
    low, high = rubric["range"]

    blocks = [
        RUBRIC_HEADER.format(
            title=rubric["title"],
            low=low,
            high=high,
            guidance=rubric["guidance"],
            rules="\n".join(f"- {rule}" for rule in rubric.get("rules", [])),
        )
    ]

    for name, dimension in rubric["dimensions"].items():
        note = dimension.get("note")
        blocks.append(
            RUBRIC_DIMENSION.format(
                name=name,
                label=dimension["label"],
                low=low,
                high=high,
                low_text=dimension["low"],
                high_text=dimension["high"],
                anchors="\n".join(f"  - {score} · {text}" for score, text in dimension["anchors"]),
                note=f"\n\n{note}" if note else "",
            )
        )

    for name, text in (rubric.get("unscored") or {}).items():
        blocks.append(RUBRIC_UNSCORED.format(name=name, text=text))

    return "\n\n".join(blocks)


# ── Reading from disk ────────────────────────


def _listed_files(config: Dict[str, Any], block: str, role: str) -> list:
    """The file names the profile lists under `block` for this role."""
    return list((config.get(block) or {}).get(role) or [])


def _read_prompts(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text().strip()

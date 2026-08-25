# tests/conftest.py
# What the suite shares: the test patient, the builders for model replies, and
# the run profiles.
#
# It lives here rather than in a test file because it used to live there:
# `test_nodes` exported to three others and `test_coverage` to a fourth, so
# touching `PATIENT` broke files that never mentioned it.

import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from ahead_agent import nodes  # noqa: E402
from ahead_agent.config import load_config  # noqa: E402
from ahead_agent.state import State  # noqa: E402


# ── The test patient ─────────────────────────
# Watch and wait, so the `specific_*` subscales have no drug to be about (C1).
# The `belief_profile` is complete on purpose: it is what the isolation test
# (§3.1) hunts for in the doctor's context.

PATIENT = {
    "patient_id": "TEST-001",
    "disease_profile": {
        "diagnosis": "Chronic Lymphocytic Leukemia (CLL)",
        "treatment_regimen": "Watch and wait",
        "key_symptoms": ["Mild fatigue"],
        "trajectory": "Slow-progressing",
        "demographics": {"age": 58, "gender": "male"},
    },
    "belief_profile": {
        "b_ipq": {
            "consequences": 7,
            "timeline": 9,
            "personal_control": 3,
            "treatment_control": 6,
            "identity": 5,
            "concern": 8,
            "coherence": 4,
            "emotional_response": 8,
            "causes": ["Genetics / family history"],
        },
        "bmq": {"specific_necessity": 3.4},
    },
}


# ── Building what the model would reply ──────


def speaks(message, **arguments):
    """A doctor reply that speaks through the tool, with whatever the arm added (§4.1)."""
    return {
        "content": "",
        "tool_calls": [
            {
                "function": {
                    "name": "hand_off_to_patient",
                    "arguments": {"message": message, **arguments},
                }
            }
        ],
    }


def note(dimension, observation):
    return {"dimension": dimension, "observation": observation}


# ── Run profiles ─────────────────────────────


def profile(mode, notes=False):
    """The local profile with the two §4.1 switches set by hand."""
    config = load_config("local")
    config["features"] = {"coverage_hint": mode, "working_notes": notes}
    return config


def in_mode(mode, notes=False):
    return State(profile(mode, notes), PATIENT)


# ── Fixtures ─────────────────────────────────


@pytest.fixture
def scripted(monkeypatch):
    """Replies queued per role, and every message sent to each model kept in `seen`."""
    replies = {"doctor": [], "patient": [], "report": []}
    seen = {"doctor": [], "patient": [], "report": []}

    def fake_chat(config, role, messages, tools=None, events=None, usage=None):
        seen[role].append(messages)
        if usage is not None:
            usage.append({"role": role, "prompt_tokens": 100, "eval_tokens": 20})
        return replies[role].pop(0)

    monkeypatch.setattr(nodes.llm, "chat", fake_chat)
    return replies, seen


@pytest.fixture
def state():
    return State(load_config("local"), PATIENT)


@pytest.fixture
def make_run_profile(tmp_path):
    """A minimal valid run profile. Blocks are **replaced**, never merged: leaving
    a key out is how `test_config` proves it is required."""

    def _make(name: str, **overrides) -> Path:
        data = {
            "profile": name,
            "models": {"doctor": "doc", "patient": "pat", "embed": "emb"},
            "sampling": {
                "doctor_temperature": 0.7,
                "patient_temperature": 0.7,
                "report_temperature": 0.0,
                "seed": None,
                "context_length": 32768,
            },
            "server": {"ollama_url": "http://127.0.0.1:11434", "request_timeout": 300, "keep_alive": "1h"},
            "limits": {"max_turns": 30, "report_attempts": 2},
            "features": {"coverage_hint": "off", "working_notes": False},
            "paths": {"patients": "patients", "runs": "runs"},
        }
        data.update(overrides)
        path = tmp_path / f"{name}.yaml"
        path.write_text(yaml.safe_dump(data))
        return path

    return _make

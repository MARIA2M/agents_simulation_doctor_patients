# tests/conftest.py
# ─────────────────────────────────────────────
# Makes the package importable when pytest is run from anywhere.
# ─────────────────────────────────────────────

import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def make_profile(tmp_path):
    """Write a minimal valid run profile, with fields overridden per test."""

    def _make(name: str, **overrides) -> Path:
        data = {
            "profile": name,
            "models": {"doctor": "doc", "patient": "pat", "embed": "emb"},
            "sampling": {"temperature": 0.7, "seed": None},
            "server": {"ollama_url": "http://127.0.0.1:11434"},
            "paths": {"patients": "patients", "runs": "runs"},
        }
        data.update(overrides)
        path = tmp_path / f"{name}.yaml"
        path.write_text(yaml.safe_dump(data))
        return path

    return _make

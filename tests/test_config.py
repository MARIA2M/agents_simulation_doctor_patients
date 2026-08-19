# tests/test_config.py
# ─────────────────────────────────────────────
# Run profiles load, and a profile that would change results silently is
# rejected rather than defaulted (§12).
# ─────────────────────────────────────────────

import glob
import json

import pytest

from ahead_agent.config import (
    BIPQ_DIMENSIONS,
    BMQ_SUBSCALES,
    CAUSES_DIMENSION,
    CONFIG,
    REPO_ROOT,
    load_config,
)


# ── The profiles that ship with the repo ─────


@pytest.mark.parametrize("profile", ["local", "hpc"])
def test_shipped_profile_loads(profile):
    config = load_config(profile)

    assert config["profile"] == profile
    assert config["models"]["doctor"] and config["models"]["patient"]
    assert config["models"]["doctor"] != config["models"]["patient"], (
        "doctor and patient must not be the same model (§6.2)"
    )
    assert isinstance(config["sampling"]["temperature"], (int, float))


@pytest.mark.parametrize("profile", ["local", "hpc"])
def test_shipped_profile_survives_first_load_from_gpfs(profile):
    """A blob off GPFS can take over two minutes on first load (§6.1)."""
    config = load_config(profile)
    assert config["server"]["request_timeout"] >= 300


def test_config_is_filled_in_place():
    """Modules that imported CONFIG at start-up must see the loaded values."""
    before = id(CONFIG)
    load_config("local")
    assert id(CONFIG) == before
    assert CONFIG["models"]["doctor"]


# ── Rejections ───────────────────────────────


def test_missing_temperature_is_rejected(make_profile):
    path = make_profile("sinT", sampling={"seed": None})
    with pytest.raises(KeyError, match="sampling.temperature"):
        load_config(str(path))


def test_zero_temperature_is_accepted(make_profile):
    """0.0 is a temperature, not a missing setting: a falsy check would drop it."""
    path = make_profile("cero", sampling={"temperature": 0.0, "seed": None})
    assert load_config(str(path))["sampling"]["temperature"] == 0.0


def test_missing_model_is_rejected(make_profile):
    path = make_profile("sinmodelo", models={"doctor": "doc", "embed": "emb"})
    with pytest.raises(KeyError, match="models.patient"):
        load_config(str(path))


def test_declared_profile_must_match_filename(make_profile):
    """The declared name goes verbatim into run_meta; a mismatch mislabels runs."""
    path = make_profile("otro", profile="local")
    with pytest.raises(ValueError, match="does not match its filename"):
        load_config(str(path))


def test_unknown_profile_is_rejected():
    with pytest.raises(FileNotFoundError):
        load_config("no_existe")


def test_ollama_url_can_be_redirected(monkeypatch):
    """Only the endpoint moves per machine; everything else comes from the file."""
    monkeypatch.setenv("OLLAMA_URL", "http://as01r1b18:11434")
    assert load_config("local")["server"]["ollama_url"] == "http://as01r1b18:11434"


# ── Dimension schema vs the corpus ───────────


def test_dimension_ids_match_every_patient():
    """The report schema and the ground truth must be keyed the same way (4.1)."""
    for path in sorted(glob.glob(str(REPO_ROOT / "patients" / "*.json"))):
        with open(path) as f:
            beliefs = json.load(f)["belief_profile"]

        assert set(BIPQ_DIMENSIONS) <= set(beliefs["b_ipq"]), path
        assert set(BMQ_SUBSCALES) <= set(beliefs["bmq"]), path


def test_causes_is_not_a_numeric_dimension():
    """Open-ended and matched by similarity — listing it here averages it (4.3)."""
    assert CAUSES_DIMENSION not in BIPQ_DIMENSIONS
    assert CAUSES_DIMENSION not in BMQ_SUBSCALES

# tests/test_config.py
# Profiles load, and one that would leave a setting to the server is rejected.

import pytest

from ahead_agent.config import (
    BIPQ_DIMENSIONS,
    BMQ_SUBSCALES,
    CAUSES_DIMENSION,
    load_config,
)


# ── The profiles that ship with the repo ─────


@pytest.mark.parametrize("profile", ["local", "hpc"])
def test_shipped_profile_loads(profile):
    config = load_config(profile)

    assert config["profile"] == profile
    assert config["models"]["doctor"] and config["models"]["patient"]
    temperatures = [k for k in config["sampling"] if k.endswith("_temperature")]
    assert len(temperatures) == 3
    for name in temperatures:
        assert isinstance(config["sampling"][name], (int, float)), name


@pytest.mark.parametrize("profile", ["local", "hpc"])
def test_shipped_profile_survives_first_load_from_gpfs(profile):
    """A blob off GPFS can take over two minutes on first load (§6.1)."""
    config = load_config(profile)
    assert config["server"]["request_timeout"] >= 300


# 0.5
def test_the_profiles_agree_on_everything_they_do_not_choose():
    """The drift base.yaml exists to stop: it happened twice before it existed."""
    local, hpc = load_config("local"), load_config("hpc")

    assert local["sampling"] == hpc["sampling"]
    assert local["limits"] == hpc["limits"]
    assert local["features"] == hpc["features"]
    assert local["prompts"] == hpc["prompts"]


def test_a_profile_completes_the_inherited_block_instead_of_replacing_it():
    """`server` names two keys in base and one in the profile; a shallow
    merge would drop whichever side did not name them."""
    local = load_config("local")

    assert set(local["models"]) == {"doctor", "patient", "embed"}
    assert local["server"]["keep_alive"] == "1h"          # from the profile
    assert local["server"]["request_timeout"] == 300      # from base


def test_base_is_not_a_profile():
    """It names no models, so loading it alone fails rather than half-working."""
    with pytest.raises(KeyError, match="models.doctor"):
        load_config("base")


# ── Inheritance ──────────────────────────────


def test_an_arm_inherits_through_a_chain(make_run_profile, tmp_path):
    """What Stage 8 needs: an arm that changes one switch and nothing else.
    Two levels, so the merge has to walk the chain and not just one parent."""
    make_run_profile("padre", server={"ollama_url": "http://127.0.0.1:11434",
                                      "request_timeout": 300, "keep_alive": "4h"})
    (tmp_path / "brazo.yaml").write_text(
        "profile: brazo\nextends: padre\nfeatures:\n  coverage_hint: show\n"
    )

    arm = load_config(str(tmp_path / "brazo.yaml"))

    assert arm["features"] == {"coverage_hint": "show", "working_notes": False}
    assert arm["server"]["keep_alive"] == "4h"      # inherited two levels up
    assert arm["models"]["doctor"] == "doc"


def test_a_cycle_is_reported_instead_of_recursing_forever(tmp_path):
    (tmp_path / "ida.yaml").write_text("profile: ida\nextends: vuelta\n")
    (tmp_path / "vuelta.yaml").write_text("profile: vuelta\nextends: ida\n")

    with pytest.raises(ValueError, match="cycle"):
        load_config(str(tmp_path / "ida.yaml"))


def test_extending_something_absent_names_what_is_missing(tmp_path):
    """Silence here would look like a profile that simply lacks its settings."""
    (tmp_path / "huerfano.yaml").write_text("profile: huerfano\nextends: fantasma\n")

    with pytest.raises(FileNotFoundError, match="fantasma"):
        load_config(str(tmp_path / "huerfano.yaml"))


def test_each_load_is_independent():
    """No shared state: loading one profile cannot alter another already loaded."""
    local = load_config("local")
    hpc = load_config("hpc")

    assert local is not hpc
    assert local["profile"] == "local"


# ── Rejections ───────────────────────────────


# A profile from `make_run_profile` declares no `extends`, so it is validated
# on its own — which is what lets leaving a key out prove the key is required.


def test_temperature_is_required_for_every_role(make_run_profile):
    """A role left out would sample at whatever the server decides (§12)."""
    path = make_run_profile(
        "sinrol", sampling={"doctor_temperature": 0.7, "patient_temperature": 0.7}
    )
    with pytest.raises(KeyError, match="sampling.report_temperature"):
        load_config(str(path))


def test_zero_temperature_is_accepted(make_run_profile):
    """0.0 is a temperature, not a missing setting: a falsy check would drop it."""
    path = make_run_profile(
        "cero",
        sampling={
            "doctor_temperature": 0.0,
            "patient_temperature": 0.0,
            "report_temperature": 0.0,
            "context_length": 32768,
        },
    )
    assert load_config(str(path))["sampling"]["report_temperature"] == 0.0


def test_missing_model_is_rejected(make_run_profile):
    path = make_run_profile("sinmodelo", models={"doctor": "doc", "embed": "emb"})
    with pytest.raises(KeyError, match="models.patient"):
        load_config(str(path))


def test_missing_turn_limit_is_rejected(make_run_profile):
    """Without max_turns nothing stops a doctor who never closes (1.5)."""
    path = make_run_profile("sinlimite", limits={"report_attempts": 2})
    with pytest.raises(KeyError, match="limits.max_turns"):
        load_config(str(path))


def test_missing_paths_are_rejected(make_run_profile):
    """Caught here rather than as a bare KeyError when a path is first used."""
    path = make_run_profile("sinrutas", paths={"patients": "patients"})
    with pytest.raises(KeyError, match="paths.runs"):
        load_config(str(path))


def test_declared_profile_must_match_filename(make_run_profile):
    """The declared name is stored in the metadata; a mismatch mislabels runs."""
    path = make_run_profile("otro", profile="local")
    with pytest.raises(ValueError, match="must declare"):
        load_config(str(path))


def test_unknown_profile_is_rejected():
    with pytest.raises(FileNotFoundError):
        load_config("no_existe")


@pytest.mark.parametrize("mode", ["off", "show"])
def test_the_coverage_arms_are_accepted(make_run_profile, mode):
    path = make_run_profile("brazo", features={"coverage_hint": mode, "working_notes": False})

    assert load_config(str(path))["features"]["coverage_hint"] == mode


def test_a_retired_mode_is_rejected(make_run_profile):
    """`declare` existed and was retired: an old profile must fail, not run on."""
    path = make_run_profile(
        "viejo", features={"coverage_hint": "declare", "working_notes": False}
    )

    with pytest.raises(ValueError, match="not one of"):
        load_config(str(path))


def test_an_unquoted_off_is_caught_and_named(make_run_profile):
    """Bare `off` is False in YAML, and False would read as "no coverage" while
    meaning "nobody chose" — the §12 failure, in a new place."""
    path = make_run_profile(
        "booleano", features={"coverage_hint": False, "working_notes": False}
    )

    with pytest.raises(ValueError, match="YAML boolean"):
        load_config(str(path))


@pytest.mark.parametrize("value", ["off", "false", "no", "0"])
def test_a_quoted_working_notes_is_caught_and_named(make_run_profile, value):
    """The mirror of the trap above: quoting it is what turns the arm on."""
    path = make_run_profile(
        "comillas", features={"coverage_hint": "off", "working_notes": value}
    )

    with pytest.raises(ValueError, match="not true or false"):
        load_config(str(path))


def test_ollama_url_can_be_redirected(monkeypatch):
    """Only the endpoint moves per machine; everything else comes from the file."""
    monkeypatch.setenv("OLLAMA_URL", "http://as01r1b18:11434")
    assert load_config("local")["server"]["ollama_url"] == "http://as01r1b18:11434"


# ── Dimension schema vs the corpus ───────────


# That every patient carries the keys of all dimensions is checked by
# `test_corpus.py::test_profile_carries_ground_truth`, which also requires them
# to be numbers: you cannot read the value of a key that is missing.


def test_causes_is_not_a_numeric_dimension():
    """Open-ended and matched by similarity — listing it here averages it (4.3)."""
    assert CAUSES_DIMENSION not in BIPQ_DIMENSIONS
    assert CAUSES_DIMENSION not in BMQ_SUBSCALES

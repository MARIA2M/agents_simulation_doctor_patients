# tests/test_prompts.py
# Composing a system prompt from disk: base role + skills + resources (1.6, 1.7).
# What is composed is decided by the profile, never by the model (§5.1).

import json

import pytest

from ahead_agent import prompts


RUBRIC = {
    "instrument": "B-IPQ",
    "title": "beliefs about the illness",
    "range": [0, 10],
    "guidance": "Score what their life shows.",
    "rules": ["Weigh the conduct."],
    "dimensions": {
        "consequences": {
            "label": "impact on their life",
            "low": "no effect",
            "high": "dependent",
            "anchors": [[2, "Keeps every role."], [8, "A major role is lost."]],
            "note": "Not the words they use.",
        }
    },
}


@pytest.fixture
def library(tmp_path):
    """A prompts/, skills/ and resources/ tree, and a config pointing at them."""
    for folder in ("prompts/doctor_rubric", "skills/styles", "resources"):
        (tmp_path / folder).mkdir(parents=True)

    (tmp_path / "prompts/DOCTOR.md").write_text("You are a doctor.\n")
    (tmp_path / "prompts/PATIENT.md").write_text("You are a patient.\n")
    (tmp_path / "prompts/REPORT.md").write_text("Write the report.\n")
    (tmp_path / "prompts/doctor_rubric/bipq.json").write_text(json.dumps(RUBRIC))
    (tmp_path / "skills/styles/empathic.md").write_text("Be warm.")
    (tmp_path / "skills/styles/terse.md").write_text("Be brief.")
    (tmp_path / "resources/csm.md").write_text("The Common-Sense Model.")

    def _config(**blocks):
        config = {
            "prompts": {
                "doctor": "DOCTOR.md",
                "patient": "PATIENT.md",
                "report": "REPORT.md",
                "doctor_rubric": ["doctor_rubric/bipq.json"],
            },
            "paths": {
                "prompts": tmp_path / "prompts",
                "skills": tmp_path / "skills",
                "resources": tmp_path / "resources",
            },
        }
        for block, value in blocks.items():
            if block == "prompts":
                config["prompts"].update(value)
            else:
                config[block] = value
        return config

    return _config


# ── Resolving files ──────────────────────────


def test_the_base_role_comes_from_the_file_the_profile_names(library):
    assert prompts.compose_prompt(library(), "doctor") == "You are a doctor."


def test_a_missing_file_is_an_error_not_an_empty_prompt(library):
    """Composing on silently is how a run gets made with half a prompt."""
    config = library()
    config["prompts"]["doctor"] = "NOPE.md"

    with pytest.raises(FileNotFoundError):
        prompts.compose_prompt(config, "doctor")


def test_no_skills_or_resources_block_composes_the_role_alone(library):
    """Both blocks are absent here, not empty — neither may raise."""
    config = library()
    config.pop("skills", None)
    config.pop("resources", None)

    assert prompts.compose_prompt(config, "doctor") == "You are a doctor."


# ── Composing skills and resources ───────────


def test_skills_are_appended_in_the_order_the_profile_lists_them(library):
    """The code decides what is loaded and when, not the model (§5.1)."""
    config = library(skills={"doctor": ["styles/terse", "styles/empathic"], "patient": []})

    composed = prompts.compose_prompt(config, "doctor")

    assert composed.index("Be brief.") < composed.index("Be warm.")
    assert composed.startswith("You are a doctor.")


def test_resources_come_after_skills(library):
    config = library(
        skills={"doctor": ["styles/empathic"], "patient": []},
        resources={"doctor": ["csm"], "patient": []},
    )

    composed = prompts.compose_prompt(config, "doctor")

    assert composed.index("Be warm.") < composed.index("The Common-Sense Model.")


def test_each_role_gets_only_its_own_skills(library):
    config = library(skills={"doctor": ["styles/empathic"], "patient": ["styles/terse"]})

    assert "Be warm." in prompts.compose_prompt(config, "doctor")
    assert "Be warm." not in prompts.compose_prompt(config, "patient")
    assert "Be brief." in prompts.compose_prompt(config, "patient")


def test_fragments_are_separated_so_they_cannot_run_together(library):
    """A skill that reads as the last paragraph of the role is a different prompt."""
    config = library(skills={"doctor": ["styles/empathic"], "patient": []})

    assert prompts.SEPARATOR in prompts.compose_prompt(config, "doctor")


# ── Hashes ───────────────────────────────────


def test_the_hash_is_of_the_composed_prompt_not_the_base_file(library):
    """Otherwise a run could not be traced to the prompt that produced it (0.4)."""
    bare = prompts.hashes(library())
    with_skill = prompts.hashes(library(skills={"doctor": ["styles/empathic"], "patient": []}))

    assert bare["doctor"] != with_skill["doctor"]
    assert bare["patient"] == with_skill["patient"]


def test_the_same_composition_always_hashes_the_same(library):
    """Deterministic composition is what makes the hash worth recording (§5.1)."""
    config = library(skills={"doctor": ["styles/empathic"], "patient": []})

    assert prompts.hashes(config) == prompts.hashes(config)


def test_an_arm_that_adds_a_tool_argument_changes_the_tool_hash(library):
    """The descriptions are instructions, so two arms are not the same run (0.4)."""
    bare, arm = library(), library()
    arm["features"] = {"coverage_hint": "show", "working_notes": True}

    assert prompts.hashes(bare)["tools"] != prompts.hashes(arm)["tools"]
    assert prompts.hashes(bare)["doctor"] == prompts.hashes(arm)["doctor"]


def test_the_hashes_name_which_skills_were_loaded(library):
    """The hash says a prompt changed; this says what changed it."""
    config = library(skills={"doctor": ["styles/empathic"], "patient": []})

    assert prompts.hashes(config)["skills"] == {"doctor": ["styles/empathic"], "patient": []}


# ── The doctor's rubric ──────────────────────


def test_the_anchors_reach_the_report(library):
    composed = prompts.compose_prompt(library(), "report")

    assert "  - 2 · Keeps every role." in composed
    assert "  - 8 · A major role is lost." in composed
    assert "Not the words they use." in composed


def test_the_doctor_never_sees_the_scale_during_the_consultation(library):
    """Only the report scores. A doctor holding the anchors would be scoring
    while it talks, which is the elicitation arm by another route."""
    assert "A major role is lost." not in prompts.compose_prompt(library(), "doctor")
    assert "A major role is lost." not in prompts.compose_prompt(library(), "patient")


def test_changing_an_anchor_changes_the_rubric_hash(library, tmp_path):
    """It is hashed apart from the report so a change of anchors can be told
    from a change of instructions (0.4)."""
    before = prompts.hashes(library())

    moved = json.loads(json.dumps(RUBRIC))
    moved["dimensions"]["consequences"]["anchors"][0][0] = 3
    (tmp_path / "prompts/doctor_rubric/bipq.json").write_text(json.dumps(moved))
    after = prompts.hashes(library())

    assert before["doctor_rubric"] != after["doctor_rubric"]
    assert before["doctor"] == after["doctor"]


def test_a_missing_rubric_file_is_an_error(library):
    config = library(prompts={"doctor_rubric": ["doctor_rubric/nope.json"]})

    with pytest.raises(FileNotFoundError):
        prompts.compose_prompt(config, "report")


# ── The real files ───────────────────────────


def test_the_profiles_on_disk_compose():
    """Every shipped profile must name prompt files that exist."""
    from ahead_agent.config import RUN_PROFILES_DIR, load_config

    import yaml

    for path in sorted(RUN_PROFILES_DIR.glob("*.yaml")):
        # base.yaml and anything else shared: no `profile:` key, never loads alone
        if "profile" not in (yaml.safe_load(path.read_text()) or {}):
            continue
        config = load_config(path.stem)
        for role in ("doctor", "patient"):
            assert prompts.compose_prompt(config, role).strip(), f"{path.name}: empty {role} prompt"

# tests/test_styles.py
# The doctor's communication styles as files (1.14, 6.5, §5.1).
#
# Nothing here runs a model. These tests hold the port together — that the
# registry and the directory agree, that a style says how the doctor talks and
# never what it should conclude, and that the base prompt no longer fixes a
# style of its own. Whether a style actually changes a transcript is a live
# question and cannot be asked here.

import re
from pathlib import Path

import pytest
import yaml

from ahead_agent import prompts
from ahead_agent.config import RUN_PROFILES_DIR, load_config

REPO_ROOT = Path(__file__).resolve().parents[1]
STYLES_DIR = REPO_ROOT / "skills" / "styles"
REGISTRY = yaml.safe_load((STYLES_DIR / "styles.yaml").read_text())

STYLE_IDS = sorted(REGISTRY["styles"])
STYLE_FILES = {path.stem: path for path in STYLES_DIR.glob("*.md") if path.stem != "README"}


def composed_with(style: str) -> str:
    config = load_config("hpc")
    config["skills"] = {"doctor": [f"styles/{style}"], "patient": []}
    return prompts.compose_prompt(config, "doctor")


# ── The registry and the directory ───────────


def test_every_style_has_a_file_and_every_file_a_style():
    """The source arm had `high_psysician_control_paternalistic` in its allow
    list and `physician` on disk, which made that style unreachable in both
    directions. The spelling was never the fix; this is."""
    assert set(STYLE_IDS) == set(STYLE_FILES)


@pytest.mark.parametrize("style", STYLE_IDS)
def test_a_style_declares_what_it_is_and_how_to_recognise_it(style):
    entry = REGISTRY["styles"][style]

    assert entry["label"]
    assert entry["role"]
    assert entry["turn_budget"]
    # 6.5 compares styles against these, so an empty list is a style that
    # cannot be checked for adherence
    assert entry["markers"]


@pytest.mark.parametrize("style", STYLE_IDS)
def test_hypotheses_are_declared_even_when_there_are_none(style):
    """`good_doctor` has no source and predicted nothing. Absent and null are
    not the same: one is an oversight, the other is the answer."""
    assert "hypotheses" in REGISTRY["styles"][style]


@pytest.mark.parametrize("style", STYLE_IDS)
def test_every_style_has_the_same_three_sections(style):
    """Nine files that read alike are nine files that can be diffed. One with
    its own shape is one whose difference is layout, not style."""
    headings = re.findall(r"^## (.+)$", STYLE_FILES[style].read_text(), re.M)

    assert headings == ["What you do", "What you do not do", "Questions and turns"]


@pytest.mark.parametrize("style", STYLE_IDS)
def test_a_style_constrains_about_as_much_as_it_prescribes(style):
    """`good_doctor` shipped with five instructions and one prohibition while
    every port had four. Uneven constraint pressure is a difference between
    arms that nobody chose, and it lands on the axis the styles are meant to
    vary."""
    sections = STYLE_FILES[style].read_text().split("## ")
    prohibitions = [
        line for line in sections[2].splitlines() if line.startswith("- ")
    ]

    assert len(prohibitions) >= 3, f"{style}.md: {len(prohibitions)}"


@pytest.mark.parametrize("pair", REGISTRY["contrast_pairs"], ids=lambda p: "-vs-".join(p))
def test_a_contrast_pair_names_two_different_styles_that_exist(pair):
    first, second = pair

    assert first != second
    assert {first, second} <= set(STYLE_IDS)


# ── What a style may say ─────────────────────

# Naming the instrument to the doctor is how the questionnaire comes back in.
# Whole words: a style may perfectly well say "inaccurate" or "deliberate".
FORBIDDEN = [
    "b-ipq", "bipq", "bmq", "ipq-r",
    "questionnaire", "common-sense model", "necessity-concerns",
    "construct", "constructs", "subscale", "subscales", "0-10",
    "rate", "rating", "score", "scored", "scoring", "dimension", "dimensions",
]

# How section 9 was worded. Naming a dimension is not the problem — DOCTOR.md
# §5 lists all twelve, and a style has to be able to say "do not go into
# identity or social consequences". The problem is a style predicting, to the
# agent that will later score them, which ones come out full and which empty.
FORETELLING = [
    "target construct", "more visible", "under-elicited", "underelicited",
    "may remain", "likely visible", "expected effect",
]


@pytest.mark.parametrize("style", STYLE_IDS)
def test_no_style_names_the_instrument_or_the_scale(style):
    text = STYLE_FILES[style].read_text().lower()
    found = [word for word in FORBIDDEN if re.search(rf"\b{re.escape(word)}\b", text)]

    assert not found, f"{style}.md: {', '.join(found)}"


@pytest.mark.parametrize("style", STYLE_IDS)
def test_no_style_tells_the_doctor_which_dimensions_will_stay_empty(style):
    """The source listed, per style, which constructs would be visible and
    which would stay hidden. In an arm where the same agent later returns NA
    for those very dimensions, that is the answer handed over inside the
    question (1.10, 3.2). It belongs in the registry, and it is there."""
    text = STYLE_FILES[style].read_text().lower()
    found = [phrase for phrase in FORETELLING if phrase in text]

    assert not found, f"{style}.md: {', '.join(found)}"


@pytest.mark.parametrize("style", STYLE_IDS)
def test_the_hypotheses_stayed_out_of_the_prompt(style):
    """The line the port turns on: what we expect to see is not something the
    doctor is told before it happens."""
    hypotheses = REGISTRY["styles"][style]["hypotheses"] or {}
    prompt = " ".join(STYLE_FILES[style].read_text().lower().split())

    for text in hypotheses.values():
        # first clause, which is where each prediction actually lives
        claim = " ".join(text.lower().split()).split(".")[0]
        assert claim not in prompt


@pytest.mark.parametrize("style", STYLE_IDS)
def test_the_anchors_still_do_not_reach_a_doctor_with_a_style(style):
    """The invariant of test_prompts, once more with a skill loaded: a style is
    a new way for the scale to arrive at the consultation."""
    composed = composed_with(style)

    assert "Scale — beliefs about the illness" not in composed
    assert "Not scored." not in composed


# ── Composition and hashes (§5.1, 0.4) ───────


@pytest.mark.parametrize("style", STYLE_IDS)
def test_a_style_reaches_the_doctor_and_only_the_doctor(style):
    config = load_config("hpc")
    config["skills"] = {"doctor": [f"styles/{style}"], "patient": []}
    heading = STYLE_FILES[style].read_text().splitlines()[0]

    assert heading in prompts.compose_prompt(config, "doctor")
    assert heading not in prompts.compose_prompt(config, "patient")


def test_two_styles_are_two_different_prompts():
    """The offline half of the §5.1 test. That the composed prompts differ is
    the most this can show; that the transcripts differ needs a server."""
    first, second = REGISTRY["contrast_pairs"][0]

    assert composed_with(first) != composed_with(second)


def test_each_style_gives_the_doctor_prompt_its_own_hash():
    """Otherwise two arms are one run in the provenance (0.4)."""
    fingerprints = {}
    for style in STYLE_IDS:
        config = load_config("hpc")
        config["skills"] = {"doctor": [f"styles/{style}"], "patient": []}
        fingerprints[style] = prompts.hashes(config)["doctor"]

    assert len(set(fingerprints.values())) == len(STYLE_IDS)


# ── The profiles on disk ─────────────────────

ARM_PROFILES = sorted(RUN_PROFILES_DIR.glob("style-*.yaml"))
SHIPPED_PROFILES = [
    path for path in sorted(RUN_PROFILES_DIR.glob("*.yaml"))
    if "profile" in (yaml.safe_load(path.read_text()) or {})
]


@pytest.mark.parametrize("path", ARM_PROFILES, ids=lambda p: p.stem)
def test_a_style_arm_is_named_after_the_style_it_loads(path):
    """`style-<id>` is the whole convention, so a typo in the file name is a
    failing test rather than an arm that quietly runs another style."""
    style = path.stem.removeprefix("style-")
    config = load_config(path.stem)

    assert style in STYLE_IDS
    assert config["skills"]["doctor"] == [f"styles/{style}"]


@pytest.mark.parametrize("path", SHIPPED_PROFILES, ids=lambda p: p.stem)
def test_every_profile_names_exactly_one_style(path):
    """After 1.14 the doctor's style is always a file that was chosen. A
    profile with none runs whatever DOCTOR.md happens to imply, which is the
    unnamed arm this task exists to abolish."""
    loaded = [name for name in load_config(path.stem)["skills"]["doctor"]
              if name.startswith("styles/")]

    assert len(loaded) == 1, f"{path.name}: {loaded}"


# ── The base prompt is style-free (1.14) ─────

# What DOCTOR.md said about tone before the styles were files, and what
# `good_doctor` still has to carry for the reference condition to mean anything.
#
# The four literal example questions DOCTOR.md also carried are deliberately
# NOT pinned: they were dropped from good_doctor.md because they made the
# reference arm the most heavily scripted of the nine. That is a change to the
# arm, made before any batch ran under it, not a leak.
MOVED_OUT = [
    "Be empathic and patient-centred",
    "Adapt your style",
    "professional but warm",
]


@pytest.mark.parametrize("sentence", MOVED_OUT)
def test_the_style_left_the_base_prompt_and_is_in_good_doctor(sentence):
    """Both halves matter: if it stays in DOCTOR.md, every style contradicts
    it; if it is not in good_doctor.md, the reference condition has lost the
    tone it is supposed to be a reference for."""
    doctor = (REPO_ROOT / "prompts" / "DOCTOR.md").read_text()

    assert sentence not in doctor
    assert sentence in STYLE_FILES["good_doctor"].read_text()

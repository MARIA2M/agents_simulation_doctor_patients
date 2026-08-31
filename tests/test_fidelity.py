# tests/test_fidelity.py
# 3.5 / F1 — did the patient play its profile? Deterministic throughout; no
# model is involved, so nothing here is scripted.
#
# The failure this module was written for is real: `skills/styles/README.md`
# records that in s51-nb-1 r1 the patient claimed medication and headaches for
# CLL-001, which is watch-and-wait with neither.

import json

import pytest

from ahead_agent import fidelity
from ahead_agent.fidelity import CONTRADICTION, UNSUPPORTED


# ── Fixtures ─────────────────────────────────

WATCH_AND_WAIT = {
    "patient_id": "TEST-001",
    "disease_profile": {
        "diagnosis": "Chronic Lymphocytic Leukemia (CLL)",
        "treatment_regimen": "Watch and wait",
        "key_symptoms": ["Mild fatigue"],
        "trajectory": "Slow-progressing",
        "demographics": {"age": 58, "gender": "male"},
    },
    "belief_profile": {"b_ipq": {"consequences": 7}, "bmq": {}},
}

ON_TREATMENT = {
    "patient_id": "TEST-002",
    "disease_profile": {
        "diagnosis": "HIV",
        "treatment_regimen": "Biktarvy, one tablet daily",
        "key_symptoms": ["Occasional headaches"],
        "trajectory": "Stable, undetectable viral load",
        "demographics": {"age": 41, "gender": "female"},
    },
    "belief_profile": {"b_ipq": {"consequences": 3}, "bmq": {}},
}

# Same as WATCH_AND_WAIT with no age recorded. A profile is allowed to leave
# demographics thin, and the patient is still not allowed to fill the gap in.
NO_AGE = {
    "patient_id": "TEST-003",
    "disease_profile": {
        "diagnosis": "Chronic Lymphocytic Leukemia (CLL)",
        "treatment_regimen": "Watch and wait",
        "key_symptoms": ["Mild fatigue"],
        "trajectory": "Slow-progressing",
        "demographics": {"gender": "male"},
    },
    "belief_profile": {"b_ipq": {"consequences": 7}, "bmq": {}},
}


def findings(text, profile=WATCH_AND_WAIT):
    return fidelity.check_turn(text, fidelity.profile_facts(profile), turn=3)


def kinds(text, profile=WATCH_AND_WAIT):
    return sorted(f.kind for f in findings(text, profile))


# ── What the profile says about treatment ────


def test_a_watch_and_wait_profile_is_read_as_no_treatment():
    assert fidelity.profile_facts(WATCH_AND_WAIT).on_treatment is False


def test_a_named_regimen_is_read_as_treatment():
    assert fidelity.profile_facts(ON_TREATMENT).on_treatment is True


# ── The failure that started the module ──────


def test_claiming_medication_on_a_no_treatment_profile_is_a_contradiction():
    """s51-nb-1 r1, exactly."""
    found = findings("I always take my tablets at the same time each morning.")

    assert [f.severity for f in found] == [CONTRADICTION]
    assert found[0].kind == "treatment"


def test_the_finding_carries_the_sentence_it_came_from():
    """A finding a human cannot judge without opening the transcript is a chore,
    not a report."""
    found = findings("It has been hard. My medication makes me tired. I cope.")

    assert found[0].quote == "My medication makes me tired."
    assert found[0].turn == 3


@pytest.mark.parametrize(
    "text",
    [
        "I'm not taking any medication at all.",
        "I don't have my pills, there is nothing to take.",
        "No treatment yet, they are just watching it.",
    ],
    ids=["not taking", "don't have", "no treatment"],
)
def test_a_denial_is_not_a_claim(text):
    """Without this the module fires on precisely the sentences that prove
    fidelity rather than break it."""
    assert [f for f in findings(text) if f.kind == "treatment"] == []


def test_talking_about_treatment_in_the_future_is_not_a_claim_to_be_on_it():
    assert [f for f in findings("If it progresses they will start me on something.")
            if f.kind == "treatment"] == []


# ── Drugs ────────────────────────────────────


def test_a_named_drug_absent_from_the_profile_is_flagged():
    found = [f for f in findings("They started me on ibrutinib last month.")
             if f.kind == "drug"]

    assert len(found) == 1
    assert found[0].claim.casefold() == "ibrutinib"
    assert found[0].severity == CONTRADICTION      # no-treatment profile


def test_the_drug_in_the_profile_is_not_flagged():
    """Biktarvy is this patient's actual regimen: saying so is fidelity."""
    assert [f for f in findings("I take my Biktarvy every morning.", ON_TREATMENT)
            if f.kind == "drug"] == []


def test_a_second_drug_is_unsupported_even_on_a_treated_patient():
    found = [f for f in findings("They added venetoclax too.", ON_TREATMENT)
             if f.kind == "drug"]

    assert [f.severity for f in found] == [UNSUPPORTED]


@pytest.mark.parametrize(
    "text",
    ["I'm taking ibrutinib.", "I am on venetoclax now.", "They put me on ibrutinib."],
    ids=["taking", "on", "put me on"],
)
def test_a_bare_drug_name_is_a_medication_claim(text):
    """"I'm taking ibrutinib" names no medication noun at all, so the treatment
    patterns alone would miss it. It is caught, and caught as hard."""
    found = [f for f in findings(text) if f.kind == "drug"]

    assert [f.severity for f in found] == [CONTRADICTION]


def test_a_drug_claim_is_reported_once_not_twice():
    """`_TAKING` now has drug branches, so "I'm taking ibrutinib" matches both
    rules. One claim is one finding, and the drug one names the drug."""
    found = findings("I'm taking ibrutinib.")

    assert [f.kind for f in found] == ["drug"]


def test_the_treated_patient_is_not_punished_for_naming_their_own_regimen():
    """The drug branches can only fire where any drug is already a
    contradiction. A patient on Biktarvy saying so is fidelity, not a finding."""
    assert findings("I'm taking my Biktarvy every morning.", ON_TREATMENT) == []


def test_an_invented_drug_is_caught_by_its_suffix():
    """The list cannot hold every drug, and a fabricated one is not in it by
    definition. `-nib` and `-mab` end essentially nothing else in English."""
    found = [f for f in findings("They put me on flurbotinib.") if f.kind == "drug"]

    assert len(found) == 1
    assert found[0].claim == "flurbotinib"


@pytest.mark.parametrize(
    "word",
    ["medicine", "routine", "determine", "machine", "discipline", "vaccine"],
    ids=["medicine", "routine", "determine", "machine", "discipline", "vaccine"],
)
def test_ordinary_words_that_end_like_drugs_are_not_drugs(word):
    """The rule that catches `emtricitabine` also catches `medicine`. This is
    why the suffix rule stops at -nib/-mab/-vir and the rest is a named list."""
    assert [f for f in findings(f"It became part of my {word}.") if f.kind == "drug"] == []


def test_a_drug_named_twice_is_one_finding():
    found = [f for f in findings("Ibrutinib, yes, ibrutinib every day.")
             if f.kind == "drug"]

    assert len(found) == 1


# ── Symptoms ─────────────────────────────────


def test_a_symptom_the_profile_does_not_list_is_soft_not_hard():
    """A real patient volunteers detail. Only a human can tell that from
    invention, so this never fails a run on its own."""
    found = [f for f in findings("The headaches have been awful.") if f.kind == "symptom"]

    assert [f.severity for f in found] == [UNSUPPORTED]


def test_a_symptom_the_profile_lists_is_not_flagged():
    assert [f for f in findings("The fatigue is the worst part.") if f.kind == "symptom"] == []


def test_a_symptom_the_profile_lists_is_not_flagged_for_the_treated_patient():
    """`Occasional headaches` is in this profile, so headaches are in character."""
    assert [f for f in findings("The headaches come and go.", ON_TREATMENT)
            if f.kind == "symptom"] == []


def test_a_denied_symptom_is_not_a_claim():
    assert [f for f in findings("No nausea, nothing like that.")
            if f.kind == "symptom"] == []


def test_a_denial_early_in_the_turn_does_not_hide_a_claim_later_in_it():
    """The scan used to stop at the first occurrence, so a denial swallowed
    everything after it. A negation also stops reaching at `but`."""
    found = [f for f in findings(
        "No nausea at first, but then the nausea got really bad."
    ) if f.kind == "symptom"]

    assert len(found) == 1
    assert found[0].claim == "nausea"


def test_a_symptom_repeated_in_one_turn_is_still_one_finding():
    """Counting each repetition would measure how much the patient said it, not
    how many unsupported things they said — and the rate is built on the count."""
    found = [f for f in findings("Headaches, constant headaches, headaches all day.")
             if f.kind == "symptom"]

    assert len(found) == 1


def test_two_different_symptoms_are_two_findings():
    found = [f for f in findings("The headaches and the dizziness both.")
             if f.kind == "symptom"]

    assert len(found) == 2


def test_a_negation_does_not_reach_across_a_full_stop():
    assert len([f for f in findings("I have no nausea. The dizziness is constant.")
                if f.kind == "symptom"]) == 1


# ── The shape of the output ──────────────────


def test_the_findings_come_back_in_the_order_they_were_said():
    """A report that jumps around the turn is harder to check against it."""
    found = findings("I'm taking ibrutinib. The headaches too. I'm 45.")

    assert [f.kind for f in found] == ["drug", "symptom", "age"]


def test_a_drug_in_the_turn_does_not_hide_the_symptoms():
    """A shadowed local once left the symptom scan searching the drug name
    instead of the turn, so any turn naming a drug reported no symptoms at all.
    Invisible to every test that checked one kind at a time."""
    found = findings("They gave me ibrutinib and now I get headaches and dizziness.")

    assert sorted(f.claim for f in found if f.kind == "symptom") == ["dizziness", "headaches"]
    assert [f.claim for f in found if f.kind == "drug"] == ["ibrutinib"]


def test_the_quote_survives_doubled_whitespace():
    """Offsets used to come from a whitespace-collapsed copy, so any double
    space shifted the quote left of the thing it was meant to show."""
    found = findings("It  has been  hard.  The headaches are awful.  I cope.")

    assert found[0].quote == "The headaches are awful."


# ── Age ──────────────────────────────────────


def test_an_age_that_contradicts_the_profile_is_hard():
    found = [f for f in findings("I'm 45 and I never expected this.") if f.kind == "age"]

    assert [f.severity for f in found] == [CONTRADICTION]
    assert "45" in found[0].claim and "58" in found[0].claim


def test_the_right_age_is_not_flagged():
    assert [f for f in findings("I'm 58 years old.") if f.kind == "age"] == []


def test_an_age_the_profile_does_not_carry_is_still_hard():
    """A profile with no age does not license inventing one. An age is a hard
    clinical fact, so stating one from nowhere is the same class of failure as
    naming a drug from nowhere."""
    found = [f for f in findings("I'm 45 and I never expected this.", NO_AGE)
             if f.kind == "age"]

    assert [f.severity for f in found] == [CONTRADICTION]
    assert "45" in found[0].claim and "no age" in found[0].claim


def test_an_age_in_words_is_caught_on_a_profile_without_one():
    assert len([f for f in findings("I am 62 years old.", NO_AGE) if f.kind == "age"]) == 1


@pytest.mark.parametrize(
    "text",
    [
        "I'm 45 minutes late for everything now.",
        "I'm 20 weeks into this whole thing.",
        "I'm 82 kg these days.",
        "I'm 30 times more tired than before.",
    ],
    ids=["minutes", "weeks", "kg", "times"],
)
def test_a_number_with_a_unit_after_it_is_not_an_age(text):
    """These matter more since a profile without an age also produces findings:
    without the unit guard every one of these would fire on every patient."""
    assert [f for f in findings(text, NO_AGE) if f.kind == "age"] == []


def test_an_implausible_number_is_not_an_age():
    assert [f for f in findings("I'm 7 out of 10 on a bad day.", NO_AGE)
            if f.kind == "age"] == []


# ── What is deliberately not checked ─────────


def test_the_belief_profile_is_never_read():
    """A patient expressing a belief is doing its job. Checking beliefs here
    would punish exactly the behaviour the whole simulation is built on."""
    facts = fidelity.profile_facts(WATCH_AND_WAIT)

    assert "consequences" not in facts.everything
    assert "7" not in facts.everything


def test_the_doctors_lines_are_not_checked(tmp_path):
    """The doctor naming a drug is a question, not a fabrication by the patient."""
    run = _write_run(tmp_path / "b", "TEST-001", 1, [
        {"turn": 1, "role": "doctor", "content": "Are you taking any medication, ibrutinib perhaps?"},
        {"turn": 1, "role": "patient", "content": "No, nothing at all."},
    ])

    assert fidelity.read_consultation(run, WATCH_AND_WAIT, 1).findings == []


# ── Over a batch ─────────────────────────────


def _write_run(batch, patient_id, repeat, conversation):
    run_dir = batch / f"{patient_id}-r{repeat}"
    run_dir.mkdir(parents=True)
    (run_dir / "transcript.json").write_text(
        json.dumps({"patient_id": patient_id, "conversation": conversation})
    )
    return run_dir


def _says(text):
    return [{"turn": 1, "role": "patient", "content": text}]


def test_the_rate_is_the_share_of_clean_runs(tmp_path):
    batch = tmp_path / "b"
    _write_run(batch, "TEST-001", 1, _says("Just tired, that is all."))
    _write_run(batch, "TEST-001", 2, _says("Just tired, that is all."))
    _write_run(batch, "TEST-001", 3, _says("Just tired, that is all."))
    _write_run(batch, "TEST-001", 4, _says("I take my pills each morning."))

    checked = fidelity.read_batch(batch, {"TEST-001": WATCH_AND_WAIT})

    assert len(checked.runs) == 4
    assert checked.fidelity_rate == 0.75


def test_the_two_rates_come_apart_on_a_soft_finding(tmp_path):
    """A run with only a symptom flag fails the strict rate and passes the hard
    one. Reporting a single number would hide which kind of finding it was."""
    batch = tmp_path / "b"
    _write_run(batch, "TEST-001", 1, _says("The headaches are constant."))

    checked = fidelity.read_batch(batch, {"TEST-001": WATCH_AND_WAIT})

    assert checked.fidelity_rate == 0.0
    assert checked.contradiction_free_rate == 1.0


def test_a_patient_with_no_profile_stops_the_run(tmp_path):
    """Fidelity is a check against the profile: skipping one silently would put
    an unchecked consultation into a rate that claims to cover the batch."""
    batch = tmp_path / "b"
    _write_run(batch, "GHOST-001", 1, _says("Fine, thanks."))

    with pytest.raises(SystemExit, match="GHOST-001"):
        fidelity.read_batch(batch, {"TEST-001": WATCH_AND_WAIT})


def test_the_scores_are_never_touched(tmp_path):
    """QC only: the module reads transcript.json and never report.json."""
    batch = tmp_path / "b"
    run = _write_run(batch, "TEST-001", 1, _says("I take my pills."))
    (run / "report.json").write_text(json.dumps({"report": {"bipq": {}, "bmq": {}}}))

    before = (run / "report.json").read_text()
    fidelity.read_batch(batch, {"TEST-001": WATCH_AND_WAIT})

    assert (run / "report.json").read_text() == before

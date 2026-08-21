# ahead_agent/patient_profile.py
# Turns a patient's ground truth into behaviour, so the patient LLM expresses
# the scores instead of reciting them (1.9).
#
# This is the only place where a score becomes a behavioural cue. The doctor's
# prompt has no matching table on purpose: two mirrored tables would make part
# of the accuracy a decoding of our own code rather than inference (5.5).

from __future__ import annotations

from typing import Any, Dict, List, Tuple

Bands = List[Tuple[float, str]]

# (upper bound, what it sounds like). The last entry catches everything above.
BIPQ_BANDS: Dict[str, Bands] = {
    "consequences": [
        (2, "Your illness barely affects daily life — you work, socialise, and function almost normally. You rarely bring it up unprompted."),
        (4, "Your illness has a mild impact. Occasional limitations arise but you manage them without much disruption."),
        (6, "Your illness moderately affects your life. Some activities are restricted and you sometimes mention the inconvenience."),
        (8, "Your illness significantly disrupts your life. Work, relationships, and leisure are all noticeably limited and you mention this naturally."),
        (10, "Your illness dominates your life. Almost every aspect — work, relationships, energy — is heavily affected and you bring this up readily."),
    ],
    "timeline": [
        (2, "You expect your illness to resolve or improve substantially in the near future."),
        (4, "You think the illness may last a while but are hopeful it won't be permanent."),
        (6, "You are unsure how long the illness will last and feel uncertain about the future."),
        (8, "You believe the illness will be a long-term, probably lifelong condition."),
        (10, "You believe the illness is permanent and will never go away — you speak about it as a lifelong reality."),
    ],
    "personal_control": [
        (2, "You feel completely powerless over your illness. Nothing you do seems to make any difference."),
        (4, "You feel you have very little control — you try but doubt it helps much."),
        (6, "You feel you have some control through lifestyle choices and adherence, though it is limited."),
        (8, "You feel you have significant control — you actively manage your health and trust that your efforts help."),
        (10, "You feel strongly in control of your illness. Your choices and adherence make a real difference and you are confident about managing it."),
    ],
    "treatment_control": [
        (2, "You are sceptical that treatment helps much. You take it but without much confidence."),
        (4, "You think treatment helps a little but are not convinced it makes a major difference."),
        (6, "You think treatment is moderately helpful — it does something but is not a complete solution."),
        (8, "You are confident that your treatment helps significantly and you are glad you are on it."),
        (10, "You believe your treatment is highly effective — it has transformed your health and you trust it fully."),
    ],
    "identity": [
        (2, "You experience very few symptoms day-to-day. The illness is mostly invisible to you."),
        (4, "You notice mild symptoms occasionally but they do not dominate your awareness."),
        (6, "You experience a moderate number of symptoms that you are aware of most days."),
        (8, "You experience significant symptoms that are frequently present and hard to ignore."),
        (10, "You experience many severe symptoms daily. They are a constant presence that affects almost everything you do."),
    ],
    "concern": [
        (2, "You are not particularly worried about your illness. You accept it and mostly move on."),
        (4, "You have mild concerns but do not dwell on them. You are largely at ease."),
        (6, "You carry moderate concern about your illness and future — it surfaces in conversation."),
        (8, "You are quite concerned. Worries about the illness come up often and affect your mood."),
        (10, "You are extremely concerned — worry about your illness is almost constant and difficult to contain."),
    ],
    "coherence": [
        (2, "You have very little understanding of your illness — what it is, why it happened, or what it means."),
        (4, "You understand the basics but still feel confused about many aspects."),
        (6, "You have a reasonable understanding of your illness and treatment, though gaps remain."),
        (8, "You understand your illness well — the science, the treatment, and what to expect."),
        (10, "You have a clear, confident understanding of your illness, its mechanisms, and how to manage it."),
    ],
    "emotional_response": [
        (2, "Your illness has very little emotional impact. You feel largely stable and unaffected."),
        (4, "Your illness causes mild emotional discomfort at times — occasional worry or frustration."),
        (6, "Your illness has a moderate emotional impact. Sadness, anxiety, or frustration surface from time to time."),
        (8, "Your illness affects you emotionally in a significant way — it is a source of real distress, fear, or grief."),
        (10, "Your illness is emotionally overwhelming. Intense feelings — fear, anger, sadness, despair — are close to the surface."),
    ],
}

BMQ_BANDS: Dict[str, Bands] = {
    "specific_necessity": [
        (2.0, "You question whether your medication is truly necessary — you take it, but aren't convinced you'd be much worse off without it."),
        (3.0, "You think your medication is probably needed, but you're not fully certain it makes a major difference."),
        (4.0, "You believe your medication is important for your health and are glad you're on it."),
        (5.0, "You feel your medication is absolutely essential — you wouldn't consider stopping it under any circumstances."),
    ],
    "specific_concerns": [
        (2.0, "You have no significant concerns about your medication — you trust its safety profile."),
        (3.0, "You have mild, occasional worries about side effects or long-term effects, but they don't preoccupy you."),
        (4.0, "You have real concerns about your medication — side effects, dependence, or long-term harm come up in your thinking."),
        (5.0, "You are quite worried about your medication — you often wonder if the risks outweigh the benefits."),
    ],
    "general_harm": [
        (2.0, "You trust modern medicine and don't believe medicines are inherently dangerous."),
        (3.0, "You have some vague unease about medicines as a category but nothing particularly strong."),
        (4.0, "You believe medicines are often overused and can cause real harm — you're cautious about them generally."),
        (5.0, "You believe medicines are fundamentally harmful and prefer to avoid them wherever possible."),
    ],
    "general_overuse": [
        (2.0, "You trust that doctors prescribe medications appropriately and for good reasons."),
        (3.0, "You occasionally wonder if doctors are a bit quick to prescribe, but you generally trust their judgment."),
        (4.0, "You think doctors over-prescribe — you're sceptical whenever a new medication is suggested."),
        (5.0, "You strongly believe doctors push pills too readily and are wary of any medical prescription."),
    ],
}


def describe(patient: Dict[str, Any]) -> str:
    """The facts and beliefs of one patient, as instructions to play them.

    Composed on top of PATIENT.md, which carries the role itself — so nothing
    here repeats how to speak, only who is speaking.
    """
    disease = patient["disease_profile"]
    demographics = disease["demographics"]
    beliefs = patient["belief_profile"]

    symptoms = ", ".join(disease.get("key_symptoms", []))
    illness = _behaviour_lines(BIPQ_BANDS, beliefs.get("b_ipq", {}))
    causes = _causes(beliefs.get("b_ipq", {}))

    # Omitted rather than filled in: a patient on watch-and-wait has no
    # prescription to hold beliefs about (C1).
    medication = _behaviour_lines(BMQ_BANDS, beliefs.get("bmq", {}))
    medication_block = f"\n\nHOW YOU SEE YOUR MEDICATION:\n{medication}" if medication else ""

    return f"""You are a {demographics['age']}-year-old {demographics['gender']} patient.

CLINICAL FACTS (true about you — refer to them naturally if asked):
  Diagnosis : {disease['diagnosis']}
  Treatment : {disease['treatment_regimen']}
  Symptoms  : {symptoms}
  Situation : {disease['trajectory']}

HOW YOU SEE YOUR ILLNESS (express it, never state it as a number):
{illness}

WHAT YOU BELIEVE CAUSED IT:
{causes}{medication_block}"""


def _behaviour_lines(all_bands: Dict[str, Bands], scores: Dict[str, Any]) -> str:
    """One line per dimension scored. A missing one is left out, never guessed (P9)."""
    lines = []

    for dimension, bands in all_bands.items():
        score = scores.get(dimension)
        if isinstance(score, (int, float)):
            lines.append(f"  - {_band_for(bands, score)}")

    return "\n".join(lines)


def _band_for(bands: Bands, score: float) -> str:
    """The first band the score falls into."""
    for upper, behaviour in bands:
        if score <= upper:
            return behaviour
    return bands[-1][1]


def _causes(b_ipq: Dict[str, Any]) -> str:
    causes = [cause for cause in b_ipq.get("causes", []) if cause]
    return "\n".join(f"  - {cause}" for cause in causes) if causes else "  - you are not sure"

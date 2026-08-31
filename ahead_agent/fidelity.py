# ahead_agent/fidelity.py
# ─────────────────────────────────────────────
# 3.5 / F1 — did the patient play the profile it was given?
#
# Deterministic: string and number comparison, no model call. Post-process, so
# it runs over any arm's batch after the fact.
#
# **It reads patients/*.json, and that is why it is not in coverage.py.** That
# module is truth-blind on purpose; this one is a check *against* the truth. The
# two must not share a file, or the map of 3.2 starts seeing the answer.
#
# WHAT THIS IS: a precision-first screen for named claims the profile does not
# support — a drug, a symptom, an age. It catches what `s51-nb-1` r1 did, where
# the patient claimed medication and headaches for a watch-and-wait profile with
# neither.
#
# "Does not support" includes silence. A profile that records no age does not
# license the patient to state one: an absent fact is not a blank cheque, it is
# a fact the transcript cannot invent. The same rule would apply to any other
# hard clinical field added here later.
#
# WHAT THIS IS NOT: a measure of fidelity. It reads named entities, not meaning,
# so a patient who invents a whole illness narrative in words no list contains
# passes clean. Every miss is a false pass, never a false alarm, which makes the
# rate it reports an **upper bound** on fidelity and never a score. Read a
# failing run; do not read a passing rate as agreement.
#
# This is the same trap PENDING.md names for coverage: a word list measures
# vocabulary, not topic. The difference is the question. "Did the doctor explore
# family?" is an open semantic class and a word list cannot answer it. "Did the
# patient assert a drug?" is a closed class of named things, where a list is
# precise and its misses fall on the safe side.
# ─────────────────────────────────────────────

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── Severity ─────────────────────────────────

# The profile says one thing and the patient said the opposite. Low false
# positive rate: these are worth failing a run over.
CONTRADICTION = "CONTRADICTION"

# The patient named something clinical the profile does not carry. It may be
# fair elaboration — a real patient volunteers detail — so it is surfaced for a
# human to read, never counted as proof of fabrication on its own.
UNSUPPORTED = "UNSUPPORTED"


# ── Vocabularies ─────────────────────────────
#
# Deliberately small and specific. A long list buys recall this module has
# already declined to promise, and every added term is another way to raise a
# false alarm — the one error mode that would make the output not worth reading.

# Regimens that mean "no drug is being taken". If the profile says one of these
# and the patient talks about taking something, the two cannot both be true.
NO_TREATMENT_REGIMENS = (
    "watch and wait",
    "watchful waiting",
    "active surveillance",
    "observation",
    "no treatment",
    "untreated",
)

# The nouns that make a sentence be about medication.
_MED_NOUN = (
    r"(?:medications?|meds|pills?|tablets?|treatments?|therapy|chemo"
    r"|chemotherapy|drugs|prescriptions?|infusions?)"
)

# The drugs the two diagnoses in this corpus actually use. A named list rather
# than a clever rule, because the rule that catches `emtricitabine` also catches
# `medicine`, `routine` and `determine`.
KNOWN_DRUGS = frozenset({
    # CLL
    "ibrutinib", "acalabrutinib", "zanubrutinib", "venetoclax", "rituximab",
    "obinutuzumab", "ofatumumab", "idelalisib", "duvelisib", "fludarabine",
    "cyclophosphamide", "bendamustine", "chlorambucil",
    # HIV
    "tenofovir", "emtricitabine", "dolutegravir", "bictegravir", "efavirenz",
    "abacavir", "lamivudine", "zidovudine", "ritonavir", "darunavir",
    "raltegravir", "rilpivirine", "doravirine", "cabotegravir",
    "truvada", "biktarvy", "descovy", "triumeq", "atripla",
    # general
    "prednisone", "prednisolone", "dexamethasone", "allopurinol",
})

# For a drug nobody listed — invented or simply newer than this file. Only the
# suffixes with no ordinary-English collisions: `-nib`, `-mab` and `-vir` end
# essentially nothing else at this length. `-ine` and `-cin` are left out on
# purpose; the named list above carries the real ones.
_DRUG_SUFFIX = re.compile(r"\b([A-Za-z]{4,}(?:nib|mab|vir))\b", re.IGNORECASE)

_KNOWN_DRUG = re.compile(
    r"\b(" + "|".join(sorted(KNOWN_DRUGS)) + r")\b", re.IGNORECASE
)

# Either kind of drug token, for the treatment patterns below.
_DRUG_TOKEN = (
    r"(?:" + "|".join(sorted(KNOWN_DRUGS)) + r"|[A-Za-z]{4,}(?:nib|mab|vir))"
)

# First person, present tense, about taking something. Every branch is anchored
# on either a medication noun or an actual drug token: a bare "I'm on" also
# starts "I'm on my way", and one false alarm is enough to make the whole output
# ignored.
#
# The drug branches are what catch "I'm taking ibrutinib", which names no
# medication noun at all. They can only fire on a no-treatment profile, where
# any drug is already a contradiction, so they cannot punish a treated patient
# for naming their own regimen correctly.
_TAKING = re.compile(
    r"\b(?:"
    r"i(?:'m|\s+am)?\s+(?:currently\s+)?taking\s+(?:\w+\s+){0,2}" + _MED_NOUN
    + r"|i(?:'m|\s+am)\s+(?:currently\s+)?on\s+(?:\w+\s+){0,2}" + _MED_NOUN
    + r"|i(?:'m|\s+am)?\s+(?:currently\s+)?taking\s+" + _DRUG_TOKEN
    + r"|i(?:'m|\s+am)\s+(?:currently\s+)?on\s+" + _DRUG_TOKEN
    + r"|(?:started|been|put)\s+(?:me\s+)?on\s+" + _DRUG_TOKEN
    + r"|my\s+(?:daily\s+|new\s+)?" + _MED_NOUN
    + r"|prescribed\s+(?:me|to\s+me)\b"
    + r"|side[- ]effects?\s+(?:of|from)\s+(?:my|the)\s+(?:\w+\s+){0,2}" + _MED_NOUN
    + r"|(?:started|been)\s+on\s+(?:\w+\s+){0,2}" + _MED_NOUN
    + r")",
    re.IGNORECASE,
)

# A short, high-signal symptom list. Soft findings only.
SYMPTOM_TERMS = (
    "headache", "headaches", "migraine", "migraines",
    "nausea", "nauseous", "vomiting", "vomit",
    "fever", "fevers", "chills",
    "night sweats", "sweating",
    "rash", "rashes", "itching",
    "diarrhoea", "diarrhea", "constipation",
    "dizziness", "dizzy", "fainting",
    "chest pain", "palpitations", "shortness of breath", "breathless",
    "weight loss", "swollen glands", "swollen lymph nodes", "lumps",
    "numbness", "tingling", "blurred vision",
    "insomnia", "fatigue", "tiredness", "exhaustion",
    "joint pain", "back pain", "muscle aches",
)

# Negation inside this many characters before a cue cancels it: "I'm not taking
# anything" must not read as a claim to be taking something.
_NEGATION_WINDOW = 40
_NEGATION = re.compile(
    r"\b(?:not|never|no|n't|without|haven't|don't|doesn't|isn't|aren't|nothing|none)\b",
    re.IGNORECASE,
)

# Where a negation stops reaching. Sentence enders and contrastive conjunctions
# only — see _negated for why the comma is left out.
_CLAUSE_BREAK = re.compile(
    r"[.;!?]|\b(?:but|however|although|though|yet|then|until|before)\b",
    re.IGNORECASE,
)

# Units that make a number not an age. Without this "I'm 45 minutes late" and
# "I'm 20 weeks into this" both read as a stated age — and once an absent
# profile age also counts as a finding, those would fire on every profile
# instead of only on the ones that disagree.
_NOT_AN_AGE = (
    r"(?:minutes?|mins?|hours?|days?|weeks?|months?|kg|kilos?|pounds?|lbs?"
    r"|stone|percent|%|degrees?|miles?|km|times?|steps?)"
)

_AGE = re.compile(
    r"\bi(?:'m|\s+am)\s+(\d{1,3})(?:\s+years?\s+old)?\b(?!\s*" + _NOT_AN_AGE + r")",
    re.IGNORECASE,
)

# Outside this range it is not a patient's age, whatever the sentence looked like.
_PLAUSIBLE_AGE = range(18, 101)

_SPACE = re.compile(r"\s+")


def _normalise(text: str) -> str:
    return _SPACE.sub(" ", text or "").strip().casefold()


def _negated(text: str, at: int) -> bool:
    """Is there a negation just before this position, in the same clause?

    The window alone is not enough. In "no nausea at first, but then the nausea
    got bad" the second mention sits 33 characters after the first denial, so a
    fixed lookback drags in a "no" that stopped applying at "but" — and the real
    claim goes unreported.

    Only strong breaks count: sentence enders and contrastive conjunctions. A
    comma is deliberately not one, because "I take nothing, no pills, no
    tablets" is a single denial and splitting it would flag its own items.
    """
    window = text[max(0, at - _NEGATION_WINDOW):at]

    breaks = list(_CLAUSE_BREAK.finditer(window))
    if breaks:
        window = window[breaks[-1].end():]

    return bool(_NEGATION.search(window))


# ── One finding ──────────────────────────────


@dataclass
class Finding:
    """One thing the patient said that the profile does not support."""

    severity: str
    kind: str            # treatment | drug | symptom | age
    claim: str           # the term or phrase that triggered it
    turn: int
    quote: str           # the sentence it sits in, so a human can judge it

    def as_dict(self) -> Dict[str, Any]:
        return {"severity": self.severity, "kind": self.kind, "claim": self.claim,
                "turn": self.turn, "quote": self.quote}


def _symptom_matches(folded: str, facts: "ProfileFacts") -> List[tuple]:
    """(position, term) for each unsupported symptom, longest match winning.

    **Every occurrence is scanned, not just the first.** A denial earlier in the
    same turn used to hide a real mention later in it — "no nausea at first, but
    then the nausea got bad" reported nothing, because `find` stopped at the
    negated one.

    **Still one finding per symptom per turn.** The scan stops at the first
    occurrence that is not negated. Reporting the same symptom three times
    because the patient repeated it measures how much they said it, not how many
    unsupported things they said, and the finding count is what the rate is
    built on.

    The list carries singulars and plurals, and `headache` is inside
    `headaches`, so overlapping matches are resolved longest-first.
    """
    spans = []
    for term in SYMPTOM_TERMS:
        if term in facts.symptoms or term in facts.everything:
            continue

        start = folded.find(term)
        while start != -1:
            if not _negated(folded, start):
                spans.append((start, start + len(term), term))
                break
            start = folded.find(term, start + 1)

    spans.sort(key=lambda span: (span[0], -(span[1] - span[0])))

    kept: List[tuple] = []
    for start, end, term in spans:
        if any(start < k_end and k_start < end for k_start, k_end, _ in kept):
            continue
        kept.append((start, end, term))

    return [(start, term) for start, _, term in kept]


def _sentence_around(text: str, position: int) -> str:
    """Enough context to judge the finding without opening the transcript."""
    start = max(text.rfind(".", 0, position), text.rfind("?", 0, position),
                text.rfind("!", 0, position)) + 1
    end = min((p for p in (text.find(".", position), text.find("?", position),
                           text.find("!", position)) if p != -1), default=len(text))
    return text[start:end + 1].strip()


# ── What the profile supports ────────────────


@dataclass
class ProfileFacts:
    """The clinical facts, flattened into what a string check can use."""

    patient_id: str
    regimen: str
    on_treatment: bool
    symptoms: str        # the profile's symptom text, normalised, for substring tests
    everything: str      # the whole disease_profile as one normalised blob
    age: Optional[int]


def profile_facts(profile: Dict[str, Any]) -> ProfileFacts:
    """`belief_profile` is deliberately not read: beliefs are what the doctor is
    inferring, and a patient expressing one is doing its job, not fabricating."""
    disease = profile.get("disease_profile") or {}
    regimen = _normalise(str(disease.get("treatment_regimen") or ""))
    symptoms = _normalise(" ; ".join(str(s) for s in (disease.get("key_symptoms") or [])))
    demographics = disease.get("demographics") or {}

    age = demographics.get("age")
    return ProfileFacts(
        patient_id=profile.get("patient_id", "unknown"),
        regimen=regimen,
        on_treatment=not any(phrase in regimen for phrase in NO_TREATMENT_REGIMENS),
        symptoms=symptoms,
        everything=_normalise(json.dumps(disease)),
        age=age if isinstance(age, int) else None,
    )


# ── Checking one turn ────────────────────────


def check_turn(text: str, facts: ProfileFacts, turn: int) -> List[Finding]:
    """Every finding in one patient utterance, in the order it was said."""
    found: List[tuple] = []          # (position, Finding), sorted at the end

    # Case-folded but NOT whitespace-collapsed: `_normalise` shortens the text
    # wherever it squeezes a double space, and every offset taken from it then
    # points a little to the left in `text` — which is what the quote is cut
    # from. Folding alone keeps the two strings in step.
    folded = text.casefold()

    # 1. A drug the profile never names. Unsupported whatever the regimen — a
    #    patient on treatment should not invent a second drug — and a
    #    contradiction outright when the regimen says no drug at all.
    #
    #    Checked before the treatment claim so that "I'm taking ibrutinib"
    #    yields one finding naming the drug, not two saying the same thing.
    drug_spans: List[tuple] = []
    seen_drugs = set()
    for pattern in (_KNOWN_DRUG, _DRUG_SUFFIX):
        for match in pattern.finditer(text):
            term = match.group(1)
            folded_term = term.casefold()      # not `folded`: that is the turn
            if folded_term in facts.everything:
                continue
            drug_spans.append((match.start(), match.end()))
            if folded_term in seen_drugs:
                continue
            seen_drugs.add(folded_term)
            found.append((match.start(), Finding(
                CONTRADICTION if not facts.on_treatment else UNSUPPORTED,
                "drug", term, turn, _sentence_around(text, match.start()),
            )))

    # 2. Claiming treatment when the profile says there is none. The failure
    #    that started this module (s51-nb-1 r1).
    if not facts.on_treatment:
        for match in _TAKING.finditer(text):
            if _negated(text, match.start()):
                continue
            # The drug branches of _TAKING overlap the drug finding above, which
            # names the drug and is therefore the more useful of the two.
            if any(match.start() < end and start < match.end()
                   for start, end in drug_spans):
                continue
            found.append((match.start(), Finding(
                CONTRADICTION, "treatment", match.group(0).strip(), turn,
                _sentence_around(text, match.start()),
            )))

    # 3. A symptom the profile does not list. Soft: elaboration is in character,
    #    and only a human can tell it from invention.
    for position, term in _symptom_matches(folded, facts):
        found.append((position, Finding(
            UNSUPPORTED, "symptom", term, turn, _sentence_around(text, position),
        )))

    # 4. A stated age the profile does not support — either because it says a
    #    different one, or because it states none at all. An age is a hard
    #    clinical fact, so inventing one is the same class of failure as
    #    inventing a drug, not the soft class.
    for match in _AGE.finditer(text):
        stated = int(match.group(1))
        if stated not in _PLAUSIBLE_AGE or stated == facts.age:
            continue
        claim = (f"{stated} (profile: {facts.age})" if facts.age is not None
                 else f"{stated} (profile states no age)")
        found.append((match.start(), Finding(
            CONTRADICTION, "age", claim, turn, _sentence_around(text, match.start()),
        )))

    return [finding for _, finding in sorted(found, key=lambda pair: pair[0])]


# ── One consultation ─────────────────────────


@dataclass
class RunFidelity:
    run: str
    patient_id: str
    repeat: int
    findings: List[Finding] = field(default_factory=list)

    @property
    def contradictions(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == CONTRADICTION]

    @property
    def unsupported(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == UNSUPPORTED]

    @property
    def passed(self) -> bool:
        """Strict: nothing unsupported at all, which is what the QC asks for."""
        return not self.findings

    @property
    def passed_strict_contradictions(self) -> bool:
        """The reading that survives a false alarm in the soft list."""
        return not self.contradictions


def read_consultation(run_dir: Path, profile: Dict[str, Any], repeat: int) -> Optional[RunFidelity]:
    """One consultation against its own profile, or None with no transcript."""
    path = run_dir / "transcript.json"
    if not path.exists():
        return None

    facts = profile_facts(profile)
    conversation = json.loads(path.read_text()).get("conversation") or []

    findings = [
        finding
        for line in conversation
        if line.get("role") == "patient"
        for finding in check_turn(line.get("content") or "", facts, line.get("turn", 0))
    ]

    return RunFidelity(run_dir.name, facts.patient_id, repeat, findings)


# ── The batch ────────────────────────────────


@dataclass
class BatchFidelity:
    batch_id: str
    runs: List[RunFidelity]

    @property
    def fidelity_rate(self) -> Optional[float]:
        """Runs with no unsupported claim at all, over runs read.

        An upper bound on fidelity, not a measurement — see the module header.
        """
        if not self.runs:
            return None
        return round(sum(1 for r in self.runs if r.passed) / len(self.runs), 3)

    @property
    def contradiction_free_rate(self) -> Optional[float]:
        """The same, counting only the hard findings."""
        if not self.runs:
            return None
        clean = sum(1 for r in self.runs if r.passed_strict_contradictions)
        return round(clean / len(self.runs), 3)


def read_batch(batch: Path, corpus: Dict[str, Dict[str, Any]]) -> BatchFidelity:
    """Every consultation of a batch against patients/*.json.

    The index is the directory, for the reason coverage.py gives: a batch
    resumed after a walltime kill rewrites batch.json with that launch alone.
    """
    if not batch.is_dir():
        raise SystemExit(f"{batch}: no such directory")

    runs = []
    for path in sorted(batch.glob("*/transcript.json")):
        name = path.parent.name
        patient_id, _, repeat = name.rpartition("-r")
        patient_id = patient_id or name

        profile = corpus.get(patient_id)
        if profile is None:
            raise SystemExit(
                f"{name}: no profile for {patient_id!r} in the corpus. "
                f"Fidelity is a check against the profile, so it cannot skip one."
            )

        fidelity = read_consultation(
            path.parent, profile, int(repeat) if repeat.isdigit() else 1
        )
        if fidelity is not None:
            runs.append(fidelity)

    if not runs:
        raise SystemExit(f"{batch}: no transcript.json found to check")

    return BatchFidelity(batch.name, runs)

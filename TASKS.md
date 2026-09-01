# AHEAD — Doctor/Patient simulation: what each task is

**Project aim.** To find out whether a clinical LLM can **infer** beliefs about
illness (B-IPQ) and treatment (BMQ) from a natural consultation, using
Leventhal's CSM and Horne's NCF as the theoretical lens. The questionnaire is the
yardstick, **not the script**: it is not administered psychometrically.

**Architecture decision.** Reimplement in Python/LangGraph the inference paradigm
of the Ruby arm, with the execution control and the evaluation layer of the
Python arm.

- Ruby (`modified_versions/ruby_version`) — the right paradigm (free
  conversation, inference), fragile execution. Kept as a reference.
- Python (`python_version/ahead_agent-bmq-integration`) — the wrong paradigm
  (elicitation: it administers the questions literally), but its `evaluation.py`
  and its `causes/` module are paradigm-agnostic and get ported.
- Ruby's old measurement layer is retired in `ruby_version/save/`.

---

## How to read this

Three documents, one job each. **If you are looking for what to do now, this is
not it.**

| | |
|---|---|
| **TASKS.md** (here) | **what** each task is and why it exists. Definitions, no status |
| [STATUS.md](STATUS.md) | **what state** each one is in |
| [PENDING.md](PENDING.md) | **what to do now**, in order, and what blocks it |

There are no ticked boxes here on purpose: status has a single home, and
duplicating it is how the two go out of sync. Closed tasks are kept to one line
so the open ones stand out.

---

## Phase 0 — Foundation

**Closed:** 0.1 new package · 0.2 git · 0.4 provenance per run · 0.5 shared
config with inheritance · 0.6 the corpus keeps the original numbers.

**0.3 — Same profiles in both arms.** ⛔ Retired: the live corpus became CK's, so
the two arms no longer score the same thing and there is nothing to verify. Two
requirements replace it, both in `test_corpus.py`: that `patients/` be
reproducible from `sintetic_patients/patientsCK/`, because without that the
ground truth has no origin; and that the previous corpus stay frozen in
`sintetic_patients/patients_version1/`, because that is what all of
`runs/historic/` was scored against.

---

## Phase 1 — Agent architecture

**Closed:** 1.1 two-agent graph · 1.2 different models and isolation · 1.3 turns
not laid out in advance · 1.4 sequential execution · 1.5 the doctor ends it ·
1.6 prompts as external markdown · 1.7 the skills mechanism · 1.9 patient
profiles · 1.11 scoring at the end · 1.13 a report every time, validated, with a
retry · 1.14 doctor styles ported.

### 1.8 — External definitions as a resource

CSM, NCF, the dimensions and the clinical terminology available to the doctor as
a context resource, instead of inside the prompt.

**The missing decision is not technical: always inject them, or retrieve them
when needed.** The interface is done and `resources/` is empty. Deferred on
purpose.

### 1.10 — Free questions that cover every dimension

The doctor phrases things its own way, from the dimensions, without reciting the
items. And it has to reach **all** of them, including `general_harm`,
`general_overuse` and `causes`, which are the ones that get left out.

Today it fails, and **it cannot be closed without coverage**: when a dimension
comes back NA there is no way to tell "did not ask" from "asked and the patient
did not answer".

### 1.12 — Ambiguity-driven probing

⛔ **The baseline is left with no mechanism, and that is deliberate.** Asking
again when the evidence is insufficient would be the right thing — the old
routing fired on reply length, so a long vague answer went straight to scoring —
but forcing coverage live brings back the questionnaire that 1.3 took out of the
code, and inflates the result. The doctor probes what it wants and coverage is
audited afterwards.

What does exist is two independent switches to measure it as an intervention:
`features.coverage_hint` (`off` | `show`) and `features.working_notes`.

---

## Phase 2 — Traceable scoring

**Closed:** 2.1 evidence before the number · 2.2 intermediate anchors ·
2.3 declared confidence.

What 2.1 and 2.2 established, still in force:

- The order `verbatim quote → reasoning → score` **is also the experiment** that
  answers whether the bias comes from justifying after the fact. In Ruby the
  table was `Score | Rationale`, i.e. decorative justification; the Python scorer
  returned the bare number.
- The doctor's rubric was written **from clinical criteria, not by inverting the
  patient's**. Copying it would rebuild the mirror that 5.5 exists to measure.

### 2.4 — Empirical confidence

The spread of the score across N runs of the same patient. It does not rely on
the model's introspection.

**Run budget:** N=10 for the baseline, which is the one that gets published and
the one this metric comes from; N=5 to screen Phase 6 interventions, going up to
10 only for whichever one survives. Below N=5 the spread means nothing.

**It moves into coverage** (PENDING.md). `reproducibility.py` was deleted.

### 2.5 — Discrimination between patients

The variance of the mean score *between* patients, per dimension.

**It must be reported alongside 2.4**, because low spread does not mean good
inference: a degenerate scorer is maximally consistent and completely useless.
Read together: low spread + high discrimination = real inference; low spread +
low discrimination = a degenerate prior in disguise.

### 2.6 — Validate declared confidence against empirical

Does what the model says it knows predict the spread actually observed? If not,
the model does not know when it does not know, **and that is a result in
itself**. Declared confidence is an object of study, not an input.

**It moves into coverage.** It depends on 2.4 existing first.

---

## Phase 3 — Corpus integrity

**Closed:** 3.1 transport retries.

### 3.2 — Coverage and quality module

Walk each transcript and mark, per dimension: was there a probe? was there an
answer? was evidence cited? The output is a dimension × patient map where the
holes are visible at a glance.

It is what makes 1.10 visible, and **the module 2.4 and 2.6 now live in**.

### 3.3 — Reproducibility

The same patient and the same prompt N times, measuring the divergence of the
conversations and of the scores. It is the source of 2.4, so it goes inside the
same thing.

### 3.4 — Usable-corpus gate

A corpus is only declared usable if it passes 3.1 and 3.2. **Do not analyse a
corpus with holes**: infrastructure failures get confused with inference
failures.

### 3.5 — Patient fidelity

Audit whether the patient played its profile: contradictions against
`disease_profile`, with no model involved. It runs over an existing batch and
needs no queue.

Done on 2026-08-31 (`ahead_agent/fidelity.py` + `fidel.py`). Two design points
the task did not state and that are now part of it:

- **It goes in its own module because it reads the truth.** `coverage.py` is
  forbidden from opening `patients/*.json` — that is what stops the 3.2 map from
  seeing the answer — and fidelity is precisely a check *against* that answer.
  Putting them together would contaminate 3.2.
- **`belief_profile` is not read, only `disease_profile`.** A patient expressing
  a belief is acting out its profile, which is its job; checking beliefs here
  would penalise the behaviour the whole simulation exists to produce.

What it does **not** deliver: a measurement. It compares named entities —
regimen, drug, symptom, age — not meaning, so its rate is an **upper bound** on
fidelity. Every leak falls on the side of a pass. It is used to read the runs
that fail, never to believe the ones that pass.

---

## Phase 4 — Evaluation

**Closed:** 4.1 ground truth from `patients/*.json` only · 4.2 port of
`evaluation.py` · 4.4 NA instead of a fallback · 4.5 per-dimension bias ·
4.7 `evaluate.py`.

What they established, still in force:

- **4.1** The mistake that was retired was comparing against an earlier run
  labelled `reference`, which were inferred scores and not truth. That measures
  drift between runs, not accuracy.
- **4.4** An NA is never a default value: it is excluded from the MAE and
  reported as coverage. The old scorer put in a 5 when the JSON did not parse,
  and those invented values counted as hits.
- **4.5** The bias is **per dimension, not global**: inflated symptom burden and
  deflated control. A global correction would make the control items worse.
- **4.7** Evaluation is post-processing and lives apart, so it can run over
  batches from any arm. `score_causes` is called from there and **never from a
  node** — in the original arm it lived inside the graph, which means whatever
  was scoring could see the truth.

### 4.3 — Port `causes/`

Ported whole and **never run**. Two things to decide when exercising it:

- **The 0.72 threshold is justified nowhere.** It appears identically in all four
  copies of the code, with no experiment, no calibration set and no citation.
  `coverage_score` **is** the fraction of true causes that reach that cut, so the
  metric rests entirely on an inherited constant nobody explained. It is not
  wrong; it is indefensible as it stands. **The sweep is free**: as soon as
  `--causes` runs once, the similarities are stored and moving the cut costs not
  one extra call. Out comes either a defensible value or the finding that
  coverage is highly sensitive to the threshold, which is also a result. The
  threshold and the embedding model go together, because the distribution of
  cosines changes with the model.
- **`models.embed` is no longer the problem this document described.** `hpc.yaml`
  pins `nomic-embed-text`, which is in the Ollama store and which this code can
  reach. The earlier description — an unreachable HuggingFace model — was left
  here after the profile was fixed, and is corrected on 2026-08-31. What still
  does not exist is the **validation**: if the model is ever missing, "absent"
  and "unreachable" will still come out the same and silently degrade the metric
  to category overlap, halfway through a batch instead of at profile load.

**Count the cost:** classifying each cause is a call to the model, both the
inferred ones and the profile's. That is why it is not called from inside a run,
and why the ground truth's classification is worth caching, since it is the same
across every run of the same patient.

### 4.6 — Provisional targets

MAE thresholds inherited from the report, **presented as a reference and not as
pass/fail**, until 5.3 tells us how much two experts differ from each other. If
they differ by more than the threshold, the threshold is not reachable and has to
be reformulated.

There is no yardstick today either: it comes out of coverage.

---

## Phase 5 — Comparison arms

**None of them delivers a verdict.** They are presented alongside the inference
arm as reference lines, to place the result. Deciding whether a number is good or
bad is premature and falls outside this phase.

- **5.1 Blind floor** — scoring from diagnosis and demographics alone, with no
  conversation: what gets right by clinical priors.
- **5.2 Elicitation ceiling** — the Python arm asking directly: what is recovered
  when the patient says it explicitly.
- **5.3 Human reference** — two or three clinicians scoring the same transcripts.
  They give how much is genuinely inferable and their agreement with each other,
  which is the realistic ceiling of the task. A subset is enough, and only once
  the corpus is clean.
- **5.4 Artefact tests** — checking that the number comes from the conversation
  and not from the setup. Cheap: they re-score an existing corpus, with no new
  runs. **Crossed transcript**, scoring one patient with another's transcript; if
  the MAE does not degrade, nothing is being read. **Evidence ablation**,
  removing the quotes the doctor itself alleged and re-scoring; if the number
  does not move, the evidence was decorative. It is the direct test of whether
  the justification is written after the fact.
- **5.5 Arm with no behavioural cues** — `PATIENT.md` says how to express a high
  score and `DOCTOR.md` says what to listen for: **the same table mirrored**.
  Part of the accuracy is decoding a code we put into both prompts, not clinical
  inference. The control gives the patient only the number and a narrative
  description, and the difference measures the size of the artefact.

---

## Phase 6 — Interventions on the agent

One variable per run, with a full run in between. Only after 3.4 and Phase 4.

- **6.1** The effect of 2.1 (evidence before the number) on the bias.
- **6.2** The effect of 2.2 (intermediate anchors) on bias and mid-range
  profiles.
- **6.3** Per-dimension calibration with few-shot, using the bias from 4.5. Only
  after 6.1 and 6.2: otherwise you correct numbers without correcting the
  mechanism.
- **6.4** The effect of the two switches of 1.12, **one per run**.
  `coverage_hint: show` measures whether showing it the holes makes it ask about
  what the baseline never touches; `working_notes: true`, the effect of writing
  conclusions as it goes. Neither is comparable with the baseline on accuracy:
  both do some of the doctor's work in advance.
- **6.5** **Compare the styles against each other.** The loading is already done
  (1.14), so what remains is the comparison. The registry's `hypotheses` are
  inherited as questions, never as results: nobody has run anything behind them.
- **6.6** **Does the doctor revise?** With `working_notes: true`, two notes on the
  same dimension in different turns are a dated change of mind. The whole
  architecture of scoring at the end rests on late information being able to
  correct an early impression, and **there is not one observation of it
  happening**. If it almost never revises, 1.11 is not buying what we think.

---

## Phase 7 — Closing

- **7.1 Extend the corpus** — mid-range profiles and patients who hide emotions.
  Only once the pipeline is reliable.

  **The band-floor rule.** If a new profile brings a B-IPQ of 0 or a BMQ at the
  minimum, the floor band is added **in the same commit** as the profile. Today
  the bands start higher and `_band_for` returns the first whose ceiling is not
  exceeded, so a 0 would be played as a 2: the patient acts a 2, the doctor
  correctly infers 2, and the evaluation records it as an error. It would be an
  error manufactured by the table, exactly the artefact 5.5 measures. It also
  clashes with the doctor's rubric, which says a 0 is a finding and needs
  evidence like any other number. It is not a live problem — the current corpus
  has no 0 — which is why the text is not being touched now.

- **7.2 Rewrite section 6 of the report** with the real results. In particular
  the part describing a global overestimation when what there is is asymmetry per
  dimension (4.5).

---

## Phase 8 — Interface: API and frontend

Independent of phases 5–7. The entry condition is that the report contract be
stable, i.e. when Phase 4 closes.

The current frontend **is not adapted, it is inverted**: today it does not
display the consultation, it drives it — it walks the questions by index and
decides whether to re-ask based on reply length. The presentational part does get
ported.

- **8.1** **Isolation at the HTTP boundary.** Today the patient endpoint returns
  the whole profile to the browser, the client resends it every turn and reads
  the ground truth's causes to pass them to the scorer. In other words: **the
  client holds the truth and shows it to whatever is scoring.** The invariant is
  verified inside the process and does not exist in the API. It goes first
  because it conditions every endpoint.
- **8.2** **Per-turn streaming.** A consultation is several minutes: a request
  that answers at the end leaves the interface mute and gets cut by any proxy.
  Decided: emit each turn as it happens, with the report as the last event.
- **8.3** **`api_server.py`.** Per-exchange scoring disappears; a report endpoint
  replaces it. New: launch a run, and query coverage.
- **8.4** **Port the presentational parts** — bubbles, bars, screens and styles,
  which know nothing of the paradigm. They get copied as they are.
- **8.5** **The client stops driving.** From orchestrator to spectator: it
  launches the consultation and shows the turns as they arrive. Who asks, what
  they ask and when they stop is decided by the doctor inside the graph.
- **8.6** **The questionnaire leaves the client.** The question lists and the
  re-ask thresholds do not come back. The client should not know which dimensions
  exist or how they are scored.
- **8.7** **No progress bar.** Since the scoring happens once and at the end, it
  would sit at zero for the whole consultation and then jump to the total. **It
  is not replaced by another one**: faking progress would suggest a walk through
  the dimensions, which is exactly what this arm does not do.
- **8.8** **The report screen, for the new contract.** Each dimension carries
  evidence with its turn, reasoning, score and confidence. **A quote has to be
  able to take you to the turn it comes from**: that reading is what makes 2.1
  useful, and it is the manual review 5.3 will ask the clinicians for. An NA is
  shown as a hole, never as a zero.
- **8.9** **Tests.** That the patient endpoint's response contains no belief
  value — the invariant at the HTTP boundary. That an NA travels as null. That no
  question list is left in the client.
- **8.10** **The demo, two views of the same run.** One shows the conversation
  and nothing else; the other adds the notes appearing and being revised turn by
  turn. It is a **display switch, not an experimental one**: the doctor behaves
  identically, because it never sees the interface.

- **8.11** **Reconcile which batch is the baseline.** `STATUS.md` treats `e4-1`
  as the live corpus — "the project's first corpus with no holes" — while the
  `runs/historic/` README lists it as superseded, because nothing in that folder
  is comparable with anything after 2026-08-26. Both cannot be true at once.
  **Deferred on purpose on 2026-08-27**: it gets resolved when there is a new
  batch to decide against, not by rewriting documents now. Until then, every
  figure coming out of `e4-1` — including V1's coverage — carries the note that
  it measures a superseded configuration.

  It goes here because it is documentation work and blocks nothing, not because
  it has anything to do with the API. Watch the numbering: **Phase 8** in this
  document is the interface, whereas **Stage 8** in `ARCHITECTURE.md` §8 is the
  interventions. They are not the same thing.

### What exists of Phase 8, and what it is not

`replay_server.py` + `replay_frontend/` (2026-09-01) delivers **8.4 and 8.8 over
runs that already exist**: the presentational layer, and a report screen where
each dimension carries evidence, reasoning, score and confidence, an NA is drawn
as a hole rather than a zero, and every quote jumps to the turn it claims to come
from — crossing turn *and* speaker, because the number alone identifies nobody
(D13).

It is **not** 8.3 and does not attempt it. It reads batches off disk and
generates nothing, so 8.1 does not arise — there is no patient endpoint to leak
through — and 8.2 does not either, since there is no live consultation to stream.
8.5, 8.6 and 8.7 are satisfied by construction rather than by work: with no
elicitation loop there is no orchestrator to invert, no questionnaire to remove
and no progress to fake.

What it adds that the phase did not foresee: **one patient at a time**. Ten
people on screen at once is a corpus summary, and `cover.py` already answers
that question better.

---

## Still to be decided

- Whether external definitions are always injected or retrieved (1.8).
- Whether the elicitation arm (5.2) is kept alive or frozen as a reference.
- Formal external clinical resources as a reference, beyond 1.8. Parked until
  after the September demo.
- **How a change of behaviour is measured without proxies.** See PENDING.md: it
  is what blocks coverage.

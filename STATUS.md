# Status

What is done, and where we drifted from the design.

- **What needs doing** → [PENDING.md](PENDING.md)
- **What each task is** → [TASKS.md](TASKS.md)
- **Where the inherited problems come from** → [INHERITED_ISSUES.md](INHERITED_ISSUES.md)

**No figures, on purpose.** This document says what state each thing is in, not
how large it is. The measurements live in each batch's `evaluation.json`, which
is where they can be checked again.

Key: **✅** done · **◐** measured by hand, with no tool to reproduce it ·
**⚠️** half done, with what is missing beside it · **❌** not started ·
**⛔** decided against for now.

---

## The ground moved on 2026-08-26

Almost nothing from before that date is comparable with what came after:

- **The corpus** is CK's. See 0.3 and D11.
- **The bands**: `concern` and `emotional_response` were separated. The first is
  worry about what is coming, the second the mood right now. Before, both asked
  for unease to be expressed and the doctor could not attribute that behaviour to
  one or the other.
- **The doctor's prompt**, for the second time. There are three hash states, and
  `prompts/reference/DOCTOR_v1.md` is the middle one.
- **`max_turns`** came down.
- **The old runs** are in `runs/historic/`, with a README explaining why they do
  not work as a baseline.

---

## Phase 0 — Foundation

| | | |
|---|---|---|
| 0.1 | New package | ✅ `agents_simulations/` |
| 0.2 | Git | ✅ |
| 0.3 | Same profiles in both arms | ⛔ retired. `patients/` is CK's corpus, so the two arms are no longer comparable patient by patient — a decision, not drift. Two tests stand in its place: that `patients/` reproduces its origin in CK, and that the previous corpus stays frozen in `sintetic_patients/patients_version1/`, because that is what `runs/historic/` was scored against |
| 0.4 | Provenance per run | ✅ `metadata.py`. `features` was added after 0.5, so earlier runs do not record their arm |
| 0.5 | Shared config | ✅ inheritance through `extends:`, chainable, with cycles and missing parents caught. Merged block by block and validated on the merged result. A Phase 6 arm is now a three-line file |
| 0.6 | The corpus keeps the original numbers | ✅ `patients/*.json` stores the fraction as CK wrote it, quoted because it is not a JSON number, and the scale is applied on the way in. `ahead_agent/corpus.py` is the single loader that `main.py`, `run_batch.py` and `evaluate.py` all go through |

## Phase 1 — Agent architecture

| | | |
|---|---|---|
| 1.1 | Graph with two agent nodes | ✅ and the extension point has already been used: `report` |
| 1.2 | Different models, and isolation | ✅ with a test: the patient's profile never reaches the doctor |
| 1.3 | Turns not laid out in advance | ✅ |
| 1.4 | Sequential and coherent | ✅ |
| 1.5 | The doctor ends it | ✅ in `e4-1` no consultation ran out against the cap |
| 1.6 | Prompts as external markdown | ✅ |
| 1.7 | Skills | ✅ composes and hashes. The §5.1 test — two opposite skills give different transcripts — passed on one patient. It has not been done over the whole corpus |
| 1.8 | External definitions as a resource | ⚠️ the interface is ready, `resources/` is empty. **A decision is missing: inject them or retrieve them.** Deferred on purpose |
| 1.9 | Patient profiles | ✅ structure intact. `persona` retired — see D2 |
| 1.10 | Free questions that cover **every** dimension | ❌ **fails.** `general_overuse` comes back NA on part of the corpus and with a number on the rest, with no way to know whether it was ever asked. Coverage makes it visible |
| 1.11 | Scoring at the end | ✅ |
| 1.12 | Ambiguity-driven probing | ⛔ no mechanism in the baseline, on purpose — D3 |
| 1.13 | A report every time, validated, with a retry | ✅ exercised end to end, including giving up when the attempts run out. It had never fired live until 2026-09-01 — see N10 |
| 1.14 | Doctor styles ported | ✅ eight styles plus `good_doctor`, which is what `DOCTOR.md` used to carry inside it in prose. How the doctor talks goes to the prompt, the hypotheses and markers to the registry. The section of the original that said which dimensions would stay empty was discarded, because it would be read by the same agent that later scores them |

## Phase 2 — Traceable scoring

| | | |
|---|---|---|
| 2.1 | Evidence before the number | ✅ in the schema and in the prompt. The experiment that would put it to the test is 5.4, not done |
| 2.2 | Intermediate anchors | ✅ from clinical criteria, without inverting the patient's bands |
| 2.3 | Declared confidence | ✅ emitted and parsed. **It does not calibrate** |
| 2.4 | Empirical confidence | ⚠️ **the tool is complete** in `coverage.py`: `mean` and `sd` per (patient, dimension), `mean_within_patient_sd` as the overall measure, and the per-dimension breakdown. **Since 2026-09-01 there is data**: eight batches with `--repeats 5` over CLL-003 and HIV-005. What is missing is running `cover.py` over them — it never has. Six of the eight will give a number; the two that lost a consultation are down to four readings and come out all nulls |
| 2.5 | Discrimination between patients | ◐ it ranks well and compresses the range. It is not a degenerate scorer. **D12 fixed on 2026-08-31**: the correlation groups by `patient_id` and requires 3 distinct patients, so it no longer counts each repeat as a person |
| 2.6 | Validate declared confidence against empirical | ❌ outside coverage V1 on purpose. Confidence is read and stored, not crossed with anything. It depends on 2.4 giving a number |

## Phase 3 — Corpus integrity

| | | |
|---|---|---|
| 3.1 | Transport retries | ✅ and fired live, all recovered |
| 3.2 | Coverage module | ✅ **V1**: `ahead_agent/coverage.py` + `cover.py`, deterministic, model-free and blind to the truth. It verifies each quote in three separate checks — verbatim, in the named turn, in a patient's line — cross-tabulates score against verified evidence in four states, and flags turns cited by several dimensions. **What it does not do is say whether the doctor asked**: that requires a judgement about language and is deliberately out of scope, so 1.10 stays open |
| 3.3 | Reproducibility | ⚠️ see 2.4: the code is there and the repeats now exist; the post-processing is what is missing |
| 3.4 | Usable-corpus gate | ❌ **it can now be written**, which was what was missing: 3.2 exists, 3.5 exists and `batch.json` gives `stop_reason` |
| 3.5 | Patient fidelity | ✅ `ahead_agent/fidelity.py` + `fidel.py`, 2026-08-31. Deterministic, model-free, and it **does read `patients/*.json`** — the opposite of coverage, which is why they are separate files. Two severities: contradicting the regimen or the age, and an unsupported mention of a drug or symptom. It touches no score. **Its rate is an upper bound, not a measurement**: it reads named entities, so every miss falls on the side of a pass |

## Phase 4 — Evaluation

| | | |
|---|---|---|
| 4.1 | Ground truth from `patients/*.json` only | ✅ |
| 4.2 | Port `evaluation.py` | ✅ the per-dimension arithmetic is intact. New: NA as a value, aggregation across patients, and two correlations with different names, `within_patient_r` and `between_patient_r` |
| 4.3 | Port `causes/` | ⚠️ ported whole, and **never run**: `e4-1` was evaluated without `--causes`. New relative to the original: the method used is recorded in the result, because before it changed metric silently when the embeddings failed. It carries an unjustified threshold and an unreachable `models.embed` in `hpc.yaml` |
| 4.4 | NA instead of a fallback | ✅ verified, never clamped |
| 4.5 | Per-dimension bias | ✅ now a tool, not a script. It reproduces the shape of the inherited bias, with `identity` considerably more inflated and `personal_control` changing sign |
| 4.6 | Provisional targets | ❌ no yardstick to set them against. It comes out of coverage |
| 4.7 | `evaluate.py` | ✅ the entry point that was missing. Pure post-process — no graph, no server — so it works over batches from any arm |

## Phases 5, 6 and 7

Almost entirely unstarted, which is the plan. The two `coverage_hint` arms exist
and are Stage 8 material. One exception:

| | | |
|---|---|---|
| 5.4 | Artefact tests — evidence ablation | ◐ **run for the first time on 2026-08-31**, over 2 consultations of `e4-1`. `ahead_agent/ablation.py` + `rescore.py`: they remove the sentences the doctor cited and re-score in two conditions, `intact` (the control, read cold) and `ablate`. `rescore.py` resumes and survives one fallen consultation. The cross-transcript half of 5.4 is still missing |

---

## The `e4-1` batch

Ten patients, two repeats, `coverage_hint: off`. Every consultation correct and
closed by the doctor, every report parsed first time, and the only incidents were
recovered transport retries.

**It is the project's first corpus with no holes** — the Ruby arm lost a
substantial share of the patient's turns and of the reports.

**Coverage ran over it on 2026-08-27** and it is the first reading of 3.2 on real
data. The figures are in its `coverage.json`, which is where they can be checked
again. Three things that are status rather than measurement:

- The verified-quote rate **matches the one measured by hand**, so two
  independent methods give the same answer.
- **Nothing comes out of 2.4**: `e4-1` has two repeats and three are needed.
- Green on the map means the quote is real and correctly located, **not that it
  belongs to that dimension**. Misclassification is invisible by construction,
  and that is what E2 would measure. `general_overuse` comes back NA in half the
  consultations, which until now was only recorded in the document.

**It lives in `runs/historic/`**, whose README says nothing there is comparable
with anything after 2026-08-26. Either that or this section is out of date: it is
the contradiction of 8.11, deferred on purpose. Until it is resolved, every
`e4-1` figure is reported with the note that it measures a superseded
configuration.

**3.5 passed over it on 2026-08-31**, on a copy outside the repository, and it is
the first time we know whether the patient played its profile. The figures are in
its `fidelity.json`. What is status rather than measurement:

- **Two consultations out of twenty carry a hard contradiction**, and one of them
  is the one already seen by eye in `s51-nb-1` r1: a patient on a `watch and
  wait` regimen talking about its side effects. Two independent methods, the same
  failure.
- **The strict rate is low and one symptom drives it.** `headaches` appears in
  more than half the consultations, across both diagnoses, without any profile
  listing it. That is a fact about `dolphin-llama3`, not about those
  consultations: the patient model uses headache as illness filler. The rate that
  answers "did it invent clinical history?" is the contradiction rate, not the
  strict one.
- **`CLL-001` is among the worst in the corpus and `CLL-003`/`HIV-005` among the
  best.**

Neither 3.2 nor 3.5 is still on the list of things left to write.

---

## The demo matrix, 2026-09-01

Eight batches `<ID>x5-<mode>-<style>-run2` over **CLL-003** and **HIV-005**, the
four arms per patient, five repeats each. They are the first in the project to
reach the `MIN_REPEATS` floor. **No post-processing has run over them yet**:
no fidelity, no coverage, no ablation, no evaluation.

What is already status, read from `batch.json` and from no metric:

- **Gate D does not pass.** 5 consultations ran out against `max_turns` and 2
  fell over, out of 40. See PENDING.md for the per-arm breakdown — it matters
  because all seven incidents land in `narrowly_biomedical` and `show`, and none
  in the other two.
- **The 2 that fell left nothing on disk** and cost the SDs of two whole
  batches. That is N10, now fixed.
- **`general_overuse` and `general_harm` come back NA in all eight.** 1.10 again,
  and this time on the current configuration rather than on `e4-1`.
- Each batch holds **a single patient**, so `between_patient_r` will come back
  `None` in all of them. That is D12 working, not a fault: three people are
  needed. Discrimination needs a wide batch as well.

The suite was recounted the same day: **321 test functions**, and the whole thing
green with `AHEAD_GRAPH_TESTS=1`.

---

## Deviations from ARCHITECTURE.md

The paradigm is intact: agentic loop, patient as a tool, verified isolation, NA
without exceptions, evidence before the number.

### Substantive

**D1 — `run_batch.py`.** ✅ resolved, with two guards the design did not ask for:
it aborts on a dirty tree and warns if both temperatures are zero.

**D2 — `persona` retired from the profile.** The design asked for it from the
start so that Phase 7 would not force a schema change later. It was removed by an
explicit decision, so 7.1 will have to reintroduce it.

**D3 — `coverage_hint` defaults to `off`.** No longer a deviation: the design has
been rewritten and describes that arm as the baseline. There was a third mode,
`declare`, retired because the declarations came back in the history and the
doctor could re-read itself: the arm did not isolate what it claimed to isolate.

**D9 — The doctor writes its own report.** It continues the conversation it has
just had, instead of the separate reporter the design listed. A new model reading
the transcript cold would measure something else, and that is exactly the arm of
5.4. Consequence: 2.1 is verified inside the same context that formed the
impression, so the ablation of 5.4 is the only separator.

**D11 — The corpus is CK's, and C1 falls with it.** The BMQ came as a raw sum
over the maximum, which is not even valid JSON. It was not a change of format:
several dimensions carry a different value, and the two `general_*` match on no
patient. C1 falls with it, because CK scores the `specific_*` subscales on
patients without a prescription too, and that was accepted knowingly.
`INHERITED_ISSUES.md` still describes C1 as live.

**D12 — `between_patient_r` counted reports, not patients.** ✅ **Resolved on
2026-08-31.** `evaluate_batch` built one `PatientMetrics` per `report.json`, so in
a batch of 10 × 5 the correlation ran over 50 points with each person counted
five times, and the noise of a person against themselves read as agreement
between people.

Now `_per_patient_pairs` groups by `patient_id`, averages each patient's repeats
and leaves **one point per person**; it applies equally to the overall number and
to each `by_dimension` entry, which carried the same fault. And `MIN_PATIENTS =
3`: below that it returns `None`, because **two points always correlate at ±1**
and publishing that 1.0 would assert a discrimination the batch cannot support.

How it stayed hidden: the three tests that said "three patients" built their
reports with the same `patient_id`, `TEST-001`. They now use distinct ids, and
there is a test pinning the difference — 0.866 grouping correctly against 0.548
grouping reports.

**D13 — A turn is an exchange, not an intervention.** `nodes.py` gives the
doctor's question and the patient's reply **the same number**, because the unit
inherited from the tools paradigm is the `function_call` /
`function_call_output` pair. Ruby numbered nothing, so there is no deviation with
respect to it; the numbering belongs to the Python arm and exists for 2.1 and
8.8. Consequence: `Evidence.turn` **does not identify the speaker**, and turn and
role have to be crossed. It cost a bug in coverage, and it affects 8.8, where the
citation would lead to the exchange and not to the patient's sentence. Whether to
number lines is undecided: changing it forces a change to `REPORT.md` and breaks
comparability by hash.

### Cosmetic

**D4** — The rubric moves from markdown to JSON.
**D5** — `prompts/REPORT.md` is new.
**D6** — A `features` block in the profiles, required and validated.
**D7** — `report_raw.txt` only when the report does not parse.
**D8** — `api_server.py` is missing. See the frontend section.
**D10** — `ahead_agent/api/` is empty, a consequence of D9.

---

## The frontend, if `api_server.py` were added

**It is not reused wholesale, and the reason is substantive: the frontend *is*
the elicitation arm.** `App.tsx` does not display the consultation, it drives it
— it walks the questions by index, decides whether to re-ask based on how short
the answer was, and calls the scorer question by question. The list walk and the
re-ask-by-length rule are still alive in React after being taken out of Python.

| Part | Reusable |
|---|---|
| presentational `components/` — bubbles, bars, screens, styles | ✅ as is |
| `ReportScreen` and `CausesPanel` | ⚠️ the frame works; the content changes, because each dimension now carries evidence, reasoning and confidence, not a loose number |
| `runner/config.ts` — the questionnaire and the thresholds | ❌ the questionnaire does not live in the client |
| `runner/api.ts` — the per-question endpoints | ❌ they disappear |
| `App.tsx` — the loop | ❌ it inverts: from driver to spectator |

So the design falls short when it says `App.tsx` will be *"an adaptation, not a
rewrite"*. The presentational part, yes; the orchestrator is not adapted, it is
replaced, because the orchestrator is now the graph.

**One gap already decided.** The proposed `POST /run` launches a whole
consultation: minutes of wall clock, which do not fit in a request that answers
at the end. It will be done with per-turn streaming, and the report arrives as
the last event. No progress bar: the scoring happens once and at the end, so
there is nothing to count while the conversation is going on.

**What exists instead, since 2026-09-01**, is `replay_server.py` +
`replay_frontend/` — the viewer for consultations that have already been run. It
is not this server and does not replace it: it reads batches off disk, generates
nothing, and shows one patient at a time. The three endpoints that make the
original an elicitation arm are absent rather than stubbed.

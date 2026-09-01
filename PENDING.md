# Open work

What is still open, with what it needs before it can be touched. Cut of
2026-09-01. `TASKS.md` remains the full list by phase; this is only what is live.

---

## The batch that unblocked everything else

**Not any more.** As of 2026-09-01 there are eight batches with `--repeats 5`
over CLL-003 and HIV-005 — the four arms per patient,
`<ID>x5-<mode>-<style>-run2` — plus `s52-nb-1` and `s52-bps-1`. Until today this
document said none existed, and sent you off to repeat work already done.

What is left on them is **post-processing**, not generation: none has been
through `fidel.py`, `cover.py`, `rescore.py` or `evaluate.py`. 2.4 still has no
number, but no longer for want of data.

**Two consultations out of the forty left nothing on disk** — `CLL-003-r5` from
the `show` arm and `HIV-005-r3` from `nb` — both with
`TransportError: report: 3 attempts, last failure was empty reply`. With
`MIN_REPEATS = 5` one lost consultation leaves the batch on four readings and
**all its SDs come out null**, so those two consultations cost two whole batches
of 2.4. They are recovered by relaunching with the same `--run-id`.

**It is five, not three.** `coverage.py` sets `MIN_REPEATS = 5` and below that
returns `sd: None`, which is what TASKS 2.4 asks for — "below N=5 the spread
means nothing". This document said three until 2026-08-31 and was wrong: a batch
of 3 comes out entirely null.

### Gate D does not pass, and it fails in one place

Read over the eight batches on 2026-09-01. Of 40 consultations: 29 clean, 4
closed by the doctor with a recovered retry, **5 exhausted by `max_turns`** and
**2 fallen**.

| arm | turn_cap | failed | of 10 |
|---|---|---|---|
| off + good_doctor | 0 | 0 | 0 |
| off + biopsychosocial | 0 | 0 | 0 |
| off + narrowly_biomedical | 2 | 1 | 3 |
| show + good_doctor | 3 | 1 | 4 |

**All seven incidents are in the two arms that constrain the doctor, and there is
not one in the other two.** In `show` the code is correct —
`test_the_doctor_can_always_close_with_dimensions_open` verifies that the
coverage note compels nothing — and the behaviour changes anyway. A correct
mechanism and an effect on behaviour are different things.

**The `turn_cap` runs are not relaunched**: they are the result, and removing
them would erase from the data exactly the difference between arms. They get
reported. The `failed` ones are relaunched, because they leave nothing to report.

`general_overuse` and `general_harm` come back **NA in all eight batches**, in
every arm and with every style: that is 1.10 confirmed on the current
configuration, not on `e4-1`, which is pre-styles. The `specific_*` NAs on
CLL-003 are correct — it is on watch-and-wait — but CK's ground truth does carry
a number (D11), so its coverage rate drops for being right. Read that before the
MAE.

Execution order for a new batch, with the style arms
`skills/styles/README.md` pinned down:

```bash
git add -A && git commit -m "..."          # run_batch aborts on a dirty tree
. serve_ollama.sh                          # on the compute node, not on login

# Time ONE before committing to forty
time ./venv-hpc/bin/python run_batch.py --profile style-narrowly_biomedical \
     --patients patients/CLL-001.json --repeats 1 --run-id timing-1

./venv-hpc/bin/python run_batch.py --profile style-narrowly_biomedical --repeats 5 --run-id s52-nb-1
./venv-hpc/bin/python run_batch.py --profile style-biopsychosocial     --repeats 5 --run-id s52-bps-1

# Post-processing. Only rescore.py needs the server: it goes before releasing the node.
./venv-hpc/bin/python fidel.py    runs/s52-nb-1 --profile hpc   # 3.5, no server
./venv-hpc/bin/python cover.py    runs/s52-nb-1                 # 3.2 + 2.4, no server
./venv-hpc/bin/python rescore.py  runs/s52-nb-1 --profile hpc   # 5.4, WITH server
./venv-hpc/bin/python evaluate.py runs/s52-nb-1 --profile style-narrowly_biomedical
```

**The order is not decorative.** Fidelity first: if the patient did not play its
profile, neither the coverage nor the MAE of that consultation says anything.
Coverage next, because 3.4 forbids analysing a corpus that has not passed 3.2,
and an MAE over numbers with nothing behind them means nothing. Evaluation last.

**You can go from 2 to 5 without repeating anything.** `run_batch.py` skips what
already exists, so relaunching with `--repeats 5` and **the same `--run-id`**
adds only the missing rounds.

**Gate D before anything else** (`skills/styles/README.md`): every consultation
closes with `stop_reason: doctor`. If one runs out on `max_turns`, the style
changed the stopping rule and everything below inherits the problem.

**Do not compare against `e4-1`**: it is pre-styles, a different prompt hash,
different bands and a different build of the patient model (`hpc.yaml` today
pins `dolphin-llama3:8b-v2.9-q8_0`; `e4-1` ran the untagged `dolphin-llama3`,
which resolves to the Q4). Arms are compared against each other.

---

## Opened on 2026-09-01, in order

### 1. N10 — fixed, and what is left of it

`llm.py` rebuilds the body per attempt and raises the temperature floor after
each empty reply (`RESAMPLE_FLOOR`). See INHERITED_ISSUES N10. **Closed.**

What is left is reading it live: the two consultations that were lost went down
under the previous code, so **no existing run has exercised the new retry**. The
first batch launched will say whether a `retry_temperature` ever appears in an
`events` list, and if it does, whether the second draw came back.

### 2. Relaunch the two fallen consultations

`CLL-003-r5` from the `show` arm and `HIV-005-r3` from `nb`. Same `--run-id`,
which resumes and pays only for what is missing. It is also the experiment: the
conversation regenerates at T=0.7, so the report receives a different transcript.
If it fails in the same place again the cause is the size of the request; if it
comes back, it was the model. **Why the first reply came back empty is not
known** — the exception rises before `write_transcript`, so those two
consultations left nothing to inspect.

### 3. The viewer, and what it lacks

`replay_server.py` + `replay_frontend/` (2026-09-01). Plays back a consultation
that has already been written and then shows the evaluation. No model, no GPU and
no graph: post-processing, like `cover.py`. Tested by hand over 19 batches and
127 consultations.

**The read layer has tests** — `tests/test_replay_server.py`, 20 functions, with
no need for a real batch. **The HTML does not**, and there it stays: the turn by
turn playback, the jump from a quote to its turn and the drawing of NAs are seen
by nothing. Covering them would ask for a headless browser, and that is a new
dependency for a layer that decides no number.

**It shows one patient at a time**, not the whole corpus: `--patient CLL-003`, or
the browser picks one first. Ten people on screen at once is a corpus summary,
and `cover.py` is already there for that.

**It starts slowly** the first time, because it globs `runs/` off GPFS. Pointing
`--runs` at a directory holding only what will be shown avoids it.

Two things it does differently from the original frontend, and both are
decisions rather than oversights: **it does not normalise BMQ onto 0-10** — they
are two scales and are judged separately — and it **draws the NAs instead of
skipping them**, because the original did `if (typeof value !== "number") return
null` and here that would erase the finding of 1.10 from the screen.

---

## The coverage plan, rung by rung

The layered design and which paper backs each layer are in **ARCHITECTURE §13**.
Here, only the order and what blocks each rung.

| | What it is | Blocked by | Cost |
|---|---|---|---|
| **L0** ✅ | quote integrity, ungrounded scores, spread | — | done |
| **F1** ✅ | `fidelity.py` — does the patient play its profile? | — | done 2026-08-31 |
| **L0b** | 2.5 and 2.6 inside coverage | the N≥5 batches finishing | ~35 lines |
| **G** | a labelled set, AIS shape (see §13.5) | **your time**, ~20 min | — |
| **L1** | the ASKED judge — checklist, firm ground | G, and the unset threshold | ~400 lines + rubric |
| **L2** | is the quote of that dimension? — attribution, bad ground | L1, and an NLI model | see §13.4 |

**L0b and G do not depend on each other.** L1 and L2 do come after G, and they
are **not chained to each other**: they are tasks with different reliabilities
and L2 may never be done.

**Before asking for labels**, the two validations that cost no annotation
(§13.6): degrade the doctor on purpose and see whether coverage drops, and
contrast two models against each other. Neither gives accuracy, but they bound it.

### F1 — done, and with what limit

`ahead_agent/fidelity.py` + `fidel.py`. Deterministic, model-free, and it **reads
`patients/*.json`**, which is precisely what `coverage.py` is forbidden to do:
hence two files and not one. It writes `fidelity.json` and touches no score.

Four checks, in two severities:

- **CONTRADICTION** — the profile says otherwise, or says nothing and the patient
  makes it up. Claiming medication on a `watch and wait` regimen, naming a drug
  on that regimen — including "I'm taking ibrutinib", which contains no
  medication noun — or giving an age that is not the profile's **or that the
  profile does not record**. A missing datum is not a blank cheque. It is the
  real failure of `s51-nb-1` r1.
- **UNSUPPORTED** — named and unsupported: an extra drug in an already treated
  patient, a symptom the profile does not list. A real patient volunteers
  detail, so this is read, not failed on by itself.

**What it is not: a measurement.** It reads named entities, not meaning, so a
patient who invents an entire narrative in words that appear on no list passes
clean. **Every detection failure falls on the side of a pass**, and that is why
the rate it emits is an **upper bound** on fidelity and never a score. You read a
run that fails; you do not read a rate that passes.

It is the same trap this document describes below for coverage — a word list
measures vocabulary, not topic. The difference is in the question: "did the
doctor explore the family?" is an open semantic class and a list cannot answer
it; "did the patient assert a drug?" is a closed class of named things, where the
list is precise and its failures fall on the safe side.

---

## Coverage — V1 done, the rest not

`ahead_agent/coverage.py` + `cover.py` exist and run. **3.2 closed**; 2.4 has
code and lacks data; 2.6 not started.

What it does: verifies each quote in three separate checks — verbatim, in the
named turn, in a patient's line — cross-tabulates score against verified evidence
in four states, measures the spread grouping by patient, and flags the turns
cited by several dimensions. Deterministic, model-free, label-free and blind to
the truth. `tools/make_dummy_batch.py` fabricates a batch with a known answer to
exercise it without a server.

**2.4 emits three things since 2026-08-31**, and all three come out in `cover.py`
and in `coverage.json`:

- `mean` and `sd` **per (patient, dimension)**. The mean is given from a single
  score; the sd only from `MIN_REPEATS` up, and never a misleading zero.
- `mean_within_patient_sd` — **the overall consistency measure**: the average of
  the sds computed *inside* each patient. Averaging internal sds is what keeps it
  a consistency measure: pooling the scores first would let the distance
  *between* patients inflate it, and that is 2.5's number, not 2.4's.
- `within_patient_sd_by_dimension` — the actionable half: which dimension the
  doctor is least stable on.

What is missing, in order of cost:

- **2.5 and 2.6** — a few lines each, waiting for 2.4 to give a number. Careful
  with 2.5: `evaluate.py` computes it over **distinct patients**, so with fewer
  than three it returns `None` (D12, fixed on 2026-08-31).
- **ASKED** — saying whether the doctor asked demands a judgement about language:
  a rubric per dimension, a model judging with a mandatory quote, and a
  hand-annotated set to validate it against before letting it decide anything.
  **It is not justified for now**: the first reading over `e4-1` says that almost
  everything the doctor scores it can quote for, so the problem is not a lack of
  grounding. It remains the only thing that would close 1.10.
- **The threshold is unset.** What is missing is declaring, *before* looking at
  the figure, what rate of ungrounded scores would force building that judge.
  Without declaring it first, any result gets rationalised.

### If the judgement is ever automated: NLI, not prompting

A constraint of method, not a preference. It comes from **AttributionBench**
(arXiv 2402.15089, in `papers/`), which turns attribution evaluation into binary
classification over seven datasets and measures from `roberta-large-mnli` to
GPT-4:

- GPT-4 zero-shot with CoT stops at **73.3%** macro-F1 and a fine-tuned GPT-3.5
  at **~80%**. On specialised-domain questions, **below 60%** — and a clinical
  dialogue is a specialised domain.
- **Large LLMs perform below small fine-tuned NLI models.** A 3B FLAN-T5, and on
  some sets the 770M one, beat GPT-4. *"Simply switching stronger models cannot
  significantly improve the performance."*
- **Prompt engineering is not the lever.** Four increasingly elaborate prompts
  moved F1 from 73.2 to 74.0: what changes is the split between false positives
  and negatives, not the accuracy.
- **Adding context makes it worse.** Including the full question and answer did
  not help and sometimes hurt, because the model ends up judging whether the
  answer is useful rather than whether it is supported.
- **11.2%** of their error cases turned out to be failures of the human label,
  not of the model. Labelling a gold set badly is a measured risk, not a
  theoretical one.

Consequences for the design, if it gets there:

1. **Separate two tasks that are not the same.** Saying *whether it was asked* is
   checklist-shaped, and there the French OSCE measures ICC 0.85. Saying *whether
   a quote supports a dimension* is attribution, and there the ceiling is that
   60-80%. They are not chained and they do not deserve the same confidence.
2. For the second, **an NLI model** — `t5_xxl_true_nli_mixture` is the one ALCE
   and this paper use — and not the doctor's model with a careful prompt.
3. **Minimal input**: the quote and the dimension's definition, without the
   transcript around it.
4. Do not spend time refining the prompt expecting accuracy to rise.

`reproducibility.py` **was deleted on 2026-08-27**: a 211-line draft with no
tests, no caller and no review. What 2.4 needed was written inside coverage, from
scratch.

---

## 1.10 — free questions that cover every dimension

That the doctor reaches every dimension by asking freely, without walking a
questionnaire. If it has to be guided, it is elicitation again.

**The gap is now confirmed from the data**, not from the document: coverage read
it over `e4-1` and `general_overuse` comes back NA in half the consultations.

But **it still cannot be closed**, and now we know exactly why. Coverage V1
distinguishes scored from unscored and grounded from ungrounded; what it does not
distinguish is "did not ask" from "asked and the patient did not answer", because
that is written nowhere in the transcript: the question has to be interpreted.
That is what the judge would do, and today building it is not justified.

The only thing V1 offers against this is a bound: the turns cited by several
dimensions say the doctor harvests several dimensions from the same answer, so
most were **not** probed one by one. It is a ceiling on probing, not a
measurement of it.

---

## 4.6 — provisional targets

Fixing what error is acceptable, so a run can be declared good or bad.

Blocked by the same thing as everything else: with noise of 0.99 per dimension
there is nothing to compare against. It comes out of coverage, not before.

---

## Justification → score order

An open suspicion since 2026-08-14, unresolved. `DOCTOR.md` §5.3 asks for a
justification quoting the patient's sentences, to leave an auditable trail. The
doubt is whether the model **picks the number first and then goes looking for the
quote**, in which case the trail looks rigorous and is decorative.

What has been measured: the quotes are real (93-96% verifiable), so there is no
fabrication. The evidence against is about classification — in `run_01/CLL-001`,
`Timeline = 7` is justified with *"waiting for a bomb to go off"*, which exists
but expresses `Concern`. A real quote, the wrong dimension. That is an
indication, not a proof: the order of generation cannot be deduced from the final
text.

**The tool ran for the first time on 2026-08-31.** `ahead_agent/ablation.py` +
`rescore.py` (5.4): they remove from the transcript the sentences the doctor
itself cited and score again in two conditions — `intact` and `ablate` — both
read cold. `intact` is not a separate experiment but the **control**: the
original report was written by the doctor continuing its own consultation (D9),
and a cold reader sees far less, so comparing `ablate` against the original would
measure the ablation and the loss of context at once.

First reading, over 2 consultations of `e4-1` and therefore **validation of the
tool, not a result**: 11 of 21 dimensions returned **exactly the same score**
with their evidence deleted.

### The asymmetry to respect when reading it

`ablate_turn` overlaps in both directions, so a long quote takes with it the
sentences it spans. Measured: **60% and 57% of what the patient said was
removed**, with quotes averaging 21 and 17 words — a sentence — and about four
per dimension. It is not that the algorithm deletes too much: it is twelve
dimensions each citing four sentences, which between them cover almost everything
that was said.

The consequence, and it is the one that decides how this is counted:

- **The ones that did not move count, and count for more.** Removing too much
  only reinforces that direction: more than the evidence was deleted and the
  number stayed the same.
- **The ones that moved are not interpretable.** With 60% gone there is no
  separating "lost its evidence" from "lost the conversation". The count is
  reported, not a conclusion.

Isolating it asks for ablating the evidence **of one dimension at a time** and
re-scoring: twelve times the cost in calls. That is future work, not the demo's.

---

## Future, not now

**1.8 — external definitions as a resource.** Giving the doctor the clinical
definitions of the dimensions as a resource, instead of carrying them inside the
prompt. The interface is done and `resources/` is empty. What is missing is a
decision that is not technical: **inject them into the prompt, or let it retrieve
them when it needs them.** Deferred on purpose.

---

## How to measure a change of behaviour — the underlying question

It came up trying to read the §5.1 gates and applies to coverage just the same.

A gate reader was written and **thrown away on 2026-08-27**, because it rested on
proxies: searching for isolated words measures vocabulary, not topic, and
counting words measures verbosity, not breadth. A doctor can be long-winded and
strictly biomedical; "and at home, how are they coping?" opens family ground
without containing a single word from any list.

Of the four gates, only the `stop_reason` one was not a proxy, because it is a
datum and not an interpretation.

This is not an implementation detail: it is the same problem 3.2 has — deciding
whether the doctor "probed" a dimension — posed over styles instead of over
dimensions. **Until it is resolved, any coverage module inherits the problem.**
Resolving it probably goes through hand-labelling a small sample and contrasting
any automatic instrument against it, before letting it decide anything.

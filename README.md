# AHEAD Agent — inference arm

An automated clinical interview system that uses two LLMs to simulate a
doctor–patient consultation. A **doctor LLM** holds an open conversation with a
**patient LLM** whose behaviour is grounded in a structured patient profile, and
then writes a single report inferring the patient's illness perceptions (B-IPQ)
and medication beliefs (BMQ) from what was actually said. Nothing is administered
as a questionnaire. After the consultation, a set of analysis tools checks whether
the report can be believed, and only then compares it against the profile's
ground truth.

---

## Overview

The B-IPQ is a validated 9-item questionnaire measuring how patients perceive
their illness (consequences, timeline, personal control, emotional impact, etc.).
The BMQ is a 4-subscale questionnaire measuring beliefs about medication —
necessity, concerns, general harm and overuse.

**This arm does not ask those questions.** The questionnaire is the yardstick,
not the script. The doctor converses freely and infers the scores at the end,
which is the whole experiment: whether a clinical LLM can recover a belief
profile from an ordinary conversation.

That single decision is what separates this package from the elicitation arm in
`../python_version/`:

| | Elicitation arm | **This arm** |
|---|---|---|
| Who drives | The code walks a question list by index | The doctor decides what to ask and when to stop |
| When it scores | After every exchange | Once, at the end, over the whole transcript |
| What the patient is | A node in a fixed chain | A **tool** the doctor calls |
| Re-asking | Fires when a reply is under 10 words | No length rule exists |
| What a missing answer becomes | A default value | `NA`, never a number |

Three LLM roles are involved:

- The **doctor LLM** talks to the patient through a tool call, decides when it
  has enough, and then writes the report. It never sees the patient's profile and
  never sees the scoring anchors while it is talking.
- The **patient LLM** answers in character, from a system prompt built out of the
  clinical facts and the ground-truth belief scores.
- An **embedding model** is used only for the open-text causes question.

There is no scorer LLM. The doctor writes its own report, which is a deliberate
choice — a fresh model reading the transcript cold would measure something else,
and that is one of the analysis tools below rather than the pipeline.

---

## Pipeline Logic

### 1. Patient profile

Each patient is a JSON file in `patients/`, with two sections:

- **`disease_profile`** — clinical facts: diagnosis, stage, treatment regimen,
  key symptoms, trajectory and demographics.
- **`belief_profile`** — ground-truth B-IPQ scores (0–10 per dimension) with
  causal beliefs, and BMQ scores (1.0–5.0 per subscale).

`patient_profile.py` converts these into a natural-language system prompt. Each
score maps to a behavioural descriptor — a `consequences` of 9 becomes *"your
illness dominates your life… you bring this up readily"*. **The number itself
never reaches the patient**, only the behaviour it implies, and a dimension with
no score produces no text at all rather than an invented default.

### 2. The consultation loop

The conversation is an agent↔tool loop, not a chain of fixed nodes:

```
                 ┌──────────────────────────────┐
                 │                              │
                 ▼                              │
  START ──► doctor ──(tool_call: speak)──► patient_tool
                 │                              │
                 └──(no tool_call)──► report ──► END
```

**`doctor` node** — an ordinary agent with one tool. Speaking to the patient *is*
a tool call, so the number of turns is not fixed anywhere: the doctor calls the
tool as often as it wants, and stops calling it when it decides it has enough.

**`patient_tool` node** — invokes the patient LLM with its profile and hands the
reply back as a tool result. This is the only place in the codebase that reads
`state["profile"]`, and a test serialises everything sent to the doctor and fails
if a single belief value appears in it.

**`report` node** — always runs on leaving the loop, however the loop ended. If
the report comes back incomplete it is asked for again, up to three attempts;
whatever is still missing stays `NA`.

A turn is an **exchange**, not an intervention: the doctor's question and the
patient's reply carry the same turn number, inherited from the
`function_call`/`function_call_output` pair. This matters when reading citations
— a turn number alone does not identify who spoke.

### 3. The report

The doctor returns one structure, and the field order is the specification:

```python
@dataclass
class DimensionScore:
    dimension: str
    evidence: List[Evidence]   # FIRST — verbatim quotes, each with its turn
    reasoning: str             # SECOND
    score: float | None        # THIRD — None is NA, never a default
    confidence: float          # 0–1, declared by the doctor
```

Evidence comes before the number so the trail can be audited: every score is
supposed to point at something the patient actually said. Whether it really does
is what the analysis tools are for.

**NA policy.** A score is `None` when it cannot be extracted, when the dimension
was never explored, or when the value comes back off its scale. It is never
clamped and never defaulted. An NA is excluded from the MAE, counted in the
coverage rate, and drawn as a hole rather than a zero.

### 4. Causes

The causes question is open text and carries no number, so it stays out of the
MAE. `causes/scorer.py` classifies each inferred and ground-truth cause into one
of seven categories and matches them by cosine similarity, falling back to
category overlap if the embedding model is unavailable — and **recording which
method it used**, because the old module switched silently and a batch could mix
two measures without leaving a trace.

A cause the doctor cannot quote for is dropped at parse time.

---

## The analysis tools

This is what the arm adds beyond running consultations. **A consultation that
produced a number is not the same as a number worth reading**, and each tool
answers a different question about that. All of them are pure post-processing:
they read a batch off disk, none of them touches `report.json`, and each leaves
its own file beside the batch.

| Tool | Question it answers | Needs a server |
|---|---|---|
| `fidel.py` | Did the patient play its profile? | no |
| `cover.py` | Can the report point at what it claims, and does the score hold still across repeats? | no |
| `rescore.py` | Does the number come from the conversation, or from a prior? | **yes** |
| `evaluate.py` | How far is the report from the ground truth? | no |
| `compare.py` | How do two arms differ? | no |
| `replay_server.py` | What actually happened in one consultation? | no |

### `fidel.py` — patient fidelity

A quality-control screen, run **before** any score is read. It compares what the
patient said against its `disease_profile` — regimen, drugs, symptoms, age — and
reports two severities: a **contradiction** (claiming medication on a
watch-and-wait regimen, giving an age the profile does not have) and an
**unsupported mention** (a drug or symptom the profile does not list).

It touches no score. What changes when a run fails here is whether you should
believe it: if the patient did not play its profile, that consultation's coverage
and MAE are measuring the patient's infidelity, not the doctor's inference.

**Its rate is an upper bound, not a measurement.** It reads named entities, not
meaning, so a patient inventing an entire narrative in words that appear on no
list passes clean. Read the runs that fail; do not trust the rate that passes.

### `cover.py` — evidence integrity and consistency

Deterministic, model-free, and **blind to the ground truth** — it is the one tool
forbidden from opening `patients/*.json`, which is what stops its map from being
contaminated by the answer.

It verifies every quote in three separate checks, kept apart on purpose because
they are different findings:

| Check | What it asks |
|---|---|
| verbatim | are these words anywhere in the transcript? |
| named turn | are they in the turn the report said? |
| from the patient | are they in a line the patient spoke? |

It then cross-tabulates score against verified evidence into four states:

|  | verified evidence = 0 | ≥ 1 |
|---|---|---|
| **unscored** | `SILENT` | `CITED_UNSCORED` — it quoted and declined to score |
| **scored** | **`UNGROUNDED`** — a number with nothing behind it | `GROUNDED` |

`UNGROUNDED` is the cell the tool exists for. The output is a dimension × patient
map where holes are visible at a glance.

It also measures **consistency across repeats**: the mean and standard deviation
per (patient, dimension), and one headline number, the average of the SDs
computed *inside* each patient. Averaging internal SDs is what keeps it a
consistency measure — pooling the scores first would let the distance *between*
patients inflate it, and that is a different question.

**Five repeats minimum.** Below `MIN_REPEATS = 5` the SD is reported as `None`,
never as a misleading zero.

### `rescore.py` — evidence ablation

Removes from the transcript the sentences the doctor itself cited, and scores it
again. If the number does not move, the evidence was decorative.

Two conditions, both read cold by a fresh reader:

- **`intact`** — the whole transcript. This is the **control**, not a separate
  experiment: the original report was written by the doctor continuing its own
  consultation, and a cold reader sees far less, so comparing `ablate` against the
  original would measure the ablation and the loss of context at once.
- **`ablate`** — the same transcript with the cited sentences gone.

Whole sentences are removed, never trimmed inside a quote: a mutilated turn stops
reading as human speech and the model would react to the mutilation as well.

**Read the asymmetry.** Removing the cited sentences takes out most of what the
patient said, so the two directions are not equally interpretable: a dimension
that **did not move** is a strong result, because more than its evidence was
deleted and the number held. A dimension that moved cannot be separated from
"lost the conversation".

### `evaluate.py` — accuracy against ground truth

Reads the ground truth from `patients/*.json` and nowhere else. Reports MAE, bias,
band agreement and two correlations that are deliberately named differently:

- **`within_patient_r`** — does this person's profile have the right *shape*?
- **`between_patient_r`** — can the model tell people apart?

They answer different questions and only the second is discrimination. It needs
at least three distinct patients and returns `None` below that, because two
points always correlate at ±1 and publishing that would assert a discrimination
the batch cannot support.

**Bias is reported per dimension, not just globally.** A global figure hides the
shape of the error: the inherited arm reported +0.13 overall with one dimension
at +1.00 and another at −0.77, and a global correction would have made the second
worse.

### `compare.py` — two arms side by side

Gate check, how each arm talked, what dimensions each reached, and the MAE, in
one table. **Arms are compared against each other and never against the budget
declared in their own style file** — every style overshoots its own sentence
count, so the number in the file discriminates nothing.

---

## Evaluation Metrics

### B-IPQ (scale 0–10) and BMQ (scale 1.0–5.0)

The two scales are judged separately and never normalised onto each other. 5.5 is
a legal B-IPQ score and an illegal BMQ one.

| Metric | Description |
|---|---|
| **MAE** | Mean absolute error over the scored dimensions. NAs are excluded, not counted as zero error |
| **Median AE** | Robust to outliers — the typical error |
| **Bias** | Signed drift, per dimension. Positive = the report scored high |
| **Coverage rate** | Scored ÷ (scored + NA). An NA is reported, never silently dropped |
| **Band agreement** | Fraction within the clinical tolerance for that scale |
| **`within_patient_r`** | Is this person's profile the right shape? |
| **`between_patient_r`** | Can the model tell people apart? Needs ≥3 patients |

### From the analysis tools

| Metric | Tool | Description |
|---|---|---|
| **Ungrounded rate** | `cover.py` | Of the scores emitted, how many stand on no verified quote |
| **Quote verification** | `cover.py` | Three rates, kept apart: verbatim, named turn, from the patient |
| **`mean_within_patient_sd`** | `cover.py` | The headline consistency number. Lower = steadier |
| **Contradiction-free rate** | `fidel.py` | Runs with no hard contradiction against the profile |
| **Dimensions unmoved by ablation** | `rescore.py` | Scores that stayed identical with their evidence deleted |

**Why an MAE is never published alone.** A scorer that answers the same thing
every time has perfect consistency and zero discrimination — that is what the
earlier arm did with 67% eights, and its MAE looked reasonable. Consistency and
discrimination are read together or not at all.

---

## Models

| Role | Local profile | HPC profile | Notes |
|---|---|---|---|
| Doctor | `llama3.2` | `glm-4.7-flash:q8_0` | Needs reliable tool calling — without it there is no loop. GLM verified 10/10 well-formed calls |
| Patient | `dolphin-llama3` | `dolphin-llama3:8b-v2.9-q8_0` | Uncensored; responds without safety refusals on health topics |
| Embeddings | `nomic-embed-text` | `nomic-embed-text` | Optional; only for causes matching |

**Doctor and patient are different families on purpose.** Two sizes of the same
model share expression conventions learnt in the same training, and the doctor
could be decoding those conventions rather than inferring.

Models live in the shared store, **not** in `~/.ollama`:

```
/gpfs/projects/bsc02/llm_models/ollama
```

---

## Installation

**Prerequisites:** Python, and access to the shared Ollama store. Nothing is
pulled from the network at run time and no remote endpoint is ever called.

Two virtual environments, because the two machines have different interpreters:

| | Python | Where it works | Used for |
|---|---|---|---|
| `venv-local` | 3.12 | login node | tests, smoke runs, all post-processing, the viewer |
| `venv-hpc` | 3.9 | compute node **only** | batches and anything needing the GPU |

```bash
cd /gpfs/projects/bsc02/bsc064212/AHEAD/use_cases/patient_doctor_agents/agents_simulations

# login node
python3 -m venv venv-local
./venv-local/bin/pip install -r requirements.txt

# compute node — venv-hpc uses the system python3, which is 3.9 there and 3.10
# on login, so it imports nothing outside a compute node
python3 -m venv venv-hpc
./venv-hpc/bin/pip install -r requirements.txt
```

`venv-hpc.lock` records the exact versions that produced the existing runs.

Verify the install:

```bash
./venv-local/bin/python -m pytest tests/ -q     # 509 passed, 2 skipped
./venv-local/bin/python -c "import langgraph; print('ok')"
```

The two skipped tests are the end-to-end ones; `AHEAD_GRAPH_TESTS=1` runs them
too, for 511. **`import langgraph` takes about three minutes off GPFS** — that is
thousands of small files and a metadata cost, not a cold cache, so a slow first
import is expected rather than a sign of trouble.

Start the model server:

```bash
. serve_ollama.sh
```

It exports `OLLAMA_MODELS`, `OLLAMA_URL`, the binary's `PATH` and
`OLLAMA_NUM_PARALLEL`, then starts Ollama on its own port (11500) and lists the
models. The parallelism variable has to be set **before** the server starts: it
is a server setting, not a request option, and left to its default the server
splits the context between slots and truncates in silence.

### The repository

`agents_simulations/` is the repository root, and that is not a preference:
`metadata.py` resolves `REPO_ROOT` as `parents[1]` of the package and shells out
to `git -C` there for the commit each run records.

**`runs/` is tracked**, so the viewer works on a fresh clone. Two things follow.
A batch dirties the tree as it writes, so `run_batch.py` needs `--allow-dirty`
unless the previous one is committed first. And `metadata.py` reads `git_commit`
and `dirty` from `git status --porcelain` under a 60-second timeout — a call its
own comment measures at 24.7 s on GPFS for a tree of twenty files. As the tracked
batches accumulate that call slows down, and on timeout it returns `None` and the
run records no provenance without reporting it. A `git_commit: null` in a fresh
`metadata.json` means the timeout, not a missing repository.

---

## Modes

Two things vary independently, and one run changes one of them.

### Run profile — where and how big

Chosen with `--profile`. `config/base.yaml` holds what is shared; each profile
declares what it inherits and only what changes.

| Profile | Doctor | For |
|---|---|---|
| `local` | `llama3.2` | Smoke tests on the login node. **Never** a published metric |
| `hpc` | `glm-4.7-flash:q8_0` | Baselines and batches, on a compute node |

### Arms — what the doctor gets

Two independent switches, and both go into the run's metadata so a batch can be
identified months later.

**`features.coverage_hint`** — whether the doctor is told which dimensions are
still open:

| Value | What it does |
|---|---|
| `off` | **The baseline.** It is neither asked nor told. Not asking about a dimension is a result, not a fault to prevent |
| `show` | What is still open is handed back on every reply |

**The doctor's style** — a markdown fragment composed onto its prompt. Nine exist
in `skills/styles/`; `good_doctor` is the reference condition, and
`narrowly_biomedical` / `biopsychosocial` are the opposing pair.

The shipped profiles combine them:

| Profile | Hint | Style | What it is |
|---|---|---|---|
| `hpc` | `off` | `good_doctor` | The baseline |
| `hint-show` | `show` | `good_doctor` | Changes the hint |
| `style-narrowly_biomedical` | `off` | `narrowly_biomedical` | Changes the style |
| `style-biopsychosocial` | `off` | `biopsychosocial` | The opposite style |

**Compare the last two against each other**, not against the baseline: they are
the antagonistic pair, and each differs from `hpc` by one thing only.

A style is a file somebody chose, never a code branch, and the composed prompt is
hashed into the run's metadata — which is what lets a change of result be
attributed to a change of prompt rather than to something else.

---

## Execution order

Nine stages. **The order is not decorative**: each one decides whether the next
one means anything. The only thing that needs a live server after the
consultations is `rescore.py`, so it goes before releasing the node.

```
LOGIN NODE — no server
 0 ├─ pytest + cover.py smoke        does the code work?
 1 └─ git commit                     run_batch refuses to start on a dirty tree
                │
                ▼
COMPUTE NODE — server up
 2 ├─ serve_ollama.sh, warm the model
 3 ├─ rescore.py smoke on an old batch    4 calls. Find breakage now, not later
 4 ├─ time ONE consultation               does the batch fit in the walltime?
 5 └─ run_batch.py --repeats 5             the consultations
                │
                ▼
THE GATE — no server
 6 └─ batch.json: every consultation ok, closed by the doctor, events 0
                │              if this fails, nothing below is worth reading
                ▼
ANALYSIS — only rescore needs the server
 7 ├─ fidel.py     did the patient play its profile?
   ├─ cover.py     can the report point at what it claims?  ← the consistency number
   ├─ rescore.py   does the number come from the conversation?   NEEDS SERVER
 8 └─ evaluate.py  the MAE, last
                │
                ▼
 9 └─ compare.py / replay_server.py    read the result
```

Three things about that order that are not style:

- **Fidelity first.** If the patient did not play its profile, neither the
  coverage nor the MAE of that consultation says anything.
- **Coverage before the MAE.** A corpus that has not passed the coverage check is
  not analysed, because an MAE computed over numbers with nothing behind them
  means nothing.
- **Stage 3 before stage 5.** If `rescore.py` is broken, finding out on an old
  batch costs a minute; finding out at stage 7 costs the whole node reservation.

---

## How to Run

### Option A — one consultation

```bash
. serve_ollama.sh
./venv-local/bin/python main.py --patient patients/CLL-003.json --profile local
```

Runs the full loop and writes `runs/<run-id>/` with a transcript and a report.
Useful for smoke tests; **one consultation measures nothing**, because the spread
between identical runs is larger than most effects worth detecting.

### Option B — a batch

The unit of measurement: N repeats × M patients under one configuration.

```bash
salloc -A bsc02 -q acc -p acc --gres=gpu:1 -c 40 -t 4:00:00 srun --export=ALL --pty bash
cd /gpfs/projects/bsc02/bsc064212/AHEAD/use_cases/patient_doctor_agents/agents_simulations

hostname; nvidia-smi -L     # the node, and ONE gpu. Four means you are still on login
. serve_ollama.sh

./venv-hpc/bin/python run_batch.py --profile hpc --repeats 5 --run-id my-batch
```

| Option | What it does |
|---|---|
| `--repeats N` | Consultations per patient. **Use 5** — below that the consistency number is all nulls |
| `--patients ...` | Specific profiles. Default: all ten |
| `--profile` | The arm, from the table above |
| `--run-id` | The batch's name. Default: a timestamp |
| `--allow-dirty` | Run with uncommitted changes. Without it, it refuses to start |

**Relaunching with the same `--run-id` resumes.** It skips consultations that
already have a transcript and pays only for the missing ones, so a batch killed
by the queue is picked up rather than repeated.

The `srun` inside `salloc` is **not optional**: `salloc` reserves the node but
runs the command where you invoked it, and the ACC login nodes also have H100s —
without it everything looks correct while the reserved node does nothing.

### Option C — many batches at once, with GREASY

One line per batch, one node per line. Each line is self-sufficient: it starts its
own Ollama and then runs `run_batch.py`.

```bash
mkdir -p logs greasy_tasks
PATIENTS="CLL-003 HIV-005" ARMS="off show nb bps" REPEATS=5 \
  ./make_greasy_tasks.sh > greasy_tasks/demo.txt
sbatch --nodes=4 submit_greasy.sh greasy_tasks/demo.txt
```

The task file is plain text: read it, cut it, reorder it, keep two lines. **One
task per node** — this Ollama build ships Vulkan, which ignores
`CUDA_VISIBLE_DEVICES`, so two servers on one node can load into the same card and
lose the batch.

GREASY leaves a restart file with whatever failed, and that file is itself a valid
task list.

**GREASY only runs the consultations.** Stages 6 to 9 still happen afterwards.

### The gate, before reading anything

```bash
python3 -c "
import json; b=json.load(open('runs/my-batch/batch.json'))
for c in b['consultations']:
    print(c['run'], c['status'], c.get('stop_reason'), 'events', c.get('events'))"
```

What you want: every consultation `ok`, `stop_reason: doctor`, `events: 0`.

`turn_cap` means the turn limit closed the consultation, not the doctor. **That
is a result, not a fault to fix** — it usually means the arm changed the doctor's
stopping behaviour, and every number downstream inherits that. Report it; do not
relaunch it.

### The analysis, in order

```bash
./venv-local/bin/python fidel.py    runs/my-batch --profile local --quotes
./venv-local/bin/python cover.py    runs/my-batch
./venv-hpc/bin/python  rescore.py   runs/my-batch --profile hpc      # needs the server
./venv-local/bin/python evaluate.py runs/my-batch --profile local
```

And to compare two arms:

```bash
./venv-local/bin/python compare.py runs/arm-nb runs/arm-bps
```

Each leaves a file beside the batch — `fidelity.json`, `coverage.json`,
`report-{intact,ablate}.json` per consultation, `evaluation.json` — and **none of
them modifies `report.json`**.

---

## Viewing results in the browser

```bash
./venv-local/bin/python replay_server.py --patient HIV-005
./venv-local/bin/python replay_server.py --patient CLL-003
./venv-local/bin/python replay_server.py --patient CLL-003 --port 8010   # 8000 taken
```

Those are the two patients with batches on disk. The corpus has ten profiles;
`runs/` holds consultations for these two, so the other eight have nothing to
show and do not appear.

`--patient` belongs to the server, not to the browser: `/api/patients` and
`/api/runs` both apply it, and a server started for one person cannot be talked
out of it from the page. Leave it out to get the picker instead.

Then open `http://127.0.0.1:8000`. Over SSH, forward the port first:

```bash
ssh -L 8000:127.0.0.1:8000 <login-node>
```

Under VS Code's remote extension the port is forwarded for you.

The viewer is **read-only post-processing**: no model, no GPU, no graph. It runs
on the login node while a batch is still in the queue, and it generates nothing —
the transcript on disk is the whole truth.

Three screens:

**1. Pick a patient, then a consultation.** One person at a time. Each button
shows how the consultation ended and how many turns it took; a repeat missing from
a run of five is a consultation that left nothing on disk.

**2. Playback.** The conversation replays turn by turn, with a speed control and
a "show all" button. The header carries the diagnosis, the regimen, how it ended
and — once `fidel.py` has run — whether the patient contradicted its profile.

**3. The report.** Each dimension shows **evidence first, then reasoning, then
the score, then the declared confidence**, in that order, because that is the
order the report is written in. Below it, the comparison against ground truth:
per-dimension error and bias, then MAE, coverage and the correlations.

**The one thing worth clicking is a quote.** It jumps to the turn it claims to
come from, matching turn *and* speaker, and highlights the sentence. If the words
are not there, it says so instead of failing quietly. That is what turns the
audit trail from a claim into something you can check.

Two deliberate differences from the elicitation arm's report screen:

- **The two scales are not mixed.** The original normalised BMQ onto 0–10 to
  reuse one bar; here each is drawn on its own scale, with that scale labelled.
- **NAs are drawn, not skipped.** The original returned early on a non-numeric
  score and the dimension vanished from the screen. Since the dimensions that
  come back NA are exactly the finding worth showing, hiding them would erase the
  result.

Without `--patient` the browser picks a person first. Its first start is slow
because it globs `runs/` off GPFS; point `--runs` at a directory holding only what
you are going to show and it is immediate.

**Expect it to look hung, twice.** Nothing is printed until the whole of `runs/`
has been walked, and the patient filter is applied after the glob rather than
before, so naming one person does not make the wait shorter. Then, once it does
print, uvicorn runs at `log_level="warning"` and never says it started — a silent
terminal after `listening :` is the server working, not a stall. It has not bound
the port until that line appears.

---

## Patient Profiles

Profiles live in `patients/`:

```
patients/
  HIV-001.json  ...  HIV-005.json
  CLL-001.json  ...  CLL-005.json
```

They are generated from `sintetic_patients/patientsCK/` by `normalize_ck.py`, and
a test re-runs that normalisation and requires it to reproduce the files byte for
byte — without it, `patients/` would be a hand-edited directory and the ground
truth would have no provenance.

The BMQ is stored **as it was written**, a raw sum over the subscale maximum
(`"21/25"`), quoted because it is not a JSON number. The 1–5 scale is derived on
load by a single loader, so the three entry points that read the corpus cannot
drift apart.

---

## Project Structure

```
agents_simulations/
├── main.py                  # CLI — one consultation
├── run_batch.py             # N repeats × M patients — the unit of measurement
├── serve_ollama.sh          # start Ollama against the shared model store
│
├── fidel.py                 # 1. did the patient play its profile?
├── cover.py                 # 2. evidence integrity + consistency across repeats
├── rescore.py               # 3. evidence ablation — needs a server
├── evaluate.py              # 4. accuracy against ground truth
├── compare.py               # two arms side by side
├── replay_server.py         # the browser viewer
├── normalize_ck.py          # regenerate patients/ from the CK source
│
├── make_greasy_tasks.sh     # print a GREASY task file, one line per batch
├── submit_greasy.sh         # run a task file across nodes
├── submit_matrix.sh         # patients × 4 arms × N repeats, on one node
│
├── ahead_agent/
│   ├── config.py            # run profiles, dimension names. NO question list
│   ├── corpus.py            # the single loader for patients/*.json
│   ├── state.py             # what is carried between turns
│   ├── graph.py             # the only place that touches StateGraph
│   ├── nodes.py             # doctor_node, patient_tool_node, report_node
│   ├── routing.py           # continue the conversation, or write the report?
│   ├── tools.py             # how the doctor speaks to the patient
│   ├── prompts.py           # compose prompt + skills + resources, and hash them
│   ├── llm.py               # the HTTP client, and what gets retried
│   ├── patient_profile.py   # belief_profile → behaviour
│   ├── metadata.py          # what produced this run: models, hashes, commit, node
│   ├── report.py            # the report schema, parsing, NA policy, gaps
│   ├── evaluation.py        # MAE, bias, bands, the two correlations
│   ├── coverage.py          # quote verification and consistency — truth-blind
│   ├── fidelity.py          # did the patient play its profile — reads the truth
│   ├── ablation.py          # remove the cited sentences and re-score
│   └── causes/              # taxonomy, cosine, greedy matching
│
├── config/
│   ├── base.yaml            # what the profiles share; does not load on its own
│   ├── local.yaml           # small models, smoke scale
│   ├── hpc.yaml             # the baseline arm
│   ├── hint-show.yaml       # coverage_hint: show
│   └── style-*.yaml         # one file per style arm
├── prompts/
│   ├── DOCTOR.md            # the doctor's role — no tone, no style
│   ├── PATIENT.md           # the patient's role
│   ├── REPORT.md            # how the report is requested
│   └── doctor_rubric/       # scoring anchors, doctor side. Never sent during the talk
├── skills/styles/           # nine communication styles, one file each
├── patients/                # profiles + ground truth
├── runs/                    # outputs, one directory per batch
├── replay_frontend/         # the viewer — one HTML file, no build step
└── tests/                   # 321 test functions, none of them touching the network
```

**The dependency rule:** `nodes` → `llm`. The analysis modules — `evaluation`,
`coverage`, `fidelity`, `ablation`, `causes/` — import nothing from `nodes` or
`graph`, which is what lets them run over a batch from any arm.

**And one rule spanning two modules:** `coverage.py` is forbidden from opening
`patients/*.json`, and `fidelity.py` is required to. That is what keeps the
coverage map blind to the answer, and it is why they are two files rather than
one.

---

## Configuration

Settings live in `config/*.yaml`, merged block by block on load. A profile
declares its parent and only what changes:

```yaml
# config/style-narrowly_biomedical.yaml — the whole file
profile: style-narrowly_biomedical
extends: hpc

skills:
  doctor:
    - styles/narrowly_biomedical
```

What `base.yaml` holds:

```yaml
sampling:
  doctor_temperature: 0.7     # asks and infers, and must vary
  patient_temperature: 0.7
  report_temperature: 0.0     # writing the report; variation buys nothing here
  context_length: 32768

server:
  request_timeout: 300        # the first load off GPFS can exceed two minutes

limits:
  max_turns: 20               # a safety net, not a criterion
  report_attempts: 3

features:
  coverage_hint: "off"        # quoted: bare `off` is the YAML boolean False
  working_notes: false
```

**Every setting is sent explicitly on every call**, temperature included. A
setting left out does not raise — the server picks its own default, and the run's
metadata then records something that never travelled.

`OLLAMA_URL` is read from the environment, which is how `serve_ollama.sh` points
the code at its own port.

---

## Further reading

This README is the entry point. Six documents go deeper, each with one job:

| Document | Read it to find |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Why it is built this way, and the build order |
| [TASKS.md](TASKS.md) | **What** each numbered task is. Definitions, no status |
| [STATUS.md](STATUS.md) | **What state** each one is in, and where we drifted |
| [PENDING.md](PENDING.md) | **What to do now**, in order, and what blocks it |
| [TESTS.md](TESTS.md) | What the suite covers, file by file, against which failure |
| [INHERITED_ISSUES.md](INHERITED_ISSUES.md) | What broke in the earlier arms and where it stands |
| [RUN.md](RUN.md) | The launch procedure in full detail, step by step |

Status lives in exactly one place. If TASKS and STATUS disagree, STATUS wins; if
STATUS and the code disagree, the code wins.

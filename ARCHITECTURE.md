# AHEAD — Architecture and build instructions

The design document for the reimplementation. The numbered tasks (`1.5`, `2.1`…)
refer to [TASKS.md](TASKS.md).

---

## 1. Baseline decisions

| Decision | What it means |
|---|---|
| **Runtime** | Python + LangGraph. |
| **Paradigm** | Inference, not elicitation. The doctor converses freely and infers; it never recites questionnaire items. |
| **Agentic behaviour** | The Ruby/Scout arm's: the patient is a **tool** of the doctor, not a peer node. |
| **Code style** | The current Python arm's, so the frontend and the `api_server` can be reused. |
| **Starting point** | `python_version/ahead_agent-bmq-integration`. |

### 1.1 The piece to emulate

In Scout, `delegate` registers the patient as a function of the doctor:

```ruby
doctor.delegate patient, :patient, "Ask this patient questions"
# → exposes the tool hand_off_to_patient(message:, new_conversation:)
```

The doctor is an ordinary agent with tools. Talking to the patient **is a tool
call**. Three properties follow that the current Python arm does not have:

- Turns are not laid out in advance: the doctor calls the tool when it wants
  (1.3).
- The doctor decides when to stop: it stops calling and moves on to writing
  (1.5).
- The transcript is a by-product: it is rebuilt from the `function_call` /
  `function_call_output` pairs.

**In LangGraph this is an agent↔tool loop**, not a chain of fixed nodes:

```
                 ┌──────────────────────────────┐
                 │                              │
                 ▼                              │
  START ──► doctor ──(tool_call: speak)──► patient_tool
                 │                              │
                 └──(no tool_call)──► report ──► END
```

`patient_tool` invokes the patient's LLM with its profile and returns the reply
as a tool result. The doctor receives it and decides: ask again, or finish.
`report` **always** runs on leaving the loop (1.13).

Contrast with what is in `graph.py` today: a walk through a list of questions
with `q_index` and `bmq_index`. That disappears entirely.

**Free does not mean concurrent** (1.4). The loop is strictly sequential: every
turn sees the full state of the previous one. Calls to the LLM are `async` at
the transport level, but there are never two turns in flight at once. What is
free is *when* and *how many times* the doctor speaks, not the order.

---

## 2. File structure

It mirrors the current one so the frontend and the import style keep working.
`NEW` = does not exist today. `PORT` = comes from the current package.

```
ahead_agent_v2/
├── main.py                  # CLI, same shape as the current main.py
├── api_server.py            # FastAPI (see §7)
├── run_batch.py             # PORT — N runs × M patients
│
├── ahead_agent/
│   ├── __init__.py          # re-exports State and build_graph (the latter, lazily)
│   ├── config.py            # CONFIG, models, paths. NO question list
│   ├── state.py             # State TypedDict (§3)
│   ├── graph.py             # build_graph() — the only place that touches StateGraph
│   ├── nodes.py             # doctor_node, patient_tool_node, report_node
│   ├── routing.py           # route_after_doctor
│   ├── tools.py             # NEW — the equivalent of Scout's delegate
│   ├── prompts.py           # NEW — loading markdown: prompts, skills, resources
│   ├── llm.py               # PORT — HTTP client, retries (3.1)
│   ├── patient_profile.py   # PORT — profile → patient prompt
│   │
│   ├── report.py            # NEW — schema, parsing, validation, retry (§4)
│   ├── evaluation.py        # PORT — MAE, bias, Pearson, ICC (4.2)
│   ├── coverage.py          # NEW — 3.2, coverage map + quote verification
│   ├── reproducibility.py   # NEW — 3.3, spread (2.4) and discrimination (2.5)
│   ├── artifacts.py         # NEW — 5.4, crossed transcript and ablation
│   │
│   ├── api/
│   │   ├── doctor.py        # PORT/adapt — now with tools
│   │   ├── patient.py       # PORT almost as is
│   │   └── reporter.py      # NEW — replaces scorer.py
│   │
│   └── causes/              # PORT unchanged — embeddings, similarity, scorer
│
├── config/                  # run profiles (§6)
│   ├── base.yaml            # 0.5 — what is shared; not a profile, does not load alone
│   ├── local.yaml           # small models, smoke scale
│   └── hpc.yaml             # large models, full batches
├── prompts/
│   ├── DOCTOR.md            # the doctor's role
│   ├── PATIENT.md           # the patient's role
│   └── rubric/              # 2.2 — anchors 2/4/6/8, DOCTOR SIDE
│       ├── bipq.md
│       └── bmq.md
├── skills/
│   └── styles/              # 6.5 — one .md per communication style
├── resources/               # 1.8 — CSM, NCF, terminology
├── patients/                # profiles + ground truth
└── runs/                    # outputs per run
```

`build_graph` is resolved when asked for, not when the package is imported:
`graph.py` pulls in langgraph, which off GPFS takes about three minutes, and an
ordinary re-export would charge that to every import — including the
post-processing ones, which never touch the graph. It is also what lets the two
end-to-end tests stay behind `AHEAD_GRAPH_TESTS=1` without dragging the rest of
the suite along.

**A flat structure, as today.** The current package has 9 top-level modules and
only two subpackages (`api/`, `causes/`). It stays that way: `report.py`,
`coverage.py`, `reproducibility.py` and `artifacts.py` are loose modules, not
packages. If any of them passes ~400 lines it gets split then, not before.

**Dependency rule.** `nodes` → `api` → `llm`. `evaluation`, `coverage`,
`reproducibility`, `artifacts` and `causes` import nothing from `nodes`/`graph`:
they are pure post-processing and must be able to run over runs from any arm,
the elicitation one included (5.2).

---

## 3. State

```python
class State(TypedDict):
    # ── Conversation ──
    conversation: List[Dict]      # [{"role": "doctor"|"patient", "content": str, "turn": int}]
    doctor_messages: List[Dict]   # the doctor LLM's history, with tool_calls
    turn_count: int
    finished: bool                # the doctor closed the consultation (1.5)
    coverage_hint: Dict[str, str] # dimension → "covered"; absent = not probed (§4.1)
    working_notes: List[Dict]     # [{turn, dimension, observation}] (§4.1)

    # ── Patient ──
    profile: Dict                 # the full JSON. ONLY patient_tool_node reads it
    patient_messages: List[Dict]

    # ── Output ──
    report_raw: Optional[str]
    report: Optional[Report]      # see §4
    report_attempts: int

    # ── Traceability ──
    run_meta: RunMeta             # 0.4
    events: List[Dict]            # retries, failures, empty turns
```

Out: `q_index`, `bmq_index`, `follow_up_count`, `scores`, `bmq_scores`. There is
no incremental scoring — it is emitted whole at the end (1.11).

### 3.1 The isolation invariant (1.2)

> `profile` never appears in the doctor's context.

This is not a comment, it is a test. `patient_tool_node` is the only thing that
reads `state["profile"]`. Add a check to the suite that serialises every message
sent to the doctor and fails if it contains any `belief_profile` value.

Different models for doctor and patient: `CONFIG["doctor_model"]` and
`CONFIG["patient_model"]`. The current config calls the doctor's `model`; it is
worth renaming to `doctor_model` when porting, because a bare `model` also served
the scorer, which no longer exists.

### 3.2 `run_meta`: the run's provenance (0.4)

Everything needed to interpret a run's results months later. It is written
**once at the start**, next to the outputs, in `runs/<run_id>/run_meta.json`. The
precedent to copy: `run_config.rb`'s `manifest.json` in the Ruby arm.

```jsonc
{
  "run_id": "20260819-161200",
  "started_at": "2026-08-19T16:12:00+02:00",
  "profile": "hpc",                        // local | hpc (§6)

  "models":   { "doctor": "glm-4.7-flash:q8_0",
                "patient": "dolphin-llama3",
                "embed": "jina-embeddings-v4" },

  "sampling": { "temperature": 0.7,        // ALWAYS explicit (§12)
                "seed": null,
                "context_length": 32768,
                "num_parallel": 1 },

  "features": { "coverage_hint": "off",    // the run's arm (§4.1)
                "working_notes": false },

  "prompts":  { "doctor": "sha256:a1b2…",  // hash of the ALREADY COMPOSED prompt (§5.1)
                "patient": "sha256:c3d4…",
                "rubric": "sha256:e5f6…",
                "skills": ["styles/empathic"] },

  "code":     { "git_commit": "9f2c1ab", "dirty": false },

  "compute":  { "hostname": "as01r1b18", "slurm_job": "44820726", "gpus": 1 },

  "corpus":   { "patients": 10, "ground_truth_source": "patients/*.json" }
}
```

Without this, the "one variable per run" method does not work: on seeing the MAE
change between two runs you could not tell whether it was the change you made or
something else. Three fields that look minor and are not:

- **`dirty`** — if there were uncommitted changes, `git_commit` lies. Recording
  it stops you believing a run is reproducible when it is not.
- **`temperature`** — what was **sent** is recorded, not what is assumed. A
  server with its own default changes results silently.
- **prompt hashes** — they are what makes phase 6 measurable: they attribute a
  change of result to a specific change of prompt.
- **`features`** — the arm (§4.1). The shared values have lived in `base.yaml`
  since 0.5, so the profile file no longer shows them: without copying them here,
  a run with `coverage_hint: show` is indistinguishable from the baseline when
  read months later.

---

## 4. The report contract

The doctor returns **one single** structure at the end. It is the heart of
phase 2.

```python
@dataclass
class Evidence:
    quote: str          # a verbatim quote from the transcript
    turn: int           # the turn it comes from

@dataclass
class DimensionScore:
    dimension: str
    evidence: List[Evidence]   # FIRST
    reasoning: str             # SECOND
    score: float | None        # THIRD — None = NA (4.4)
    confidence: float          # 0–1, declared by the doctor (2.3)

@dataclass
class Report:
    patient_id: str
    clinical_summary: str
    bipq: Dict[str, DimensionScore]    # 8 dimensions
    bmq:  Dict[str, DimensionScore]    # 4 subscales
    causes: List[str]                  # open, ranked
    causes_evidence: List[Evidence]
```

**The field order is the specification** (2.1). The prompt and the output schema
must force `evidence → reasoning → score`. Today Ruby's table is
`Score | Rationale`, so the justification is generated after the number and is
decorative; the Python scorer returns the bare number.

**NA policy** (4.4). `score = None` when it cannot be extracted, when the
dimension was not probed, or when the JSON does not parse. Never a default value.
An NA:

- is excluded from the MAE,
- is counted in the coverage rate,
- appears as a hole in the 3.2 map.

**Validation and retry** (1.13). `report.py` checks the 12 dimensions + causes.
If something is missing, retry with the same transcript and a prompt that names
explicitly what is missing. At most 3 attempts (`limits.report_attempts`);
whatever is still missing stays NA and is recorded in `events`.

### 4.1 Ambiguity-driven probing (1.12) — decided

The doctor asks again when the **evidence is insufficient**, not when the answer
is short. The old Python routing fired on `len(reply) < 10 words`, so a long
vague answer went straight to scoring. That rule does not exist here and does not
come back.

What was decided, on closing Stage 3, is **how it is supported**. The first
version of this section assumed the doctor would keep its own list and consult it
before closing. That is an arm, not the baseline: a list of dimensions the doctor
walks is the questionnaire 1.3 took out of the code, coming back in through the
back door, and it forces a coverage that then inflates the result.

It is implemented as **two independent switches**, declared in the `features`
block — in `base.yaml`, or overridden by the profile — and copied to `run_meta`
as they end up after merging (0.4):

```yaml
features:
  coverage_hint: "off"     # off | show
  working_notes: false
```

Independent on purpose: reminding it what it is missing and asking it to write
down what it concludes are different interventions, and in a single value there
would be no telling which produced the effect.

| `coverage_hint` | `working_notes` | What it is |
|---|---|---|
| `off` | `false` | **Baseline.** It is neither asked nor told. |
| `show` | `false` | What is still open is handed back on every reply. |
| `off` | `true` | It records what it concludes, with nothing said to it. |
| `show` | `true` | Both. This is the demo's mode. |

**The baseline is `off` / `false`**, and with it 1.12 is deliberately left
**without a mechanism**: the doctor probes what it wants and coverage is
reconstructed afterwards from the transcript (3.2). Not asking about a dimension
is a result, not a fault to be avoided live.

The state that supports coverage is minimal — a dimension becomes `"covered"`
when the doctor declares it, and there is no intermediate state:

```python
coverage_hint: Dict[str, str]   # dimension → "covered"; absent = not probed
```

#### `working_notes` — the only thing that can show whether the doctor revises

The doctor records, in the same tool call and with no extra calls, what each
answer tells it about a dimension. There is no score field: that still belongs to
the end and to the whole transcript (1.11).

```python
working_notes: List[Dict]   # [{"turn", "dimension", "observation"}]
```

**They are added, never replaced.** Two entries for the same dimension in
different turns are a dated change of mind:

```python
{"turn": 2, "dimension": "consequences",
 "observation": "Has given up the after-dinner walk. Sounds like resignation."}
{"turn": 6, "dimension": "consequences",
 "observation": "I read that as resignation, but they clarify they can and just
                 don't feel like it. Less limitation than it looked."}
```

The whole architecture of reporting at the end rests on late information being
able to correct an early impression, and **there is not one observation of that
happening**. This is the only arm that produces it.

What it costs: it brings part of the judgement forward. When it comes to scoring,
the doctor arrives with its impressions already written, so **its results are not
comparable with the baseline** and that has to be said when reporting them.

There was a third `coverage_hint` mode, `declare` — declare without receiving
anything — meant to cross what the doctor believes it explored against what it
explored. **Retired**: its own declarations come back in the history inside the
`tool_calls`, so it could re-read itself and the arm did not isolate what it
claimed to isolate.

And a point of form that turned out not to be minor: `show`'s reminder travels as
a separate message with `role: user` — the same channel as the `OPENING` — never
inside the tool result. In that channel the doctor cannot tell our words from the
patient's, and `Evidence.quote` has to be a verbatim quote of theirs.

**What `off` shows** (batch `e4-1`, 10 patients × 2): `general_overuse` comes
back NA in 5 of 10 patients and carries a number in the other 5; both `specific_*`
subscales get a number in the 3 patients with no prescription. That is exactly
what this section predicts and what 3.2 has to make visible: coverage is not
forced, it is measured.

---

## 5. Prompts, skills and resources

All three are loaded from disk with `prompts.py`, never embedded in code (1.6).

- **`prompts/DOCTOR.md`, `prompts/PATIENT.md`** — the base role.
- **`prompts/rubric/`** (2.2) — anchors 2/4/6/8 per dimension, **doctor side**.
  Written from clinical criteria. **Do not invert the bands in
  `patient_profile.py`**: that rebuilds the mirror (5.5). Having both without
  their being the same table is the point.
- **`skills/`** (1.7, 6.5) — fragments composed onto the base prompt. The
  doctor's communication styles are files here, not code branches.
  **Deterministic composition, not model-decided loading** — see §5.1.
- **`resources/`** (1.8) — CSM, NCF, terminology. Still to be decided whether
  they are always injected or retrieved; leave the interface ready for both.

Each file is hashed and the hash goes into `run_meta` (0.4), so a result can be
attributed to a version of a prompt.

### 5.1 What "skill" means here (1.7)

**It is not Claude's skills mechanism.** There the model decides for itself which
skill to load and when, through progressive disclosure. This project's models —
llama3.2, GLM, the large HuggingFace ones — do not do that reliably, and building
the design on that assumption would break it silently.

Here a skill is **a markdown fragment the orchestrator concatenates onto the
system prompt before the call**. What gets loaded is decided by the code,
according to the run profile and the experimental arm, not by the model.

```python
build_prompt("DOCTOR.md", skills=["styles/empathic"], resources=["csm"])
# → a single system string, deterministic and hashable
```

Three consequences:

1. **It is model-agnostic.** It works the same with any backend because it only
   manipulates text before sending it.
2. **It is reproducible.** The hash of the composed prompt goes into `run_meta`
   (0.4). With model-decided loading you would not know which prompt produced
   which result.
3. **The fragment has to be verified to have an effect.** Concatenating it does
   not guarantee the model obeys it: a small model can ignore a style instruction
   buried in a long prompt. **Stage 2 test:** compose two opposite skills, run the
   same consultation with each, and check that the transcripts differ observably.
   If they do not differ, the mechanism does not work with that model however
   correct the code is.

### 5.2 Patient profile and room for personalities (1.9, 7.1)

The current structure is kept: `disease_profile` (diagnosis, stage, treatment,
symptoms, lab, demographics) + `belief_profile` (B-IPQ, BMQ, causes) as ground
truth.

An **optional `persona` block** is added, separate from `belief_profile`:

```jsonc
"persona": {
  "communication_style": "guarded",     // talkative, evasive, technical…
  "emotional_expression": "suppressed", // 7.1 — patients who hide emotions
  "health_literacy": "high",
  "traits": ["stoic", "self-reliant"]
}
```

Three reasons to leave it open from the start even if it is not filled in yet:

1. **7.1 needs it.** "Patients who hide emotions" is a property of persona, not
   of belief. Without this block the schema would have to be touched later.
2. **It keeps the two measured things apart.** `belief_profile` is what the
   doctor has to infer; `persona` is what makes the inference more or less
   difficult. Mixing them makes it impossible to analyse the effects separately.
3. **It composes through skills** (1.7): each trait is a markdown fragment added
   to the patient's prompt, just like the doctor's styles. No branches in
   `patient_profile.py`.

`patient_profile.py` translates `belief_profile` → behaviour today; with this it
translates `belief_profile` + `persona` → behaviour, without changing its
signature.

---

## 6. Two run profiles: local and HPC

Everything runs **locally**, with no remote endpoints. Two profiles, the same
architecture and the same code: the model, the scale and the place change.

| | **Local** | **HPC** |
|---|---|---|
| What for | Development, smoke, tests | Baselines, arms, batches |
| Where | Login node or laptop | Compute node, through the queue |
| Server | Ollama, `127.0.0.1:11434` | Ollama or vLLM on the node |
| Doctor | `llama3.2` (2 GB) | a large model — see §6.2 |
| Patient | `dolphin-llama3` (4.7 GB) | a family different from the doctor's |
| Embeddings | `nomic-embed-text` | `jina-embeddings-v4` |
| Scale | 1–2 patients × 1 run | up to 10 × 10 |

The profile is **config, not a code branch**, and is chosen with `--profile`.
`config/base.yaml` has everything shared; `config/local.yaml` and
`config/hpc.yaml` declare what they inherit from and only what changes — the
models and `keep_alive`:

```yaml
profile: hpc
extends: base
```

It is merged **block by block** on load (0.5): a shallow merge would erase a
whole block instead of completing it, so `models: {doctor: …}` in the profile
would end up with no `embed`.

**Inheritance is explicit and chainable.** A profile without `extends` loads on
its own — that is what lets a test leave a key out and see it rejected — and a
chain can have as many links as needed:

```
base.yaml ◄── hpc.yaml ◄── hpc-show.yaml   # `features.coverage_hint: show`, nothing else
```

It is the shape "one variable per run" asks for: a Phase 6 arm is a three-line
file naming its parent and the switch it moves, instead of a copy of `hpc.yaml`
that drifts all over again. A cycle is detected and named; so is inheriting from
something that does not exist, because otherwise an orphaned profile would look
like a profile that is simply missing settings.

`base.yaml` is not a profile and does not load alone: it has no `profile:` key.
What is copied to `run_meta` (0.4) is **the merged result** — `features`
included, which is the arm — so a run is still read from a single file even when
its configuration comes from several.

No result from the local profile goes into published metrics: it tells you the
code works, not how accurate it is.

### 6.1 Model store

The project's Ollama models **are not in `~/.ollama`** but in the shared store.
The variable has to be exported before starting the server, or only what is in
the home directory will be visible:

```bash
export OLLAMA_MODELS=/gpfs/projects/bsc02/llm_models/ollama
ollama serve
```

It holds `llama3.2`, `dolphin-llama3`, `nomic-embed-text` and
`glm-4.7-flash:q8_0`. The large HuggingFace models are elsewhere, in
`/gpfs/projects/bsc02/llm_models/huggingface_models`, and are served with vLLM.

**The first load from GPFS is slow** — a large blob can take over two minutes and
Ollama aborts if the client gives up first. Design consequences:

- The client timeout has to be generous on the first call (≥300 s).
- Every run starts with a **warm-up**: a trivial call that forces the load before
  anything is timed or measured.
- On HPC it is worth copying the weights to the node's local disk if there is
  one; reading a 30 GB model over GPFS on every task does not scale.

### 6.2 Choosing models

Four criteria, in order of hardness:

- **Different families for doctor and patient.** Not two sizes of the same model:
  they share expression conventions learnt in the same training, and the doctor
  may be decoding those conventions rather than inferring. It is 5.5's problem at
  the level of weights, and no 5.4 test detects it.
- **The doctor needs reliable tool calling.** That is the hard requirement:
  without it there is no agentic loop. It is verified with the probe before
  choosing, not after.
- **The patient must not be too obliging.** A heavily aligned model plays a
  suspiciously cooperative patient, answering everything completely and in order,
  and inflates the doctor's apparent performance.
- **The pair is frozen before the stage 7 baseline.** Changing it afterwards
  invalidates the comparability of everything before.

**Verification with `tools/probe_tools.py`** — N calls at temperature 0 with the
real `hand_off_to_patient` tool, counting how many return a well-formed call. It
distinguishes a model failure from a transport failure.

| Model | Result | Note |
|---|---|---|
| `glm-4.7-flash:q8_0` | **10/10** | Fit for doctor. Deterministic at T=0. Measured on a login node (see §6.3): the verdict holds, the 43 s load time has to be remeasured |
| `llama3.2` | 3/3 and 5/5 | Good for smoke tests. Deterministic at T=0. Loads in 5 s on a compute node |
| `dolphin-llama3` | not measured | It is the patient, it needs no tools |
| Large HuggingFace ones | pending | Only if more than GLM is needed |

On HPC it is launched with `tools/probe_hpc.sh <model> [N] [hours]`, which
replicates `submit.sh`'s environment, starts its own Ollama on the node and warms
the model before measuring.

**Determinism confirmed locally.** GLM's 10 replies at T=0 are identical word for
word, as are llama3.2's. That is useful for reproducible regression tests, but
**2.4's spread requires temperature > 0**: at T=0 there is nothing to measure.

### 6.3 The SLURM trap: `salloc` without `srun`

`salloc` reserves the resources but **runs the command on the machine it was
invoked from**, not on the allocated node. The command has to be wrapped in
`srun`.

On the ACC partition the mistake is especially treacherous because **the login
nodes also have H100s**: `nvidia-smi` answers, the model loads, everything looks
correct, and meanwhile the reserved node does nothing.

Three ways to detect it, all verified:

| Signal | Without `srun` (wrong) | With `srun` (right) |
|---|---|---|
| `hostname` | `alogin4` | `as01r1b18` = `$SLURM_NODELIST` |
| `nvidia-smi` | 4 H100s (the login node's) | 1 H100 (the one from `--gres=gpu:1`) |

`probe_hpc.sh` compares `hostname` with `$SLURM_NODELIST` and warns.
**Verified**: without `srun` it gave `alogin4` and 4 GPUs; with `srun
--export=ALL` it gives the allocated node and 1 GPU.

The Ruby arm's `submit.sh` uses the same pattern without `srun`, so its "local"
runs almost certainly executed on the login node. It does not invalidate the
scores — the model and the weights were the same — but it does invalidate any
conclusion about the timings or throughput of those batches.

---

## 7. Frontend and API

The frontend (`bipq_frontend/`, React+Vite, `src/App.tsx`) consumes
`api_server.py`. To reuse it:

**Kept as they are:**
`GET /patients`, `GET /patients/{id}`, `POST /patient/respond`,
`POST /transcript`, `GET /health`.

**Changed:**
- `POST /doctor/ask` → also returns the intent (`speak` | `finish`) and the tool
  call, not just the message.
- `POST /evaluate` → same route, but it receives a `Report` instead of a
  dictionary of loose scores, and also returns coverage and NAs.
- `POST /score` and `POST /bmq/score` → **they disappear.** There is no
  per-exchange scoring. `POST /report` replaces them, receiving the full
  transcript and returning a `Report`.

**New:** `POST /report`, `GET /coverage/{run_id}`, `POST /run` (launch a full
consultation).

Keep the Pydantic models in the same style (`DoctorRequest`/`DoctorResponse`…) so
that the work on `App.tsx` is adaptation, not a rewrite.

**Since 2026-09-01 there is a read-only server that is not this one.**
`replay_server.py` + `replay_frontend/` play back consultations already on disk:
no model, no GPU, no graph. It delivers what 8.4 and 8.8 of TASKS asked for and
deliberately does not attempt `POST /run` — a consultation is minutes of wall
clock, which is what §8.2 of TASKS says has to be streamed per turn.

---

## 8. Build order

Nine stages. Each ends with something runnable and verifiable — do not move to
the next without closing the previous one.

**Nothing is launched at scale at the end.** Each stage closes with a small,
cheap *smoke run* actually executed against a local LLM. The scale only goes up
when the previous stage is green:

| Stage | Smoke run | Cost |
|---|---|---|
| 1 | none — startup only | — |
| 2 | 1 patient × 1 run | ~15 turns |
| 3 | 2 patients × 1 run | ~2 reports |
| 4 | 10 patients × 2 runs | 20 consultations |
| 5 | reuses stage 4's batch | 0 |
| 6 | 10 × 5 | 50 consultations |
| 7 | 10 × 10 (baseline) + arms | 100 + arms |
| 8 | 10 × 5 per intervention | 50 each |
| 9 | depending on the extended corpus | — |

Tests are written **in the stage that introduces the behaviour**, not at the end.
Each stage inherits and re-runs the previous stages' tests.

### Stage 1 — Skeleton (0.1, 0.2, 0.3, 0.4)
Copy the package, `git init`, `run_meta` with provenance, verify that the
`patients/*.json` match across arms.
**Tests:** config loads; `run_meta` serialises completely.
**Done when:** `git log` has the initial commit and `python main.py --help` runs.

### Stage 2 — Agentic loop (1.1–1.9)
It starts by verifying tool calling on the chosen doctor model (§6.2): without
that there is no loop and the rest of the stage makes no sense.
Then `tools.py` with the equivalent of `delegate`, `state.py`, `nodes.py`,
`graph.py`, `routing.py`, `prompts.py` with the composition of skills (1.7) and
resources (1.8). Patient profile with the `persona` block already in the schema
even if empty (1.9). No report yet: the consultation ends and dumps the
transcript.
**Tests:** §3.1's isolation (mandatory from here on); the doctor closes; the turn
cap cuts; the prompt loader resolves files, composes skills and computes hashes;
**two opposite skills produce observably different transcripts** (§5.1) —
concatenation does not prove the model obeys.
**Smoke:** 1 patient × 1 run, local profile.
**Done when:** a 10–15 turn consultation with free turns, closed by the doctor,
and the isolation test green.

### Stage 3 — Report and rubric (1.10, 1.11, 1.12, 1.13, 2.1, 2.2, 2.3, 4.4)
`report.py` complete: schema, parsing, validation, retry. The doctor's anchor
rubric (2.2). Ambiguity probing with `coverage_hint` (§4.1). Declared confidence
(2.3).
**Tests:** the parser with well- and badly-formed reports; the NA policy (never a
default value); the `evidence → reasoning → score` order present; the retry fires
and gives up after 2.
**Smoke:** 2 patients × 1 run.
**Done when:** both produce a valid `Report`, with NA where appropriate.

### Stage 4 — Robustness (3.1, 3.3, 3.4)
Transport retries in `llm.py`, `run_batch.py`, the `events` log,
`reproducibility.py`.
**Tests:** retry on an empty reply and on a server error; `events` records every
failure; the corpus is marked usable/not usable (3.4).
**Smoke:** 10 patients × 2 runs.
**Done when:** the batch comes out with no empty turns and no lost reports.

### Stage 5 — Evaluation (4.1, 4.2, 4.3, 4.5, 4.6)
Port `evaluation.py` and `causes/`. Ground truth from `patients/*.json` and
nowhere else.
**Tests:** metrics against hand-computed values; the ground truth loader rejects
any source other than the profile; causes with text containing `<br/>` and
asterisks (a regression of the old parser's bug).
**Smoke:** reuses stage 4's batch.
**Done when:** a table of MAE, per-dimension bias and causes coverage.

### Stage 6 — Coverage and confidence (3.2, 2.4, 2.5, 2.6)
`coverage.py` with the dimension × patient map and quote verification. Spread
between runs and discrimination between patients, always together.
**Tests:** an invented quote is detected; an unprobed dimension comes out as a
hole; spread and discrimination over known synthetic data.
**Smoke:** 10 × 5.
**Done when:** the heat map comes out and declared confidence has been crossed
against the observed spread.

### Stage 7 — Comparison arms (5.1, 5.2, 5.4, 5.5)
Blind floor, elicitation ceiling, artefact tests, the arm with no behavioural
cues. They are presented, they deliver no verdict.
**Tests:** the crossed transcript degrades the MAE (if not, there is a leak); the
blind floor does not see the conversation.
**Smoke:** 10 × 10 as a baseline, plus the arms.
**Done when:** a chart places the inference arm between floor and ceiling.

**5.3 (human reference)** is not code: it is coordination with clinicians. It is
launched in parallel with this stage, over the already clean transcripts from
stage 4. All that has to be built is the scoring form and the inter-rater
agreement calculation.

### Stage 8 — Interventions (6.1–6.5)
One variable per run, N=5 to screen and N=10 to confirm. 6.5 is loading styles as
skills, not comparing styles.
**Done when:** each intervention has its delta measured against the baseline.

### Stage 9 — Corpus and closing (7.1, 7.2)
Extend the corpus with mid-range profiles and patients who hide emotions (uses
§5.2's `persona` block). Rewrite section 6 of the report with the real numbers.
**Done when:** the extended corpus passes 3.4 and the report is up to date.

---

## 9. Working cycle per stage

Six roles. You implement; I assist where asked.

| # | Role | What it produces | Who |
|---|---|---|---|
| 1 | **Planner** | Breaks the stage into small tasks, defines the "done" criterion | I propose, you approve |
| 2 | **Implementer** | Writes the code | **You**, with my help |
| 3 | **Reviewer** | Reviews Clean Code, SOLID, duplication, complexity | Me |
| 4 | **Tester** | Writes and runs tests, verifies behaviour | I propose, you run |
| 5 | **Refactorer** | Improves structure without changing behaviour | I propose, you decide |
| 6 | **Security/Quality** | Config, secrets, error handling, overall quality | Me |

**Passing rule:** a stage does not close until it has been through all six. Point
5 only acts with point 4's tests green, so a refactor can be told apart from a
change of behaviour.

### The invariants the Reviewer checks at every stage

1. `profile` does not enter the doctor's context (3.1).
2. No default value replaces a failure — always NA (4.4).
3. Ground truth is read only from `patients/*.json` (4.1).
4. `evidence` before `score` in the schema and in the prompt (2.1).
5. `evaluation.py`, `coverage.py`, `reproducibility.py`, `artifacts.py` and
   `causes/` do not import from `nodes`/`graph`.
6. No prompt embedded in a `.py` — everything in `prompts/` or `skills/`.
7. Every run writes its `run_meta` (0.4).
8. No calls to a remote endpoint. Everything local (§6).

### Kinds of test

The concrete tests go stage by stage in §8. The four categories:

- **Unit** — pure logic, no LLM: the parser, the NA policy, the metrics.
- **Integration** — a full consultation with the local profile.
- **Invariant** — the eight above, at every stage from 2 on.
- **Regression** — a small fixed batch, to detect drift between stages.

---

## 10. Benchmark extensions (optional)

What TASKS.md plans covers the basics. These additions are cheap and fit without
touching the architecture. **None of them delivers a verdict**; they are
presented, like 5.1/5.2.

### Agreement metrics, not just error

- **ICC (intraclass correlation)** — the standard in clinical agreement studies.
  Its value is that it compares **directly** with the agreement between 5.3's
  clinicians: it puts the model and the humans on the same scale.
- **Spearman** alongside Pearson. Pearson assumes linearity; Spearman only
  measures whether the order is preserved. If Spearman is high and Pearson low,
  the model ranks the patients well but the scale is shifted — a very different
  problem, and one fixed with calibration (6.3) rather than with more probing.
- **Bland-Altman** — the standard method-comparison plot in medicine: it shows
  whether the bias changes with magnitude. It would say, for instance, whether
  the model only gets the extremes wrong or the mid-range too.
- **Dichotomised agreement** — split each dimension into high/low and report
  concordance. It is the clinically actionable reading: to intervene on a patient
  what matters is whether their perceived adherence is low, not whether it is 3.2
  or 3.8.

### Automatic problem detection

- **Quote verification** (in `coverage.py`) — check that every `Evidence.quote`
  appears verbatim in the transcript. It detects evidence fabrication
  automatically and cheaply. It was checked by hand before and the finding was
  that the model did not invent quotes but misclassified them; as an automatic
  gate, it watches that this stays true.
- **Evidence↔score contradiction** — a second model reads only the quote and the
  reasoning, without seeing the number, and predicts the score. A large
  divergence = the number does not follow from the evidence. It is the automatic
  version of 5.4.
- **Drift between runs** — the same configuration, runs separated in time: it
  detects endpoint changes that are not the code's fault.

### Conversation metrics

None of these needs ground truth and all come out of the transcript:

- Turns to closing, and their spread across patients.
- Question diversity: does the doctor vary or repeat a script?
- The doctor/patient share of the talking.
- Temporal coverage: at what point in the consultation each dimension is
  touched — if `causes` always comes up in the last turn, it is filler.

---

## 11. Language

**English, and this document is the canonical version.** The project thread
(Christina, the PI) runs in English, so this is the one other people will read.

The plan was to translate on closing stage 3, when the agentic loop and the
report contract would no longer change, because translating while the design
moves guarantees two diverging versions.

**Done on 2026-09-01**, and it went further than this section planned: every
document is now in English — README, ARCHITECTURE, TASKS, STATUS, PENDING, TESTS,
INHERITED_ISSUES, RUN and `skills/styles/README.md`. There is no Spanish version
to keep in sync, which is the point: two versions is how they diverge.

Note that this section used to say `TASKS.md` could stay in Spanish as an
internal working document. That exception is retired — the split was what made it
possible to forget which one was authoritative.

---

## 12. Known risks

| Risk | Mitigation |
|---|---|
| The doctor never closes the consultation | The turn cap as a safety net (1.5) |
| The report degrades on long consultations | Validation + retry (1.13); it is what lost CLL-004 |
| The doctor's rubric ends up mirroring the patient's | Write it from clinical criteria; measure it with 5.5 |
| Implicit temperature: a server applying its own default changes results without warning | Send it **always** explicitly and record it in `run_meta` |
| A slow load from GPFS aborting the first call | Warm up before measuring and a timeout ≥300 s (§6.1) |
| Rewriting the frontend instead of adapting it | Freeze §7's endpoints before touching `App.tsx` |
| **Contamination between patients.** In `simulation.rb` the doctor agent is created **once** outside the patient loop and reset with `doctor.start`. If the reset is not complete, patient N sees residue from N−1 | Create the doctor agent **inside** the loop, one per consultation. Test: two consecutive consultations share not one message |
| Leaving evaluation to the end and discovering the corpus is unusable | Smoke runs per stage (§8) and 3.4's gate |
| **Automating a judgement the literature puts at 60-80% and reading it as if it were exact** | §13: what is verifiable gets verified, what is interpretable gets validated against labels before deciding anything |
| **Two documents name a different baseline.** `STATUS.md` treats `e4-1` as the live corpus and `runs/historic/`'s README calls it superseded. While that lasts, an `e4-1` figure can be read as a baseline without being one | Deferred to TASKS Phase 8 (8.11), on purpose: it gets reconciled with a new batch in front of us, not by rewriting now. Until then every `e4-1` figure is reported with the note |
| **A retry that cannot succeed.** An identical request at temperature 0 gets the identical reply, so retrying an empty report reproduced the failure three times instead of recovering from it (N10) | Fixed on 2026-09-01: the body is rebuilt per attempt and an empty reply raises the temperature floor. A transport failure still repeats the identical request — the two cases are different and the code now says so |

---

## 13. Coverage: layers, and what backs each one

`coverage.py` is not a module with one metric: it is **layers with very different
reliabilities**, and mixing them is what turns a measurement into an impression.
The order runs from what is checked to what is interpreted, and each layer
validates the next.

### 13.1 The three layers

| | What it decides | How | Reliability |
|---|---|---|---|
| **L0** | does the quote exist, in that turn, said by the patient? | string comparison | exact |
| **L1** | did the doctor ask about this dimension? | a **checklist**-type judgement | high, measurable |
| **L2** | does the quote **support** that dimension? | an **attribution** judgement | 60-80%, see 13.4 |

**L0 is done** and gives three separate checks — verbatim, the named turn, a
patient's line — the four states of score × evidence, and the spread across
repeats. No model, no labels, blind to the truth.

**That the three checks are kept separate is not cosmetic.** Running over `e4-1`
it came out as `verbatim 95% · turn 93% · from the patient 0%`, and that exact
zero exposed a code bug — a turn is an exchange, and doctor and patient share a
number — that a single `verified` would have presented as "the doctor grounds
nothing".

### 13.2 The four states

|  | verified evidence = 0 | ≥ 1 |
|---|---|---|
| **unscored** | `SILENT` | `CITED_UNSCORED` — it quoted and declined to score |
| **scored** | **`UNGROUNDED`** — a number with nothing behind it | `GROUNDED` |

`UNGROUNDED` is the cell that justifies the module, and it has a name in the
literature: it is **ALCE**'s *citation recall* in the empty-citation-set case.
What is **not** taken from ALCE is the method — they solve it with an NLI model
over passage identifiers; here the doctor emits verbatim quotes and `str.find`
decides. Citing ALCE as backing for string comparison would be false.

### 13.3 What L0 cannot see, by construction

A quote **invented by the patient** is a real quote from the transcript: it
verifies and comes out `GROUNDED`. Quote integrity and fidelity to the profile
are different things, and that is why **3.5 is a sibling module and not a
coverage layer**: it would read the profile and break the blindness to the truth
that makes coverage valid for any arm.

This is not theoretical. In the baseline, the patient asserted active treatment in
3 of 5 repeats of a patient on watch-and-wait, and the doctor accepted it — so
`specific_necessity` and `specific_concerns` were scored over a drug that does
not exist.

**And it is the only place where a word list is legitimate.** Searching for
*Ritalin* is not a proxy: the drug is the fact. Searching for *work* to decide
whether `consequences` was explored is one. Understanding why one is valid and
the other is not is what marks L1's boundary.

### 13.4 A constraint of method for L2

From **AttributionBench** (arXiv 2402.15089), which measures automatic
attribution as binary classification over seven sets:

- GPT-4 zero-shot with CoT: **73.3%** macro-F1. Fine-tuned GPT-3.5: **~80%**. In
  a specialised domain, **below 60%** — and a clinical dialogue is one.
- **Large LLMs perform below small fine-tuned NLI models** (FLAN-T5 3B, and on
  some sets the 770M one).
- **The prompt is not the lever**: four increasingly elaborate prompts moved F1
  from 73.2 to 74.0. What changes is the split between false positives and
  negatives, not the accuracy.
- **More context makes it worse**: adding the full question and answer degraded
  the result, because the model ends up judging usefulness rather than
  attribution.

Consequences, if L2 is reached:

1. An **NLI model**, not the doctor's model with a careful prompt. ALCE uses
   `google/t5_xxl_true_nli_mixture` and its implementation fits in eight lines:
   compose `"premise: {passage} hypothesis: {claim}"` and read whether it returns
   `1`.
2. **Minimal input**: the quote and the dimension's definition, without the
   transcript around it.
3. The quote is a fragment — *"Fine."*, *"I don't know."* — whose meaning only
   exists in its turn, so it first has to be turned into a self-contained
   proposition. That is AIS's **explicature**, and without that step the
   judgement is incoherent.
4. Expect 70-80%, not "solved".

**L1 and L2 are not the same problem and are not chained.** L1 is
checklist-shaped, and there the French OSCE study measures ICC 0.85 — against ~0
on judgements of linguistic quality, where the humans did not agree with each
other either. L2 is attribution, and that is the bad ground. Treating them as a
single ladder was a mistake in the first version of this plan.

### 13.5 The shape of the labelled set

When L1 or L2 need validating, the schema already exists: it is **AIS**'s, and
its repository publishes the data in that shape.

- **Two phases, in order.** First `INT` — is the sentence interpretable in its
  context? — and attribution is **only annotated if `INT = 1`**. The second
  question is never asked without having answered the first.
- **Agreement recorded**, not assumed: how many annotators agreed.
- **A `Flagged` output** for a task that cannot be judged. Abstention is a value,
  the same way 4.4's NA is.
- The full guidelines are in the **paper**, not in the repository.

And a warning from AttributionBench itself: **11.2%** of its error cases turned
out to be failures of the human label. Labelling badly is a measured risk.

### 13.6 Validating without labels

Two checks that cost no annotation and are worth doing before asking for it:

- **Deliberate degradation** (the French OSCE's method): break the doctor on
  purpose and check that coverage drops. The machinery already exists — it is the
  style arms.
- **Agreement between two models** over the same conversations. It does not prove
  either is right, but disagreement marks the ceiling of the method.

Neither gives *accuracy*. Without labels there is no accuracy, and there is no
trick that avoids it.

### 13.7 Constraints inherited from clinical dialogue coding

From **RIAS**, which has been coding doctor-patient interaction since 2002:

- The coding unit is **the thought**, not the turn. Ours is coarser still — a
  whole exchange, doctor and patient under the same number — and the styles stack
  several questions into one turn.
- **Do not infer the question from the answer.** L1 and the presence of
  information have to be independent judgements, or the 2×2 collapses on its own.
- **Keywords are not enough** to identify the type of question. That is, published
  twenty years ago, the same conclusion that closed the gate reader on
  2026-08-27.

And from **AMIE**: a rubric is not invented, it is derived from published
instruments and refined with clinicians.

### 13.8 What has no backing, and has to be said

Two pieces rest on nothing in the assembled literature, and the report has to
declare it rather than hang them off a citation that says something else:

- **L0's string comparison** is not ALCE's method even though it shares the name
  of the metric.
- **3.5, patient fidelity**, measures something none of the seven papers measures.
  The French OSCE's *information recall* is the closest and runs the other way: it
  checks whether the patient **volunteers** the items on their card, not whether
  they **invent** the ones they do not have. It is our own metric.

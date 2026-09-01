# How to launch a consultation

Two profiles, the same code (§6). `local` on the login node for smoke tests and
tests; `hpc` on a compute node for anything that gets measured.

Every step is there for a concrete reason. Skipping one does not give an error:
it gives a run that looks fine and is not.

---

## Copy and paste

The why of each line is further down. Here they just are, in order.

**Tests** (login node, no server):

```bash
cd /gpfs/projects/bsc02/bsc064212/AHEAD/use_cases/patient_doctor_agents/agents_simulations
./venv-local/bin/python -m pytest tests/ -q
```

**A consultation locally** (smoke, `llama3.2`):

```bash
cd /gpfs/projects/bsc02/bsc064212/AHEAD/use_cases/patient_doctor_agents/agents_simulations
. serve_ollama.sh
./venv-local/bin/python main.py --patient patients/CLL-003.json --profile local
```

**A consultation on HPC** (`glm-4.7-flash:q8_0`). First, from the login node:

```bash
cd /gpfs/projects/bsc02/bsc064212/AHEAD/use_cases/patient_doctor_agents/agents_simulations
salloc -A bsc02 -q acc_debug -p acc --gres=gpu:1 -c 40 -t 1:00:00 \
  srun --export=ALL --pty bash
```

And once inside the node, all at once:

```bash
cd /gpfs/projects/bsc02/bsc064212/AHEAD/use_cases/patient_doctor_agents/agents_simulations

hostname; echo "$SLURM_NODELIST"
nvidia-smi -L

. serve_ollama.sh

time curl -s "$OLLAMA_URL/api/chat" -d '{
  "model":"glm-4.7-flash:q8_0",
  "messages":[{"role":"user","content":"hi"}],
  "stream":false,"keep_alive":"4h"}' > /dev/null

./venv-hpc/bin/python main.py --patient patients/CLL-003.json --profile hpc --run-id s3-1
```

**Seeing what came out:**

```bash
ls runs/s3-1/
python3 -c "import json; t=json.load(open('runs/s3-1/transcript.json')); print(t['turns'], t['stop_reason'], len(t['events']))"
```

**A batch on HPC** (same node, same steps 1–4, and instead of `main.py`):

```bash
git status --short                          # has to be empty
./venv-hpc/bin/python run_batch.py --profile hpc --repeats 5 --run-id e4-1
```

---

## The whole order, from reservation to number

Nine stages. **The only thing that needs the server after the consultations is
`rescore.py`**, so it goes before releasing the node; the rest is pure
post-processing and runs anywhere.

| | Stage | Server | Why it goes here |
|---|---|---|---|
| 0 | `pytest tests/` + `cover.py` smoke | no | The whole suite. The smoke test is the only thing exercising the CLI's formatting |
| 1 | `git commit` | no | `run_batch` aborts on a dirty tree |
| 2 | node, `serve_ollama.sh`, warm up | **yes** | §6.1 and §6.3 |
| 3 | `rescore.py` smoke over an old batch | **yes** | 4 calls. **Before generating anything**: if the tool is broken, finding out here costs a minute and at stage 7 it costs the reservation |
| 4 | time one consultation | **yes** | ×20 plus a fifth for the ablation: does it fit in the walltime? |
| 5 | `run_batch.py --repeats 5` | **yes** | the consultations |
| 6 | gate: `batch.json` | no | `stop_reason: doctor` on all of them, `events: 0`. If it fails, nothing below is read |
| 7 | `fidel.py` → `cover.py` → `rescore.py` | only the third | see below |
| 8 | `evaluate.py` | no (unless `--causes`) | the MAE, last |

```bash
# 0 — no server, on login
./venv-local/bin/python -m pytest tests/ -q
./venv-hpc/bin/python tools/make_dummy_batch.py
./venv-hpc/bin/python cover.py /tmp/ahead-dummy-batch

# 3 — ablation smoke over data that already exists, outside the repository
cp -r runs/historic/e4-1 /gpfs/projects/bsc02/bsc064212/ahead-smoke
./venv-hpc/bin/python rescore.py /gpfs/projects/bsc02/bsc064212/ahead-smoke --profile hpc --limit 2

# 6 — the gate
python3 -c "
import json; b=json.load(open('runs/BATCH/batch.json'))
for c in b['consultations']:
    print(c['run'], c['status'], c.get('stop_reason'), 'events', c.get('events'))"

# 7-8
./venv-hpc/bin/python fidel.py    runs/BATCH --profile hpc --quotes
./venv-hpc/bin/python cover.py    runs/BATCH
./venv-hpc/bin/python rescore.py  runs/BATCH --profile hpc     # with server
./venv-hpc/bin/python evaluate.py runs/BATCH --profile hpc
```

**The order of stage 7 is not decorative.** Fidelity first: if the patient did
not play its profile, neither the coverage nor the MAE of that consultation says
anything. Coverage next, because 3.4 forbids analysing a corpus that has not
passed 3.2. Evaluation last.

Each one leaves a file next to the batch: `fidelity.json`, `coverage.json`,
`report-intact.json` / `report-ablate.json` per consultation, and
`evaluation.json`. **None of them modifies `report.json`.**

**`--repeats 5`, not 2 or 3.** `coverage.py` sets `MIN_REPEATS = 5` and below
that returns `sd: None`: a batch of 3 comes out entirely null. You can start at 2
and go up later with **the same `--run-id`**, which resumes and pays only for the
missing rounds. `rescore.py` resumes the same way.

**Smoke copies go outside the repository.** Inside they dirty the tree and
`run_batch` refuses to start; inside `runs/historic/` they contaminate the
archive with files that run never produced.

---

## Looking at a consultation afterwards

```bash
./venv-local/bin/python replay_server.py --patient CLL-003   # http://127.0.0.1:8000
```

Plays a consultation back turn by turn and then shows the report and the
evaluation. Read-only post-processing — no model, no GPU, no graph — so it runs
on the login node while a batch is still in the queue. Over SSH, forward the
port: `ssh -L 8000:127.0.0.1:8000 <login>`.

One patient at a time. Without `--patient` the browser picks a person first and
then one of their consultations. Its first start is slow because it globs `runs/`
off GPFS; `--runs` pointed at a directory holding only what will be shown makes
it immediate.

---

## Tests

No server: the LLM is replaced by scripted replies.

```bash
./venv-local/bin/python -m pytest tests/ -q
```

Two stay out by default, the end-to-end ones. They are the only tests that build
the graph, and building it imports `langgraph`:

```bash
AHEAD_GRAPH_TESTS=1 ./venv-local/bin/python -m pytest tests/ -q
```

The count lives in [TESTS.md](TESTS.md), and if that document and `grep`
disagree, `grep` wins.

**`import langgraph` takes ~3 minutes reading off GPFS**, measured twice with the
same result, so it is not a cold cache: it is thousands of small files and the
cost is metadata. `main.py` pays it too, before the first call to the model. On a
compute node it is worth copying the venv to local disk before a batch; reading
it off GPFS on every task does not scale, the same way it does not for the
weights (§6.1).

---

## First of all: commit

`metadata.code.dirty` records whether the tree had uncommitted changes. If it is
`true`, the run's `git_commit` does not describe the code that produced it and
the run is not reproducible.

```bash
git status --short          # empty before a run you want to keep
```

For a smoke test it does not matter. For a baseline, it does.

---

## Local (login node)

```bash
cd /gpfs/projects/bsc02/bsc064212/AHEAD/use_cases/patient_doctor_agents/agents_simulations

export OLLAMA_NUM_PARALLEL=1
. serve_ollama.sh

./venv-local/bin/python main.py --patient patients/CLL-003.json --profile local
```

Nothing from this profile goes into published metrics: it says the code runs, not
how accurate the doctor is.

---

## HPC (compute node)

### 1. Reserve a node and land on it

```bash
cd /gpfs/projects/bsc02/bsc064212/AHEAD/use_cases/patient_doctor_agents/agents_simulations

salloc -A bsc02 -q acc_debug -p acc --gres=gpu:1 -c 40 -t 1:00:00 \
  srun --export=ALL --pty bash
```

`acc_debug` with one hour is for smoke tests. **A batch does not fit there**:
time one consultation first (`--repeats 1` over one patient), multiply by the
number of consultations, add the ablation of 5.4, and ask for `-q acc` with that
time plus a margin. Falling short does not lose the work — relaunching with the
same `--run-id` resumes — but it does lose the reservation.

The inner `srun` **is not optional** (§6.3). `salloc` reserves the resources but
runs the command on the machine it was invoked from, and the ACC login nodes have
H100s too: without `srun` everything looks right while the reserved node does
nothing.

`-c 40` is about memory, not CPU: ACC gives 8 GB per core, and ollama was killed
loading 31.8 GB of weights plus the KV cache. 40 cores = 320 GB.

### 2. Check where you are

```bash
hostname; echo "$SLURM_NODELIST"     # they have to match
nvidia-smi -L                        # 1 GPU, not 4
```

The two signals from §6.3. If `hostname` says `alogin*` or four GPUs come back,
you are on the login node: leave and repeat step 1.

### 3. Start the server

```bash
. serve_ollama.sh
```

It exports `OLLAMA_MODELS` (the project's models are not in `~/.ollama`),
`OLLAMA_HOST`, the binary's `PATH`, `OLLAMA_URL` — which `load_config` reads and
which ends up in `metadata.server.ollama_url` — and `OLLAMA_NUM_PARALLEL`.

That last one has to be set **before** the server starts: it is a server
variable, not a request option, so `llm.py` cannot send it. Without it the server
uses its default, splits the context between slots and truncates silently, while
`metadata.sampling.num_parallel` goes on saying 1.

It should list the four models: `glm-4.7-flash:q8_0`, `dolphin-llama3`,
`llama3.2`, `nomic-embed-text`.

### 4. Warm the model

```bash
time curl -s "$OLLAMA_URL/api/chat" -d '{
  "model":"glm-4.7-flash:q8_0",
  "messages":[{"role":"user","content":"hi"}],
  "stream":false,"keep_alive":"4h"}' > /dev/null
```

This pulls the weights onto the GPU. It is ~30 s from GPFS which, otherwise, is
paid by the doctor's first call against a 300 s timeout and counted as part of
the first turn (§6.1). If it takes much longer, something is wrong before
anything has been measured.

### 5. Run

```bash
./venv-hpc/bin/python -c "import langgraph; print('venv ok')"
./venv-hpc/bin/python main.py --patient patients/CLL-003.json --profile hpc --run-id hpc-test-1
```

`venv-hpc` **only works on the compute node**. Its `bin/python3` points at
`/usr/bin/python3`, which there is 3.9 and matches its `site-packages`; on the
login node it is 3.10 and it imports nothing. On login, use `venv-local`.

---

## Afterwards

```bash
ls runs/hpc-test-1/                  # metadata.json + transcript.json
```

Three things to look at in `transcript.json`:

- `stop_reason` — `doctor` is what you want. `turn_cap` means the cap cut it off,
  not the doctor. `malformed_call` is a tool-calling failure.
- `events` — empty is a clean run. Anything there (retries, empty turns) has to
  be read before believing the result.
- `turns` — 10–15 is a real consultation. 1 turn is the doctor closing
  immediately, which is what `llama3.2` does with any prompt.

And in `metadata.json`, `prompts.doctor`: the hash identifies which version of
the prompt produced this. It is what allows a change of result to be attributed
to a change of prompt and not to something else.

---

## Batches: `run_batch.py`

`main.py` is one consultation. One consultation measures nothing: the spread
between identical runs is 1.25 of MAE (N2), so any n=1 number is below the noise.
`run_batch.py` runs **N repeats × M patients** under a single configuration,
which is the unit the empirical confidence (2.4) and the discrimination between
patients (2.5) are computed on.

```bash
./venv-hpc/bin/python run_batch.py --profile hpc --repeats 2 --run-id e4-1
```

| Option | What it does |
|---|---|
| `--repeats N` | Consultations per patient. Default 1 |
| `--patients ...` | Specific profiles. Default: the 10 in `paths.patients` |
| `--profile` | `local` or `hpc`, same as `main.py` |
| `--run-id` | The batch's name. Default: a timestamp |
| `--allow-dirty` | Run with uncommitted changes. Without it, **it refuses to start** |

The scales from §8: Stage 4 is `--repeats 2` over the 10, Stage 6 is 5, and the
Stage 7 baseline is 10.

### What it does, in order

1. **Checks the tree.** If `git status` is not clean, it aborts. That is the
   failure of the four `s3-*` runs: they came out with `dirty: true` and cannot
   be attributed to any commit. For smoke tests, `--allow-dirty`.
2. **Warns if both temperatures are 0.** At T=0 the repeats are identical and 2.4
   has nothing to measure.
3. **Writes the metadata once**, in `runs/<batch>/metadata.json`: it is the same
   configuration for the whole batch, and duplicating it per consultation would
   only give 20 copies of the same file.
4. **Warms both models** with a trivial call (§6.1), so the load from GPFS is not
   paid by the first turn.
5. **Runs the consultations in series**, one full sweep of the corpus and then
   the next. If the queue cuts the batch short, what is left is the 10 patients
   once rather than two patients ten times.
6. **One consultation blowing up does not bring down the batch**: it is recorded
   as `failed` and the run continues. The index is rewritten after each
   consultation.

### What it leaves

```
runs/<batch>/
├── metadata.json         # the configuration of the whole batch (0.4)
├── batch.json            # the index: one line per consultation
├── CLL-001-r1/           # transcript.json + report.json
├── CLL-002-r1/
│   …
└── HIV-005-r2/
```

`batch.json` is what gets read before analysing anything:

```bash
python3 -c "
import json; b=json.load(open('runs/historic/e4-1/batch.json'))
for c in b['consultations']:
    print(c['run'], c['status'], c.get('stop_reason'), 'events', c.get('events'), 'NA', len(c.get('na',[])))"
```

`status: failed`, `report_parsed: false` or `events` other than 0 in any
consultation means the batch is not an analysable corpus yet (3.4). Fix it and
relaunch: **relaunching with the same `--run-id` resumes**, skips the
consultations that already have a `transcript.json` and pays only for the missing
ones.

---

## Prompt variants

There is no profile per prompt. You change the `prompts.doctor` line in
`config/hpc.yaml` and the hash in `metadata.json` records which one was used.

Today there is only one, `DOCTOR.md`. The Stage 3 variants were retired when it
closed; `prompts/reference/` keeps the Ruby arm's prompts as a reference, but
they are not wired to any profile.

One variable per run: change the prompt or change the model, not both.

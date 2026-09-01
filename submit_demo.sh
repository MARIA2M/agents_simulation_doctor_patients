#!/bin/bash
#SBATCH --job-name=ahead-demo
#SBATCH --account=bsc02
#SBATCH --qos=acc_bscls
#SBATCH --partition=acc
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=40
#SBATCH --gres=gpu:1
#SBATCH --time=08:00:00
#SBATCH --output=logs/demo-%j.out
#SBATCH --error=logs/demo-%j.err
# ────────────────────────────────────────────────────────────────────────
# One node, the whole pipeline: consultations and then the four analyses.
# The non-GREASY path — use this when the batches are few enough to run in
# series and you want the ablation in the same allocation.
#
#   mkdir -p logs
#   sbatch submit_demo.sh                       # 2 patients × 4 arms × 5 = 40
#   ARMS="nb bps" sbatch submit_demo.sh         # just the opposed pair: 20
#   ARMS="off bps" sbatch --time=04:00:00 submit_demo.sh
#
# The default is 40 consultations plus 80 ablation calls. Time one consultation
# before trusting --time=08:00:00 — it is a guess until you have measured one.
# Running out is recoverable: the same --run-id resumes and only pays for what
# is missing, in run_batch.py and rescore.py alike.
#
# This is `salloc … srun --pty bash` turned into a job, with one difference
# that matters: **the body already runs on the allocated node.** There is no
# inner srun and no §6.3 trap, because there is no interactive shell to land in
# the wrong place. `hostname` is printed anyway, since it costs nothing.
#
# `-c 40` is memory, not CPU: ACC gives 8 GB per core and ollama was killed
# loading 31.8 GB of weights plus the KV cache. 40 cores = 320 GB.
#
# The queue: acc_bscls, not acc_debug. Debug caps at an hour, and twenty
# consultations plus the ablation do not fit. Time one consultation first
# (RUN.md stage 4), multiply, add a fifth for the ablation, then set --time.
#
# COMMIT FIRST. run_batch.py refuses a dirty tree, and here that failure lands
# in a log rather than on your terminal.
# ────────────────────────────────────────────────────────────────────────
set -euo pipefail

cd "${SLURM_SUBMIT_DIR:-$(dirname "$0")}"
mkdir -p logs runs

# All four arms on both patients: 2 × 4 × 5 = 40 consultations.
#
# Mode and style are independent switches (ARCHITECTURE §4.1), and the baseline
# is `off` + good_doctor, so every arm moves exactly one thing against it:
#
#     off   hpc                        off  + good_doctor          baseline
#     show  hint-show                  show + good_doctor          moves the mode
#     nb    style-narrowly_biomedical  off  + narrowly_biomedical  moves the style
#     bps   style-biopsychosocial      off  + biopsychosocial      the opposite pole
#
# nb ↔ bps is the sharpest contrast and the only pair with prior evidence: the
# §5.1 gate separated them cleanly on doctor turn length and topic selection.
PATIENTS="${PATIENTS:-CLL-003 HIV-005}"
ARMS="${ARMS:-off show nb bps}"
REPEATS="${REPEATS:-5}"
RUN="${RUN:-1}"
PY=./venv-hpc/bin/python

# ALLOW_DIRTY=1 drops the clean-tree requirement. What it costs is recorded, not
# hidden: metadata.code.dirty comes out true and git_commit names code that is
# not what ran, so the batch is not reproducible and is not a publishable
# baseline. Fine for iterating and for a demo; redo it clean for the number you
# intend to defend.
DIRTY_FLAG=""
[ -n "${ALLOW_DIRTY:-}" ] && DIRTY_FLAG="--allow-dirty"

# arm → "profile mode style"
#
# The mode belongs in the id as much as the style does. `off` and `show` share
# good_doctor, so naming a batch by its style alone makes those two arms write
# to one directory — and the second reads as a resume of the first and skips
# every consultation. Same convention as make_greasy_tasks.sh.
arm_profile () {
  case "$1" in
    off)  echo "hpc                       off  good_doctor" ;;
    show) echo "hint-show                 show good_doctor" ;;
    nb)   echo "style-narrowly_biomedical off  narrowly_biomedical" ;;
    bps)  echo "style-biopsychosocial     off  biopsychosocial" ;;
    *)    echo "unknown arm: $1" >&2; exit 1 ;;
  esac
}

echo "[node] $(hostname) / ${SLURM_NODELIST:-?}"
nvidia-smi -L

# The same check submit_greasy.sh makes before spending the allocation: on a
# login node venv-hpc imports nothing, and it is better seen here than in N logs.
want="$(sed -n 's/^version *= *\([0-9]*\.[0-9]*\).*/\1/p' venv-hpc/pyvenv.cfg)"
have="$($PY -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
[ "$want" = "$have" ] || { echo "venv-hpc wants python $want, this node gives $have" >&2; exit 1; }
$PY -c "import langgraph, yaml" || { echo "venv-hpc is missing dependencies" >&2; exit 1; }
echo "[venv] python $have, langgraph ok"

# shellcheck disable=SC1091
. ./serve_ollama.sh

# §6.1 — pull the weights onto the GPU before anything is timed. run_batch warms
# them too, but doing it here means a cold-load failure shows up before the first
# batch rather than inside it.
echo "[warm] loading the doctor model"
time curl -s "$OLLAMA_URL/api/chat" -d '{
  "model":"glm-4.7-flash:q8_0",
  "messages":[{"role":"user","content":"hi"}],
  "stream":false,"keep_alive":"4h"}' > /dev/null

# ── The consultations ───────────────────────────────────────────────────

BATCHES=()
for patient in $PATIENTS; do
  for arm in $ARMS; do
    read -r profile mode style <<<"$(arm_profile "$arm")"
    id="${patient}x${REPEATS}-${mode}-${style}-run${RUN}"
    BATCHES+=("$id")

    echo ""
    echo "══ $id  ($profile)"
    # One failed batch does not sink the job: the others are still worth having,
    # and relaunching with the same --run-id resumes.
    $PY run_batch.py --profile "$profile" \
        --patients "patients/${patient}.json" \
        $DIRTY_FLAG --repeats "$REPEATS" --run-id "$id" || echo "  ! batch failed: $id"
  done
done

# ── The gate, then the four analyses ────────────────────────────────────
#
# Order is not decoration. Fidelity first: a patient that did not play its
# profile invalidates the coverage and the MAE of that consultation. Coverage
# next, because 3.4 forbids analysing a corpus that has not passed 3.2.
# rescore.py is the only one needing the server, and it still has it here.

for id in "${BATCHES[@]}"; do
  [ -d "runs/$id" ] || { echo "no runs/$id, skipping analysis"; continue; }

  echo ""
  echo "══ analysing $id"
  $PY -c "
import json; b=json.load(open('runs/$id/batch.json'))
bad=[c for c in b['consultations']
     if c.get('status')!='ok' or c.get('stop_reason')!='doctor' or c.get('events')]
for c in b['consultations']:
    print(' ', c['run'], c['status'], c.get('stop_reason'), 'events', c.get('events'))
print(('  ! %d consultations failed the gate — read before trusting anything below'
       % len(bad)) if bad else '  gate: clean')"

  $PY fidel.py   "runs/$id" --profile hpc --quotes || echo "  ! fidel failed"
  $PY cover.py   "runs/$id"                        || echo "  ! cover failed"
  $PY rescore.py "runs/$id" --profile hpc          || echo "  ! rescore failed"
  $PY evaluate.py "runs/$id" --profile hpc         || echo "  ! evaluate failed"
done

echo ""
echo "[done] ${#BATCHES[@]} batches under runs/"
echo "       fidelity.json, coverage.json, report-{intact,ablate}.json, evaluation.json"

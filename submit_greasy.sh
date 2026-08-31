#!/bin/bash
#SBATCH --job-name=ahead-greasy
#SBATCH --account=bsc02
#SBATCH --qos=acc_bscls
#SBATCH --partition=acc
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=40
#SBATCH --gres=gpu:1
#SBATCH --time=02:00:00
#SBATCH --output=logs/greasy-%j.out
#SBATCH --error=logs/greasy-%j.err
# ────────────────────────────────────────────────────────────────────────
# Corre un fichero de tareas con GREASY. No genera nada y no sabe qué hay
# dentro: eso lo hace ./make_greasy_tasks.sh, y el fichero es texto plano.
#
#   mkdir -p logs greasy_tasks
#   ./make_greasy_tasks.sh > greasy_tasks/tasks.txt
#   sbatch submit_greasy.sh                                  # coge tasks.txt
#   sbatch --nodes=6 submit_greasy.sh greasy_tasks/otra.txt  # más obreros, si entran
#   sbatch submit_greasy.sh greasy_tasks/tasks.txt-restart   # reanudar lo que falló
#
# Cuántos nodos pedir se mide, no se adivina: `sbatch --test-only --nodes=N ...`
# dice cuándo arrancaría sin enviar nada. Pedir muchos con GPU se queda en cola.
# Cuatro nodos son tres obreros, y GREASY reparte solo: mejor tres trabajando
# ya que ocho esperando.
#
# UNA TAREA POR NODO. Esta compilación de Ollama trae Vulkan, y Vulkan **no
# respeta CUDA_VISIBLE_DEVICES**: dos servidores en un nodo enumeran las cuatro
# H100 y a veces cargan el modelo en una tarjeta que ya tiene otro, con "failed
# to allocate Vulkan0 buffer" y la tanda perdida. Por eso --ntasks-per-node=1.
#
# GREASY da **un obrero por nodo**, no uno menos: con --nodes=2 el log dice
# "ready to run with 2 workers" y reparte en as05r3b03 y as05r3b11, o sea que el
# maestro comparte nodo con un obrero. El script viejo del brazo Python decía
# nodos−1; medido aquí, no es así. Cada línea levanta su propio Ollama.
# ────────────────────────────────────────────────────────────────────────
set -euo pipefail

cd "${SLURM_SUBMIT_DIR:-$(dirname "$0")}"
mkdir -p logs runs greasy_tasks

# Las listas viven en greasy_tasks/ y los ficheros de reinicio caen al lado,
# así que todo lo generado queda bajo un único directorio ignorado por git.
TASKS="${1:-greasy_tasks/tasks.txt}"
[ -f "$TASKS" ] || { echo "no existe el fichero de tareas: $TASKS" >&2; exit 1; }

echo "[plan] $(grep -cve '^[[:space:]]*$' -e '^[[:space:]]*#' "$TASKS") tareas" \
     "sobre ${SLURM_JOB_NUM_NODES:-1} obreros"
echo "[node] maestro en $(hostname) / ${SLURM_NODELIST:-?}"

# Lo mismo que valida submit_matrix.sh antes de gastar la asignación: en el nodo
# de login venv-hpc no importa nada, y eso se ve mejor aquí que en N logs.
want="$(sed -n 's/^version *= *\([0-9]*\.[0-9]*\).*/\1/p' venv-hpc/pyvenv.cfg)"
have="$(./venv-hpc/bin/python -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
[ "$want" = "$have" ] || { echo "venv-hpc espera python $want y este nodo da $have" >&2; exit 1; }
./venv-hpc/bin/python -c "import langgraph, yaml" || { echo "venv-hpc sin dependencias" >&2; exit 1; }
echo "[venv] python $have, langgraph ok"

module load openmpi/4.1.5-gcc
module load greasy
export GREASY_LOGFILE="logs/greasy_${SLURM_JOB_ID:-manual}.log"

greasy "$TASKS" || true

# GREASY deja un fichero de reinicio con lo que falló o no llegó a correr, y es
# a su vez un fichero de tareas válido. Lo nombra `<lista>-<jobid>.rst`, no
# `-restart` como dice su documentación: con el patrón equivocado el aviso no
# salía nunca y una tanda a medias parecía una tanda completa.
for restart in "$TASKS"-*.rst "$TASKS"-restart*; do
  [ -f "$restart" ] || continue
  echo "[greasy] $(grep -cve '^[[:space:]]*$' "$restart") tareas sin completar"
  echo "[greasy] reanudar con: sbatch submit_greasy.sh $restart"
done

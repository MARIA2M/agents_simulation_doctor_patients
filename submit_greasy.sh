#!/bin/bash
#SBATCH --job-name=ahead-greasy
#SBATCH --account=bsc02
#SBATCH --qos=acc_bscls
#SBATCH --partition=acc
#SBATCH --nodes=9
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=40
#SBATCH --gres=gpu:1
#SBATCH --time=06:00:00
#SBATCH --output=logs/greasy-%j.out
#SBATCH --error=logs/greasy-%j.err
# ────────────────────────────────────────────────────────────────────────
# Corre un fichero de tareas con GREASY. No genera nada y no sabe qué hay
# dentro: eso lo hace ./make_greasy_tasks.sh, y el fichero es texto plano.
#
#   ./make_greasy_tasks.sh > greasy_tasks.txt
#   mkdir -p logs && sbatch submit_greasy.sh greasy_tasks.txt
#   sbatch --nodes=5 submit_greasy.sh tasks.txt          # menos nodos
#   sbatch submit_greasy.sh greasy_tasks.txt-restart     # reanudar lo que falló
#
# UNA TAREA POR NODO. Esta compilación de Ollama trae Vulkan, y Vulkan **no
# respeta CUDA_VISIBLE_DEVICES**: dos servidores en un nodo enumeran las cuatro
# H100 y a veces cargan el modelo en una tarjeta que ya tiene otro, con "failed
# to allocate Vulkan0 buffer" y la tanda perdida. Por eso --ntasks-per-node=1.
#
# GREASY toma los obreros de SLURM_NTASKS y añade su maestro encima, así que
# --nodes=9 da 8 obreros. Cada línea del fichero levanta su propio Ollama.
# ────────────────────────────────────────────────────────────────────────
set -euo pipefail

cd "${SLURM_SUBMIT_DIR:-$(dirname "$0")}"
mkdir -p logs runs

TASKS="${1:-greasy_tasks.txt}"
[ -f "$TASKS" ] || { echo "no existe el fichero de tareas: $TASKS" >&2; exit 1; }

echo "[plan] $(grep -cve '^[[:space:]]*$' -e '^[[:space:]]*#' "$TASKS") tareas" \
     "sobre $((${SLURM_JOB_NUM_NODES:-1} - 1)) nodos obreros"
echo "[node] maestro en $(hostname) / ${SLURM_NODELIST:-?}"

module load openmpi/4.1.5-gcc
module load greasy
export GREASY_LOGFILE="logs/greasy_${SLURM_JOB_ID:-manual}.log"

greasy "$TASKS" || true

# GREASY deja un fichero de reinicio con lo que falló o no llegó a correr, y es
# a su vez un fichero de tareas válido.
for restart in "$TASKS"-restart*; do
  [ -f "$restart" ] && echo "[greasy] reanudar con: sbatch submit_greasy.sh $restart"
done

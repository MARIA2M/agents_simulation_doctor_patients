#!/bin/bash
#SBATCH --job-name=ahead-matrix
#SBATCH --account=bsc02
#SBATCH --qos=acc_debug
#SBATCH --partition=acc
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=40
#SBATCH --time=02:00:00
#SBATCH --output=logs/matrix-%j.out
#SBATCH --error=logs/matrix-%j.err
# ────────────────────────────────────────────────────────────────────────
# La matriz de repeticiones: 2 pacientes × 2 brazos × N repeticiones.
#
#   mkdir -p logs && sbatch submit_matrix.sh          # 2 pacientes, N=5
#   REPEATS=3 RUN=2 sbatch submit_matrix.sh          # segundo intento, no pisa el primero
#   PATIENTS="$(cd patients && ls *.json | sed 's/.json//')" sbatch submit_matrix.sh
#
# Para depurar a mano, la asignación interactiva equivalente (RUN.md §1):
#   salloc -A bsc02 -q acc_debug -p acc --gres=gpu:1 -c 40 -t 1:00:00 \
#     srun --export=ALL --pty bash
#
# Aquí NO hace falta el `srun --pty` de RUN.md: sbatch ya ejecuta el script en
# el nodo asignado. Ese aviso es solo para salloc, que lanza el comando en la
# máquina desde la que se invoca, y los login de ACC también tienen H100.
#
# -c 40 es memoria, no CPU: ACC da 8 GB por core y ollama carga 31.8 GB de
# pesos más la caché KV. 40 cores = 320 GB.
#
# Cuatro brazos por paciente, y cada uno cambia UNA cosa respecto a hpc:
#   hpc          línea base — coverage_hint off, estilo good_doctor
#   hint-show    cambia el hint
#   style-nb     cambia el estilo a narrowly_biomedical
#   style-bps    cambia el estilo a biopsychosocial, el opuesto del anterior
# Los dos últimos son el par antagónico: comparar uno con otro, no con hpc.
#
# Coste: e4-1 hizo 20 consultas en 35 min, o sea ~1,75 min cada una. El total
# es pacientes × 4 brazos × N, y hay que caber en --time:
#    2 pacientes, N=5   →  40 consultas ≈  70 min   entra en acc_debug (2 h)
#    2 pacientes, N=10  →  80 consultas ≈ 140 min   ya no
#   10 pacientes, N=5   → 200 consultas ≈  6 h      otra QOS, y subir --time
#   10 pacientes, N=3   → 120 consultas ≈ 3,5 h     otra QOS
# Subir --time no basta: acc_debug tiene su propio tope. Comprobar con
#   sacctmgr show qos format=Name,MaxWall
# ────────────────────────────────────────────────────────────────────────
set -euo pipefail

# Bajo sbatch, SLURM copia el script a su directorio de spool, así que
# BASH_SOURCE apunta allí y no al repositorio: `cd $(dirname ...)` dejaba el
# trabajo en el spool y moría en la comprobación del venv. SLURM_SUBMIT_DIR es
# el directorio desde el que se envió; el fallback sirve para ejecutarlo a mano.
cd "${SLURM_SUBMIT_DIR:-$(dirname "${BASH_SOURCE[0]}")}"

# Sin esto Python escribe stdout por bloques cuando va a fichero, y el log de
# sbatch avanza a saltos de varios KB: una tanda en marcha parece colgada.
export PYTHONUNBUFFERED=1

REPEATS="${REPEATS:-5}"
RUN="${RUN:-1}"
PATIENTS="${PATIENTS:-CLL-001 HIV-003}"
PY=./venv-hpc/bin/python

# El nombre de la tanda se lee solo, sin abrir run_meta.json:
#     CLL-001x5-off-narrowly_biomedical-run1
#     quién · repeticiones · modo · estilo · intento
# Las repeticiones van dentro del nombre porque deciden qué métricas admite la
# tanda: con x5 hay dispersión (2.4) y con x2 no. Modo y estilo son
# interruptores independientes (§4.1), así que van los dos: la línea base es
# off + good_doctor y cada brazo mueve uno solo. `run1` es el intento; las
# repeticiones viven dentro como CLL-001-r1, -r2…

# ── Dónde estamos ───────────────────────────────────────────────────────
# Las dos señales de §6.3. En sbatch deberían cuadrar siempre; si no cuadran,
# es que el trabajo no está donde cree, y más vale saberlo antes de medir.
echo "[node] $(hostname) / ${SLURM_NODELIST:-?}"
nvidia-smi -L || { echo "sin GPU visible"; exit 1; }

# ── El intérprete, antes que nada ───────────────────────────────────────
# venv-hpc no lleva python propio: bin/python3 es un enlace a /usr/bin/python3,
# y sus paquetes están en lib/python3.9. En el nodo de cómputo /usr/bin/python3
# es 3.9 y todo encaja; en el login es 3.10 y el venv no importa nada. Se
# comprueba aquí y no después porque cargar el modelo cuesta medio minuto y una
# asignación entera se puede perder por esto.
want="$(sed -n 's/^version *= *\([0-9]*\.[0-9]*\).*/\1/p' venv-hpc/pyvenv.cfg)"
have="$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
if [ "$want" != "$have" ]; then
  echo "venv-hpc espera python $want y este nodo da $have."
  echo "Si dice 3.10 estás en un nodo de login: venv-hpc solo sirve en el de cómputo."
  exit 1
fi
"$PY" -c "import langgraph, yaml" || { echo "venv-hpc no tiene las dependencias"; exit 1; }
echo "[venv] python $have, langgraph ok"

# ── Servidor ────────────────────────────────────────────────────────────
# Exporta OLLAMA_MODELS, OLLAMA_URL y OLLAMA_NUM_PARALLEL. El último tiene que
# ir antes de arrancar el servidor: llm.py no puede enviarlo como opción, y sin
# él el servidor reparte el contexto entre slots y trunca en silencio.
. ./serve_ollama.sh

# Carga los pesos ahora. Si no, los ~30 s desde GPFS los paga la primera
# llamada del médico y cuentan como parte del primer turno (§6.1).
echo "[warm] cargando el modelo del médico…"
time curl -s "$OLLAMA_URL/api/chat" -d '{
  "model":"glm-4.7-flash:q8_0",
  "messages":[{"role":"user","content":"hi"}],
  "stream":false,"keep_alive":"4h"}' > /dev/null

# ── La matriz ───────────────────────────────────────────────────────────
# Sin --allow-dirty a propósito: run_batch aborta con el árbol sucio, porque
# entonces git_commit nombra otro código y la tanda no se podría reproducir.
run () {   # run <perfil> <paciente> <modo> <estilo>
  local profile="$1" patient="$2" mode="$3" style="$4"
  local id="${patient}x${REPEATS}-${mode}-${style}-run${RUN}"
  echo
  echo "═══ $id — perfil $profile, $REPEATS repeticiones"
  "$PY" run_batch.py \
    --profile "$profile" \
    --patients "patients/${patient}.json" \
    --repeats "$REPEATS" \
    --run-id "$id"
}

for patient in $PATIENTS; do
  run hpc                       "$patient" off  good_doctor
  run hint-show                 "$patient" show good_doctor
  run style-narrowly_biomedical "$patient" off  narrowly_biomedical
  run style-biopsychosocial     "$patient" off  biopsychosocial
done

echo
echo "listo. las tandas están en runs/*-run${RUN}"

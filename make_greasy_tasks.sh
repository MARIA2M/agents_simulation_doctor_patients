#!/bin/bash
# make_greasy_tasks.sh — imprime el fichero de tareas. Nada más.
#
#   ./make_greasy_tasks.sh > greasy_tasks.txt              # profunda: 1 paciente por tanda
#   WIDE=1 REPEATS=2 ./make_greasy_tasks.sh > wide.txt     # ancha: todo el corpus por tanda
#   REPEATS=5 RUN=2 ./make_greasy_tasks.sh > tasks.txt
#   PATIENTS="CLL-001 HIV-003" ARMS="nb bps" ./make_greasy_tasks.sh > tasks.txt
#
# Una línea = una tanda = un nodo. Cada línea es autosuficiente: levanta su
# propio Ollama con serve_ollama.sh, que no hace nada si ya hay uno respondiendo
# en ese nodo, y luego corre run_batch.py.
#
# ── EL NOMBRE DE LA TANDA ────────────────────────────────────────────────
# Se lee solo, sin abrir run_meta.json ni acordarse de ningún prefijo:
#
#     CLL-001x5-off-narrowly_biomedical-run1
#     └─────┘└┘ └─┘ └─────────────────┘ └──┘
#      quién  rep modo      estilo      intento
#
# **Las repeticiones van en el nombre** porque son lo que decide qué métricas
# admite la tanda, y es lo que más se confunde al comparar dos:
#
#     all10x2-…     ancha:    10 pacientes × 2 → cobertura y discriminación,
#                             NO dispersión (2.4 pide N≥5)
#     CLL-001x5-…   profunda:  1 paciente × 5 → dispersión,
#                             NO discriminación (hace falta más de un paciente)
#
# Modo y estilo son interruptores **independientes** (ARCHITECTURE §4.1), así
# que van los dos: la línea base es `off` + `good_doctor` y cada brazo mueve uno
# solo. Los cuatro:
#
#     off  + good_doctor           línea base
#     show + good_doctor           cambia el modo
#     off  + narrowly_biomedical   cambia el estilo
#     off  + biopsychosocial       el estilo opuesto
#
# `run1` es el intento, no la repetición: las repeticiones viven dentro, como
# CLL-001-r1, CLL-001-r2… Repetir la misma configuración más adelante es run2 y
# no pisa nada.
#
# El fichero es texto plano: míralo, córtalo, reordénalo o quédate con dos
# líneas. GREASY no necesita saber de dónde salió.

set -euo pipefail
cd "$(dirname "$0")"

REPEATS="${REPEATS:-5}"
RUN="${RUN:-1}"
PATIENTS="${PATIENTS:-$(cd patients && ls *.json | sed 's/\.json$//')}"
ARMS="${ARMS:-off show nb bps}"
WIDE="${WIDE:-}"
BASE="$PWD"

# brazo → "perfil modo estilo"
arm_parts () {
  case "$1" in
    off)  echo "hpc                        off  good_doctor" ;;
    show) echo "hint-show                  show good_doctor" ;;
    nb)   echo "style-narrowly_biomedical  off  narrowly_biomedical" ;;
    bps)  echo "style-biopsychosocial      off  biopsychosocial" ;;
    *)    echo "brazo desconocido: $1" >&2; exit 1 ;;
  esac
}

task () {   # task <quién> <selección de pacientes> <brazo>
  local who="$1" selection="$2" arm="$3"
  local profile mode style id
  read -r profile mode style <<<"$(arm_parts "$arm")"
  id="${who}x${REPEATS}-${mode}-${style}-run${RUN}"

  # Separado por `;` y no por `&&`, a propósito. serve_ollama.sh termina con un
  # `curl | grep` que lista los modelos, y ese grep devuelve 1 cuando no casa
  # nada: con `&&` la cadena moría ahí, run_batch no llegaba a ejecutarse y —lo
  # peor— la redirección al log tampoco, así que las cinco tareas de la primera
  # prueba fallaron sin dejar rastro. Con `;` python corre siempre y su salida
  # acaba siempre en el log, que es lo que hace diagnosticable un fallo.
  echo "cd $BASE; . ./serve_ollama.sh >/dev/null 2>&1; ./venv-hpc/bin/python run_batch.py --profile $profile $selection--repeats $REPEATS --run-id $id > logs/${id}.log 2>&1"
}

if [ -n "$WIDE" ]; then
  # Todo el corpus en una tanda: sin --patients, run_batch los coge todos.
  count=$(echo "$PATIENTS" | wc -w)
  for arm in $ARMS; do
    task "all${count}" "" "$arm"
  done
else
  for patient in $PATIENTS; do
    for arm in $ARMS; do
      task "$patient" "--patients patients/${patient}.json " "$arm"
    done
  done
fi

#!/bin/bash
# make_greasy_tasks.sh — imprime el fichero de tareas. Nada más.
#
#   ./make_greasy_tasks.sh > greasy_tasks.txt
#   REPEATS=5 PREFIX=g1 ./make_greasy_tasks.sh > greasy_tasks.txt
#   PATIENTS="CLL-001 HIV-003" ARMS="nb bps" ./make_greasy_tasks.sh > tasks.txt
#
# Una línea por (paciente, brazo) = una tanda = un nodo. Cada línea es
# autosuficiente: levanta su propio Ollama con serve_ollama.sh, que no hace nada
# si ya hay uno respondiendo en ese nodo, y luego corre run_batch.py.
#
# El fichero es texto plano: míralo, córtalo, reordénalo o quédate con dos
# líneas. GREASY no necesita saber de dónde salió.

set -euo pipefail
cd "$(dirname "$0")"

REPEATS="${REPEATS:-5}"
PREFIX="${PREFIX:-g1}"
PATIENTS="${PATIENTS:-$(cd patients && ls *.json | sed 's/\.json$//')}"
ARMS="${ARMS:-off show nb bps}"
BASE="$PWD"

profile_of () {
  case "$1" in
    off)  echo hpc ;;
    show) echo hint-show ;;
    nb)   echo style-narrowly_biomedical ;;
    bps)  echo style-biopsychosocial ;;
    *)    echo "brazo desconocido: $1" >&2; exit 1 ;;
  esac
}

for patient in $PATIENTS; do
  tag="$(echo "$patient" | tr 'A-Z' 'a-z' | tr -d '-')"
  for arm in $ARMS; do
    id="${PREFIX}-${tag}-${arm}"
    echo "cd $BASE && . ./serve_ollama.sh >/dev/null 2>&1 && ./venv-hpc/bin/python run_batch.py --profile $(profile_of "$arm") --patients patients/${patient}.json --repeats $REPEATS --run-id $id > logs/${id}.log 2>&1"
  done
done

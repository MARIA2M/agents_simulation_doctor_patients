# Cómo lanzar una consulta

Dos perfiles, mismo código (§6). `local` en el nodo de login para humo y tests;
`hpc` en un nodo de cómputo para lo que se mide.

Cada paso está por una razón concreta. Saltarse uno no da error: da una corrida
que parece buena y no lo es.

---

## Copiar y pegar

El porqué de cada línea está más abajo. Aquí solo están, en orden.

**Tests** (nodo de login, sin servidor):

```bash
cd /gpfs/projects/bsc02/bsc064212/AHEAD/use_cases/patient_doctor_agents/agents_simulations
./venv-local/bin/python -m pytest tests/ -q
```

**Consulta en local** (humo, `llama3.2`):

```bash
cd /gpfs/projects/bsc02/bsc064212/AHEAD/use_cases/patient_doctor_agents/agents_simulations
. serve_ollama.sh
./venv-local/bin/python main.py --patient patients/CLL-003.json --profile local
```

**Consulta en HPC** (`glm-4.7-flash:q8_0`). Primero, desde el login:

```bash
cd /gpfs/projects/bsc02/bsc064212/AHEAD/use_cases/patient_doctor_agents/agents_simulations
salloc -A bsc02 -q acc_debug -p acc --gres=gpu:1 -c 40 -t 1:00:00 \
  srun --export=ALL --pty bash
```

Y ya dentro del nodo, de una vez:

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

**Ver qué salió:**

```bash
ls runs/s3-1/
python3 -c "import json; t=json.load(open('runs/s3-1/transcript.json')); print(t['turns'], t['stop_reason'], len(t['events']))"
```

---

## Tests

Sin servidor: el LLM está sustituido por respuestas guionizadas.

```bash
./venv-local/bin/python -m pytest tests/ -q
```

Uno queda fuera por defecto, el de la consulta entera de punta a punta. Es el
único que construye el grafo, y construirlo importa `langgraph`:

```bash
AHEAD_GRAPH_TESTS=1 ./venv-local/bin/python -m pytest tests/ -q
```

**`import langgraph` tarda ~3 minutos leyendo de GPFS**, medido dos veces con
el mismo resultado, así que no es la caché fría: son miles de ficheros pequeños
y el coste es de metadatos. `main.py` lo paga también, antes de la primera
llamada al modelo. En el nodo de cómputo conviene copiar el venv al disco local
antes de una tanda; leerlo de GPFS en cada tarea no escala, igual que pasa con
los pesos (§6.1).

---

## Antes de nada: commitear

`metadata.code.dirty` marca si el árbol tenía cambios sin commitear. Si es
`true`, el `git_commit` de la corrida no describe el código que la produjo y la
corrida no es reproducible.

```bash
git status --short          # vacío antes de una corrida que quieras guardar
```

Para humo da igual. Para una línea base, no.

---

## Local (nodo de login)

```bash
cd /gpfs/projects/bsc02/bsc064212/AHEAD/use_cases/patient_doctor_agents/agents_simulations

export OLLAMA_NUM_PARALLEL=1
. serve_ollama.sh

./venv-local/bin/python main.py --patient patients/CLL-003.json --profile local
```

Nada de este perfil entra en métricas publicadas: dice que el código corre, no
cuánto acierta el médico.

---

## HPC (nodo de cómputo)

### 1. Reservar y aterrizar en el nodo

```bash
cd /gpfs/projects/bsc02/bsc064212/AHEAD/use_cases/patient_doctor_agents/agents_simulations

salloc -A bsc02 -q acc_debug -p acc --gres=gpu:1 -c 40 -t 1:00:00 \
  srun --export=ALL --pty bash
```

El `srun` de dentro **no es opcional** (§6.3). `salloc` reserva los recursos
pero ejecuta el comando en la máquina desde la que se invoca, y los nodos de
login de ACC también tienen H100: sin `srun` todo parece correcto mientras el
nodo reservado no hace nada.

`-c 40` es por memoria, no por CPU: ACC da 8 GB por core, y a ollama lo mataron
cargando 31.8 GB de pesos más la caché KV. 40 cores = 320 GB.

### 2. Comprobar dónde estás

```bash
hostname; echo "$SLURM_NODELIST"     # tienen que ser iguales
nvidia-smi -L                        # 1 GPU, no 4
```

Las dos señales del §6.3. Si `hostname` dice `alogin*` o salen 4 GPUs, estás en
el nodo de login: sal y repite el paso 1.

### 3. Levantar el servidor

```bash
. serve_ollama.sh
```

Exporta `OLLAMA_MODELS` (los modelos del proyecto no están en `~/.ollama`),
`OLLAMA_HOST`, el `PATH` del binario, `OLLAMA_URL` —que lee `load_config` y
acaba en `metadata.server.ollama_url`— y `OLLAMA_NUM_PARALLEL`.

Este último tiene que estar **antes** de que arranque el servidor: es una
variable del servidor, no una opción de la petición, así que `llm.py` no puede
enviarla. Sin ella el servidor usa su valor por defecto, reparte el contexto
entre slots y trunca en silencio, mientras `metadata.sampling.num_parallel`
sigue diciendo 1.

Debería listar los cuatro modelos: `glm-4.7-flash:q8_0`, `dolphin-llama3`,
`llama3.2`, `nomic-embed-text`.

### 4. Calentar el modelo

```bash
time curl -s "$OLLAMA_URL/api/chat" -d '{
  "model":"glm-4.7-flash:q8_0",
  "messages":[{"role":"user","content":"hi"}],
  "stream":false,"keep_alive":"4h"}' > /dev/null
```

Carga los pesos en la GPU. Son ~30 s desde GPFS que, si no, los paga la primera
llamada del médico contra un timeout de 300 s y contando como parte del primer
turno (§6.1). Si tarda mucho más, algo va mal antes de medir nada.

### 5. Correr

```bash
./venv-hpc/bin/python -c "import langgraph; print('venv ok')"
./venv-hpc/bin/python main.py --patient patients/CLL-003.json --profile hpc --run-id hpc-test-1
```

`venv-hpc` **solo funciona en el nodo de cómputo**. Su `bin/python3` apunta a
`/usr/bin/python3`, que allí es 3.9 y coincide con su `site-packages`; en el
nodo de login es 3.10 y no importa nada. En login se usa `venv-local`.

---

## Después

```bash
ls runs/hpc-test-1/                  # metadata.json + transcript.json
```

Tres cosas que mirar en `transcript.json`:

- `stop_reason` — `doctor` es lo que se busca. `turn_cap` significa que cortó el
  tope, no el médico. `malformed_call` es un fallo de tool calling.
- `events` — vacío es una corrida limpia. Cualquier cosa ahí (reintentos, turnos
  vacíos) hay que leerla antes de creerse el resultado.
- `turns` — 10–15 es una consulta de verdad. 1 turno es el médico cerrando
  inmediatamente, que es lo que hace `llama3.2` con cualquier prompt.

Y en `metadata.json`, `prompts.doctor`: el hash identifica qué versión del
prompt produjo esto. Es lo que permite atribuir un cambio de resultado a un
cambio de prompt y no a otra cosa.

---

## Variantes de prompt

No hay un perfil por prompt. Se cambia la línea `prompts.doctor` de
`config/hpc.yaml` y el hash de `metadata.json` registra cuál se usó:

| Fichero | Qué es |
|---|---|
| `DOCTOR.md` | El de por defecto |
| `DOCTOR-plain.md` | Versión corta, sin estructura de sesión |
| `DOCTOR-cues.md` | Con la columna de señales conductuales — mide el espejo de 5.5 |
| `DOCTOR-ruby.md` | El del brazo Ruby, sin su sección 5 (el informe llega aparte) |

Una variable por corrida: cambia el prompt o cambia el modelo, no las dos cosas.

# AHEAD — Arquitectura e instrucciones de construcción

Documento de diseño para la reimplementación. Las tareas numeradas (`1.5`, `2.1`…)
remiten a [TASKS.md](TASKS.md).

---

## 1. Decisiones de base

| Decisión | Qué significa |
|---|---|
| **Runtime** | Python + LangGraph. |
| **Paradigma** | Inferencia, no elicitación. El médico conversa libre e infiere; nunca recita ítems del cuestionario. |
| **Comportamiento agéntico** | El del brazo Ruby/Scout: el paciente es una **herramienta** del médico, no un nodo par. |
| **Estilo de código** | El del brazo Python actual, para poder reutilizar el frontend y el `api_server`. |
| **Base de partida** | `python_version/ahead_agent-bmq-integration`. |

### 1.1 La pieza que hay que emular

En Scout, `delegate` registra al paciente como una función del médico:

```ruby
doctor.delegate patient, :patient, "Ask this patient questions"
# → expone la tool `hand_off_to_patient(message:, new_conversation:)`
```

El médico es un agente normal con tools. Hablar con el paciente **es una llamada
a herramienta**. De ahí salen tres propiedades que el brazo Python actual no tiene:

- Los turnos no están preestablecidos: el médico llama a la tool cuando quiere (1.3).
- El médico decide cuándo parar: deja de llamarla y pasa a escribir (1.5).
- El transcript es un subproducto: se reconstruye de los pares
  `function_call` / `function_call_output`.

**En LangGraph esto es un bucle agente↔herramienta**, no una cadena de nodos fijos:

```
                 ┌──────────────────────────────┐
                 │                              │
                 ▼                              │
  START ──► doctor ──(tool_call: speak)──► patient_tool
                 │                              │
                 └──(sin tool_call)──► report ──► END
```

`patient_tool` invoca al LLM del paciente con su perfil y devuelve la respuesta
como resultado de herramienta. El médico la recibe y decide: volver a preguntar,
o terminar. `report` **siempre** se ejecuta al salir del bucle (1.13).

Contraste con lo que hay hoy en `graph.py`: un recorrido por lista de preguntas
con `q_index` y `bmq_index`. Eso desaparece por completo.

**Libre no significa concurrente** (1.4). El bucle es estrictamente secuencial:
cada turno ve el estado completo del anterior. Las llamadas al LLM son `async`
por transporte, pero nunca hay dos turnos en vuelo a la vez. Lo que es libre es
*cuándo* y *cuántas veces* habla el médico, no el orden.

---

## 2. Estructura de ficheros

Espeja la actual para que el frontend y el estilo de importación sigan valiendo.
`NUEVO` = no existe hoy. `PORTAR` = viene del paquete actual.

```
ahead_agent_v2/
├── main.py                  # CLI, misma forma que el main.py actual
├── api_server.py            # FastAPI (ver §7)
├── run_batch.py             # PORTAR — N corridas × M pacientes
│
├── ahead_agent/
│   ├── __init__.py          # reexporta State y build_graph (este último, perezoso)
│   ├── config.py            # CONFIG, modelos, rutas. SIN lista de preguntas
│   ├── state.py             # State TypedDict (§3)
│   ├── graph.py             # build_graph() — único sitio que toca StateGraph
│   ├── nodes.py             # doctor_node, patient_tool_node, report_node
│   ├── routing.py           # route_after_doctor
│   ├── tools.py             # NUEVO — equivalente a delegate de Scout
│   ├── prompts.py           # NUEVO — carga de markdown: prompts, skills, recursos
│   ├── llm.py               # PORTAR — cliente HTTP, reintentos (3.1)
│   ├── patient_profile.py   # PORTAR — perfil → prompt de paciente
│   │
│   ├── report.py            # NUEVO — esquema, parseo, validación, reintento (§4)
│   ├── evaluation.py        # PORTAR — MAE, sesgo, Pearson, ICC (4.2)
│   ├── coverage.py          # NUEVO — 3.2, mapa de cobertura + verificación de citas
│   ├── reproducibility.py   # NUEVO — 3.3, dispersión (2.4) y discriminación (2.5)
│   ├── artifacts.py         # NUEVO — 5.4, transcript cruzado y ablación
│   │
│   ├── api/
│   │   ├── doctor.py        # PORTAR/adaptar — ahora con tools
│   │   ├── patient.py       # PORTAR casi tal cual
│   │   └── reporter.py      # NUEVO — sustituye a scorer.py
│   │
│   └── causes/              # PORTAR sin cambios — embeddings, similitud, scorer
│
├── config/                  # perfiles de ejecución (§6)
│   ├── base.yaml            # 0.5 — lo compartido; no es un perfil, no carga solo
│   ├── local.yaml           # modelos pequeños, escala de humo
│   └── hpc.yaml             # modelos grandes, tandas completas
├── prompts/
│   ├── DOCTOR.md            # rol del médico
│   ├── PATIENT.md           # rol del paciente
│   └── rubric/              # 2.2 — anclas 2/4/6/8 LADO MÉDICO
│       ├── bipq.md
│       └── bmq.md
├── skills/
│   └── styles/              # 6.5 — un .md por estilo de comunicación
├── resources/               # 1.8 — CSM, NCF, terminología
├── patients/                # perfiles + ground truth
└── runs/                    # salidas por corrida
```

`build_graph` se resuelve al pedirlo, no al importar el paquete: `graph.py` trae
langgraph, que desde GPFS tarda unos tres minutos, y un reexport normal se lo
cobraría a cualquier import — incluidos los de post-proceso, que no tocan el
grafo. Es también lo que permite que los dos tests de punta a punta sigan detrás
de `AHEAD_GRAPH_TESTS=1` sin arrastrar al resto de la suite.

**Estructura plana, como hoy.** El paquete actual tiene 9 módulos de primer nivel
y solo dos subpaquetes (`api/`, `causes/`). Se mantiene igual: `report.py`,
`coverage.py`, `reproducibility.py` y `artifacts.py` son módulos sueltos, no
paquetes. Si alguno pasa de ~400 líneas se parte entonces, no antes.

**Regla de dependencias.** `nodes` → `api` → `llm`. `evaluation`, `coverage`,
`reproducibility`, `artifacts` y `causes` no importan nada de `nodes`/`graph`:
son post-proceso puro y deben poder ejecutarse sobre corridas de cualquier brazo,
incluido el de elicitación (5.2).

---

## 3. Estado

```python
class State(TypedDict):
    # ── Conversación ──
    conversation: List[Dict]      # [{"role": "doctor"|"patient", "content": str, "turn": int}]
    doctor_messages: List[Dict]   # historial del LLM médico, con tool_calls
    turn_count: int
    finished: bool                # el médico cerró la consulta (1.5)
    coverage_hint: Dict[str, str] # dimensión → "covered"; ausente = sin sondear (§4.1)
    working_notes: List[Dict]     # [{turn, dimension, observation}] (§4.1)

    # ── Paciente ──
    profile: Dict                 # JSON completo. SOLO lo lee patient_tool_node
    patient_messages: List[Dict]

    # ── Salida ──
    report_raw: Optional[str]
    report: Optional[Report]      # ver §4
    report_attempts: int

    # ── Trazabilidad ──
    run_meta: RunMeta             # 0.4
    events: List[Dict]            # reintentos, fallos, turnos vacíos
```

Fuera: `q_index`, `bmq_index`, `follow_up_count`, `scores`, `bmq_scores`. No hay
puntuación incremental — se emite entera al final (1.11).

### 3.1 Invariante de aislamiento (1.2)

> `profile` no aparece jamás en el contexto del médico.

No es un comentario, es un test. `patient_tool_node` es el único que lee
`state["profile"]`. Añadir en la suite una comprobación que serialice todos los
mensajes enviados al médico y falle si contiene cualquier valor de `belief_profile`.

Modelos distintos para médico y paciente: `CONFIG["doctor_model"]` y
`CONFIG["patient_model"]`. El config actual llama `model` al del médico; conviene
renombrarlo a `doctor_model` al portarlo, porque `model` a secas también servía
al scorer, que ya no existe.

### 3.2 `run_meta`: provenance de la corrida (0.4)

Todo lo necesario para interpretar los resultados de una corrida meses después.
Se escribe **una vez al empezar**, junto a las salidas, en `runs/<run_id>/run_meta.json`.
Precedente a copiar: el `manifest.json` de `run_config.rb` en el brazo Ruby.

```jsonc
{
  "run_id": "20260819-161200",
  "started_at": "2026-08-19T16:12:00+02:00",
  "profile": "hpc",                        // local | hpc (§6)

  "models":   { "doctor": "glm-4.7-flash:q8_0",
                "patient": "dolphin-llama3",
                "embed": "jina-embeddings-v4" },

  "sampling": { "temperature": 0.7,        // SIEMPRE explícita (§12)
                "seed": null,
                "context_length": 32768,
                "num_parallel": 1 },

  "features": { "coverage_hint": "off",    // el brazo de la corrida (§4.1)
                "working_notes": false },

  "prompts":  { "doctor": "sha256:a1b2…",  // hash del prompt YA compuesto (§5.1)
                "patient": "sha256:c3d4…",
                "rubric": "sha256:e5f6…",
                "skills": ["styles/empathic"] },

  "code":     { "git_commit": "9f2c1ab", "dirty": false },

  "compute":  { "hostname": "as01r1b18", "slurm_job": "44820726", "gpus": 1 },

  "corpus":   { "patients": 10, "ground_truth_source": "patients/*.json" }
}
```

Sin esto, el método de "una variable por corrida" no funciona: al ver que el MAE
cambió entre dos corridas no podrías saber si fue por el cambio que hiciste o por
otra cosa. Tres campos que parecen menores y no lo son:

- **`dirty`** — si había cambios sin commitear, `git_commit` miente. Marcarlo
  evita creer que una corrida es reproducible cuando no lo es.
- **`temperature`** — se registra lo que se **envió**, no lo que se supone. Un
  servidor con su propio valor por defecto cambia los resultados en silencio.
- **hashes de prompts** — son lo que hace medible la fase 6: atribuyen un cambio
  de resultado a un cambio de prompt concreto.
- **`features`** — el brazo (§4.1). Los valores compartidos viven en `base.yaml`
  desde 0.5, así que el fichero de perfil ya no los enseña: si no se copian
  aquí, una corrida con `coverage_hint: show` es indistinguible de la línea base
  al leerla meses después.

---

## 4. Contrato del informe

El médico devuelve **una sola** estructura al final. Es el corazón de la fase 2.

```python
@dataclass
class Evidence:
    quote: str          # cita literal del transcript
    turn: int           # turno del que sale

@dataclass
class DimensionScore:
    dimension: str
    evidence: List[Evidence]   # PRIMERO
    reasoning: str             # SEGUNDO
    score: float | None        # TERCERO — None = NA (4.4)
    confidence: float          # 0–1, declarada por el médico (2.3)

@dataclass
class Report:
    patient_id: str
    clinical_summary: str
    bipq: Dict[str, DimensionScore]    # 8 dimensiones
    bmq:  Dict[str, DimensionScore]    # en ve subescalas
    causes: List[str]                  # abierto, ranked
    causes_evidence: List[Evidence]
```

**El orden de los campos es la especificación** (2.1). El prompt y el esquema de
salida deben forzar `evidence → reasoning → score`. Hoy la tabla de Ruby es
`Score | Rationale`, así que la justificación se genera después del número y es
decorativa; el scorer de Python devuelve el número desnudo.

**Política NA** (4.4). `score = None` cuando no se puede extraer, no se sondeó la
dimensión, o el JSON no parsea. Nunca un valor por defecto. Un NA:

- se excluye del MAE,
- se cuenta en la tasa de cobertura,
- aparece como hueco en el mapa de 3.2.

**Validación y reintento** (1.13). `report.py` comprueba las 12 dimensiones +
causas. Si falta algo, reintento con el mismo transcript y un prompt que señale
explícitamente qué falta. Máximo 3 intentos (`limits.report_attempts`); lo que siga faltando queda NA y se
registra en `events`.

### 4.1 Sondeo dirigido por ambigüedad (1.12) — decidido

El médico repregunta cuando la **evidencia es insuficiente**, no cuando la
respuesta es corta. El routing viejo de Python disparaba con
`len(respuesta) < 10 palabras`, así que una respuesta larga y vaga pasaba directa
a puntuación. Esa regla no existe aquí y no vuelve.

Lo que sí se decidió, al cerrar la Etapa 3, es **cómo se sostiene**. La primera
versión de esta sección daba por hecho que el médico llevaría su propia lista y
la consultaría antes de cerrar. Eso es un brazo, no la línea base: una lista de
dimensiones que el médico recorre es el cuestionario que 1.3 sacó del código,
entrando otra vez por la puerta de atrás, y fuerza una cobertura que después
infla el resultado.

Se implementa como **dos interruptores independientes**, declarados en el bloque
`features` —en `base.yaml`, o sobrescrito por el perfil— y copiados a `run_meta`
tal como quedan al fundirse (0.4):

```yaml
features:
  coverage_hint: "off"     # off | show
  working_notes: false
```

Independientes a propósito: recordarle lo que le falta y pedirle que anote lo
que concluye son intervenciones distintas, y en un solo valor no se sabría cuál
produjo el efecto.

| `coverage_hint` | `working_notes` | Qué es |
|---|---|---|
| `off` | `false` | **Línea base.** Ni se le pregunta ni se le dice. |
| `show` | `false` | Se le devuelve lo que queda abierto, en cada respuesta. |
| `off` | `true` | Anota lo que concluye, sin que se le diga nada. |
| `show` | `true` | Las dos cosas. Es el modo de la demo. |

**La línea base es `off` / `false`**, y con ella 1.12 se queda deliberadamente
**sin mecanismo**: el médico sondea lo que quiere y la cobertura se reconstruye
después desde el transcript (3.2). No preguntar por una dimensión es un
resultado, no un fallo que haya que evitar en vivo.

El estado que sostiene la cobertura es mínimo — una dimensión pasa a
`"covered"` cuando el médico lo declara, y no hay estado intermedio:

```python
coverage_hint: Dict[str, str]   # dimensión → "covered"; ausente = sin sondear
```

#### `working_notes` — lo único que puede enseñar si el médico revisa

El médico anota, en la misma llamada a la herramienta y sin llamadas extra, lo
que cada respuesta le dice sobre una dimensión. No hay campo de puntuación: eso
sigue siendo del final y con el transcript entero (1.11).

```python
working_notes: List[Dict]   # [{"turn", "dimension", "observation"}]
```

**Se añaden, nunca se sustituyen.** Dos entradas de la misma dimensión en turnos
distintos son un cambio de opinión fechado:

```python
{"turn": 2, "dimension": "consequences",
 "observation": "Ha dejado el paseo de después de cenar. Suena a renuncia."}
{"turn": 6, "dimension": "consequences",
 "observation": "Antes lo leí como renuncia, pero aclara que puede y no le
                 apetece. Es menos limitación de lo que parecía."}
```

Toda la arquitectura del informe al final se apoya en que información tardía
pueda corregir una impresión temprana, y **no hay ni una observación de que eso
ocurra**. Este es el único brazo que la produce.

Lo que cuesta: adelanta parte del juicio. Al puntuar, el médico llega con sus
impresiones ya escritas, así que **sus resultados no son comparables con la
línea base** y hay que decirlo al reportarlos.

Hubo un tercer modo de `coverage_hint`, `declare` —declarar sin recibir nada—,
pensado para cruzar lo que el médico cree haber explorado contra lo que exploró.
**Retirado**: sus propias declaraciones vuelven en el historial dentro de los
`tool_calls`, así que podía releerse y el brazo no aislaba lo que decía aislar.

Y una nota de forma que resultó no ser menor: el recordatorio de `show` viaja
como mensaje aparte con `role: user` —el mismo canal que el `OPENING`—, nunca
dentro del resultado de la herramienta. En ese canal el médico no puede
distinguir nuestras palabras de las del paciente, y `Evidence.quote` tiene que
ser una cita literal suya.

**Lo que se ve con `off`** (tanda `e4-1`, 10 pacientes × 2): `general_overuse`
queda NA en 5 de 10 pacientes y lleva número en los otros 5; las dos subescalas
`specific_*` reciben número en los 3 pacientes sin receta. Es exactamente lo que
esta sección predice y lo que 3.2 tiene que hacer visible: la cobertura no se
fuerza, se mide.

---

## 5. Prompts, skills y recursos

Los tres se cargan desde disco con `prompts.py`, nunca embebidos en código (1.6).

- **`prompts/DOCTOR.md`, `prompts/PATIENT.md`** — rol base.
- **`prompts/rubric/`** (2.2) — anclas 2/4/6/8 por dimensión, **lado médico**.
  Escritas desde criterios clínicos. **No invertir las bandas de
  `patient_profile.py`**: eso reconstruye el espejo (5.5). Que existan las dos
  sin ser la misma tabla es el objetivo.
- **`skills/`** (1.7, 6.5) — fragmentos que se componen sobre el prompt base.
  Los estilos de comunicación del médico son ficheros aquí, no ramas de código.
  **Composición determinista, no carga decidida por el modelo** — ver §5.1.
- **`resources/`** (1.8) — CSM, NCF, terminología. Pendiente decidir si se
  inyectan siempre o vía recuperación; dejar la interfaz preparada para ambas.

Cada fichero se hashea y el hash va a `run_meta` (0.4), para poder atribuir un
resultado a una versión de prompt.

### 5.1 Qué significa "skill" aquí (1.7)

**No es el mecanismo de skills de Claude.** Ahí el modelo decide por sí mismo qué
skill cargar y cuándo, mediante descubrimiento progresivo. Los modelos de este
proyecto —llama3.2, GLM, los grandes de HuggingFace— no hacen eso de forma
fiable, y montar el diseño sobre esa suposición lo rompería en silencio.

Aquí una skill es **un fragmento de markdown que el orquestador concatena al
prompt del sistema antes de la llamada**. Quién decide qué se carga es el código,
según el perfil de ejecución y el brazo experimental, no el modelo.

```python
build_prompt("DOCTOR.md", skills=["styles/empathic"], resources=["csm"])
# → un único string de sistema, determinista y hasheable
```

Tres consecuencias:

1. **Es agnóstico del modelo.** Funciona igual con cualquier backend porque solo
   manipula texto antes de enviarlo.
2. **Es reproducible.** El hash del prompt compuesto va a `run_meta` (0.4). Con
   carga decidida por el modelo no sabrías qué prompt produjo qué resultado.
3. **Hay que verificar que el fragmento surte efecto.** Que se concatene no
   garantiza que el modelo lo obedezca: un modelo pequeño puede ignorar una
   instrucción de estilo enterrada en un prompt largo. **Test de la etapa 2:**
   componer dos skills opuestas, correr la misma consulta con cada una, y
   comprobar que los transcripts difieren de forma observable. Si no difieren, el
   mecanismo no funciona con ese modelo por mucho que el código sea correcto.

### 5.2 Perfil de paciente y espacio para personalidades (1.9, 7.1)

La estructura actual se conserva: `disease_profile` (diagnóstico, estadio,
tratamiento, síntomas, laboratorio, demografía) + `belief_profile` (B-IPQ, BMQ,
causas) como ground truth.

Se añade **un bloque `persona` opcional**, separado del `belief_profile`:

```jsonc
"persona": {
  "communication_style": "guarded",     // locuaz, evasivo, técnico…
  "emotional_expression": "suppressed", // 7.1 — pacientes que ocultan emociones
  "health_literacy": "high",
  "traits": ["stoic", "self-reliant"]
}
```

Tres razones para dejarlo abierto desde el principio aunque no se rellene aún:

1. **7.1 lo necesita.** "Pacientes que ocultan emociones" es una propiedad de
   persona, no de creencia. Sin este bloque habría que tocar el esquema después.
2. **Mantiene separadas las dos cosas que se miden.** `belief_profile` es lo que
   el médico debe inferir; `persona` es lo que hace la inferencia más o menos
   difícil. Mezclarlas impide analizar el efecto por separado.
3. **Se compone vía skills** (1.7): cada rasgo es un fragmento markdown que se
   añade al prompt del paciente, igual que los estilos del médico. Nada de
   ramas en `patient_profile.py`.

`patient_profile.py` traduce `belief_profile` → conducta hoy; con esto pasa a
traducir `belief_profile` + `persona` → conducta, sin cambiar su firma.

---

## 6. Dos perfiles de ejecución: local y HPC

Todo se ejecuta **en local**, sin endpoints remotos. Dos perfiles, misma
arquitectura y mismo código: cambian el modelo, la escala y el sitio.

| | **Local** | **HPC** |
|---|---|---|
| Para qué | Desarrollo, humo, tests | Líneas base, brazos, tandas |
| Dónde | Nodo de login o portátil | Nodo de cómputo, por cola |
| Servidor | Ollama, `127.0.0.1:11434` | Ollama o vLLM en el nodo |
| Médico | `llama3.2` (2 GB) | modelo grande — ver §6.2 |
| Paciente | `dolphin-llama3` (4.7 GB) | otra familia distinta al médico |
| Embeddings | `nomic-embed-text` | `jina-embeddings-v4` |
| Escala | 1–2 pacientes × 1 corrida | hasta 10 × 10 |

El perfil es **config, no una rama de código**, y se elige con `--profile`.
`config/base.yaml` tiene todo lo compartido; `config/local.yaml` y
`config/hpc.yaml` declaran de quién heredan y solo lo que cambia —los modelos y
`keep_alive`—:

```yaml
profile: hpc
extends: base
```

Se funde **bloque a bloque** al cargar (0.5): una fusión superficial borraría un
bloque entero en vez de completarlo, así que `models: {doctor: …}` en el perfil
se quedaría sin `embed`.

**La herencia es explícita y encadenable.** Un perfil sin `extends` carga solo
—es lo que permite que un test deje fuera una clave y la vea rechazada— y una
cadena puede tener los eslabones que haga falta:

```
base.yaml ◄── hpc.yaml ◄── hpc-show.yaml   # `features.coverage_hint: show`, nada más
```

Es la forma que pide "una variable por corrida": un brazo de la Fase 6 es un
fichero de tres líneas que nombra su padre y el interruptor que mueve, en vez de
una copia de `hpc.yaml` que vuelve a derivar. Un ciclo se detecta y se nombra;
heredar de algo que no existe también, porque si no un perfil huérfano parecería
un perfil al que simplemente le faltan ajustes.

`base.yaml` no es un perfil y no carga solo: no tiene clave `profile:`. Lo que se
copia a `run_meta` (0.4) es **el resultado ya fundido** —incluido `features`, que
es el brazo—, así que una corrida se sigue leyendo desde un único fichero aunque
su configuración venga de varios.

Ningún resultado de perfil local entra en las métricas publicadas: sirve para
saber que el código funciona, no cuánto acierta.

### 6.1 Almacén de modelos

Los modelos de Ollama del proyecto **no están en `~/.ollama`** sino en el almacén
compartido. Hay que exportar la variable antes de arrancar el servidor, o solo se
verá lo que haya en el home:

```bash
export OLLAMA_MODELS=/gpfs/projects/bsc02/llm_models/ollama
ollama serve
```

Contiene `llama3.2`, `dolphin-llama3`, `nomic-embed-text` y `glm-4.7-flash:q8_0`.
Los modelos grandes de HuggingFace están aparte, en
`/gpfs/projects/bsc02/llm_models/huggingface_models`, y se sirven con vLLM.

**La primera carga desde GPFS es lenta** — un blob grande puede tardar más de dos
minutos y Ollama aborta si el cliente se cansa antes. Consecuencias de diseño:

- El timeout del cliente debe ser generoso en la primera llamada (≥300 s).
- Cada corrida empieza con un **calentamiento**: una llamada trivial que fuerza la
  carga antes de cronometrar o medir nada.
- En HPC conviene copiar los pesos al disco local del nodo si lo hay; leer un
  modelo de 30 GB por GPFS en cada tarea no escala.

### 6.2 Elección de modelos

Cuatro criterios, por orden de dureza:

- **Familias distintas para médico y paciente.** No dos tamaños del mismo modelo:
  comparten convenciones de expresión aprendidas en el mismo entrenamiento, y el
  médico puede estar decodificando esas convenciones en vez de inferir. Es el
  problema de 5.5 a nivel de pesos, y no lo detecta ningún test de 5.4.
- **El médico necesita tool calling fiable.** Es el requisito duro: sin él no hay
  bucle agéntico. Se verifica con la sonda antes de elegir, no después.
- **El paciente no debe ser demasiado servicial.** Un modelo muy alineado hace de
  paciente sospechosamente cooperativo, que responde completo y ordenado a todo, e
  infla el rendimiento aparente del médico.
- **La pareja se congela antes de la línea base** de la etapa 7. Cambiarla después
  invalida la comparabilidad de todo lo anterior.

**Verificación con `tools/probe_tools.py`** — N llamadas a temperatura 0 con la
tool real `hand_off_to_patient`, contando cuántas devuelven una llamada bien
formada. Distingue fallo del modelo de caída de transporte.

| Modelo | Resultado | Nota |
|---|---|---|
| `glm-4.7-flash:q8_0` | **10/10** | Apto para médico. Determinista a T=0. Medido en nodo de login (ver §6.3): el veredicto vale, el tiempo de carga de 43 s hay que remedirlo |
| `llama3.2` | 3/3 y 5/5 | Sirve de humo. Determinista a T=0. Carga en 5 s en nodo de cómputo |
| `dolphin-llama3` | sin medir | Es paciente, no necesita tools |
| Grandes de HuggingFace | pendiente | Solo si hace falta más que GLM |

En HPC se lanza con `tools/probe_hpc.sh <modelo> [N] [horas]`, que replica el
entorno de `submit.sh`, levanta su propio Ollama en el nodo y calienta el modelo
antes de medir.

**Determinismo confirmado en local.** Las 10 respuestas de GLM a T=0 son idénticas
palabra por palabra, igual que las de llama3.2. Sirve para tests de regresión
reproducibles, pero **la dispersión de 2.4 exige temperatura > 0**: a T=0 no hay
nada que medir.

### 6.3 Trampa de SLURM: `salloc` sin `srun`

`salloc` reserva los recursos pero **ejecuta el comando en la máquina desde la que
se invoca**, no en el nodo asignado. Hay que envolver la orden en `srun`.

En la partición ACC el error es especialmente traicionero porque **los nodos de
login también tienen H100**: `nvidia-smi` responde, el modelo carga, todo parece
correcto, y mientras tanto el nodo reservado no hace nada.

Tres formas de detectarlo, comprobadas:

| Señal | Sin `srun` (mal) | Con `srun` (bien) |
|---|---|---|
| `hostname` | `alogin4` | `as01r1b18` = `$SLURM_NODELIST` |
| `nvidia-smi` | 4 H100 (las del login) | 1 H100 (la de `--gres=gpu:1`) |

`probe_hpc.sh` compara `hostname` con `$SLURM_NODELIST` y avisa. **Verificado**:
sin `srun` daba `alogin4` y 4 GPUs; con `srun --export=ALL` da el nodo asignado
y 1 GPU.

`submit.sh` del brazo Ruby usa el mismo patrón sin `srun`, así que sus corridas
"local" se ejecutaron casi con seguridad en el nodo de login. No invalida las
puntuaciones —el modelo y los pesos eran los mismos— pero sí cualquier conclusión
sobre tiempos o rendimiento de aquellas tandas.

---

## 7. Frontend y API

El frontend (`bipq_frontend/`, React+Vite, `src/App.tsx`) consume `api_server.py`.
Para reutilizarlo:

**Se conservan tal cual:**
`GET /patients`, `GET /patients/{id}`, `POST /patient/respond`, `POST /transcript`,
`GET /health`.

**Cambian:**
- `POST /doctor/ask` → devuelve también la intención (`speak` | `finish`) y la
  tool call, no solo el mensaje.
- `POST /evaluate` → misma ruta, pero recibe un `Report` en vez de un diccionario
  de puntuaciones sueltas, y devuelve además cobertura y NAs.
- `POST /score` y `POST /bmq/score` → **desaparecen.** No hay puntuación por
  intercambio. Los sustituye `POST /report`, que recibe el transcript completo y
  devuelve un `Report`.

**Nuevos:** `POST /report`, `GET /coverage/{run_id}`, `POST /run` (lanzar una
consulta completa).

Mantener los modelos Pydantic con el mismo estilo (`DoctorRequest`/`DoctorResponse`…)
para que el trabajo en `App.tsx` sea de adaptación, no reescritura.

---

## 8. Orden de construcción

Nueve etapas. Cada una termina con algo ejecutable y verificable — no pasar a la
siguiente sin cerrar la anterior.

**Nada se lanza en grande al final.** Cada etapa se cierra con una *corrida de
humo* pequeña y barata que se ejecuta de verdad contra un LLM local. La escala
sube solo cuando la etapa anterior está en verde:

| Etapa | Corrida de humo | Coste |
|---|---|---|
| 1 | ninguna — solo arranque | — |
| 2 | 1 paciente × 1 corrida | ~15 turnos |
| 3 | 2 pacientes × 1 corrida | ~2 informes |
| 4 | 10 pacientes × 2 corridas | 20 consultas |
| 5 | reusa la tanda de la 4 | 0 |
| 6 | 10 × 5 | 50 consultas |
| 7 | 10 × 10 (línea base) + brazos | 100 + brazos |
| 8 | 10 × 5 por intervención | 50 c/u |
| 9 | según corpus ampliado | — |

Los tests se escriben **en la etapa que introduce el comportamiento**, no al
final. Cada etapa hereda y vuelve a ejecutar los tests de las anteriores.

### Etapa 1 — Esqueleto (0.1, 0.2, 0.3, 0.4)
Copiar el paquete, `git init`, `run_meta` con provenance, verificar que los
`patients/*.json` coinciden entre brazos.
**Tests:** carga de config; `run_meta` se serializa completo.
**Hecho cuando:** `git log` tiene el commit inicial y `python main.py --help` corre.

### Etapa 2 — Bucle agéntico (1.1–1.9)
Empieza verificando tool calling en el modelo médico elegido (§6.2): sin eso no
hay bucle y el resto de la etapa no tiene sentido.
Luego `tools.py` con el equivalente a `delegate`, `state.py`, `nodes.py`,
`graph.py`, `routing.py`, `prompts.py` con la composición de skills (1.7) y
recursos (1.8). Perfil de paciente con el bloque `persona` ya en el esquema
aunque vacío (1.9). Sin informe todavía: la consulta termina y vuelca el
transcript.
**Tests:** aislamiento de §3.1 (obligatorio a partir de aquí); el médico cierra;
el tope de turnos corta; el cargador de prompts resuelve ficheros, compone skills
y calcula hashes; **dos skills opuestas producen transcripts observablemente
distintos** (§5.1) — que se concatene no prueba que el modelo obedezca.
**Humo:** 1 paciente × 1 corrida, perfil local.
**Hecho cuando:** una consulta de 10–15 turnos con turnos libres, cerrada por el
médico, y el test de aislamiento en verde.

### Etapa 3 — Informe y rúbrica (1.10, 1.11, 1.12, 1.13, 2.1, 2.2, 2.3, 4.4)
`report.py` completo: esquema, parseo, validación, reintento. Rúbrica de anclas
del médico (2.2). Sondeo por ambigüedad con `coverage_hint` (§4.1). Confianza
declarada (2.3).
**Tests:** parser con informes bien y mal formados; política NA (nunca un valor
por defecto); orden `evidence → reasoning → score` presente; el reintento se
dispara y se rinde tras 2.
**Humo:** 2 pacientes × 1 corrida.
**Hecho cuando:** ambos producen un `Report` válido, con NA donde corresponda.

### Etapa 4 — Robustez (3.1, 3.3, 3.4)
Reintentos de transporte en `llm.py`, `run_batch.py`, log de `events`,
`reproducibility.py`.
**Tests:** reintento ante respuesta vacía y ante error de servidor; `events`
registra todo fallo; el corpus se marca utilizable/no utilizable (3.4).
**Humo:** 10 pacientes × 2 corridas.
**Hecho cuando:** la tanda sale sin turnos vacíos ni informes perdidos.

### Etapa 5 — Evaluación (4.1, 4.2, 4.3, 4.5, 4.6)
Portar `evaluation.py` y `causes/`. Ground truth desde `patients/*.json` y de
ningún otro sitio.
**Tests:** métricas contra valores calculados a mano; el cargador de ground truth
rechaza cualquier fuente que no sea el perfil; causas con texto que contenga
`<br/>` y asteriscos (regresión del bug del parser viejo).
**Humo:** reusa la tanda de la etapa 4.
**Hecho cuando:** tabla de MAE, sesgo por dimensión y cobertura de causas.

### Etapa 6 — Cobertura y confianza (3.2, 2.4, 2.5, 2.6)
`coverage.py` con el mapa dimensión × paciente y la verificación de citas.
Dispersión entre corridas y discriminación entre pacientes, siempre juntas.
**Tests:** una cita inventada se detecta; una dimensión sin sondear sale como
hueco; dispersión y discriminación sobre datos sintéticos conocidos.
**Humo:** 10 × 5.
**Hecho cuando:** sale el mapa de calor y la confianza declarada está cruzada
contra la dispersión observada.

### Etapa 7 — Brazos de comparación (5.1, 5.2, 5.4, 5.5)
Suelo ciego, techo por elicitación, tests de artefacto, brazo sin claves
conductuales. Se representan, no emiten veredicto.
**Tests:** el transcript cruzado degrada el MAE (si no, hay fuga); el suelo ciego
no ve la conversación.
**Humo:** 10 × 10 como línea base, más los brazos.
**Hecho cuando:** una gráfica sitúa el brazo de inferencia entre suelo y techo.

**5.3 (referencia humana)** no es código: es coordinación con clínicos. Se lanza
en paralelo a esta etapa, sobre los transcripts ya limpios de la 4. Lo único que
hay que construir es el formulario de puntuación y el cálculo de acuerdo
interevaluador.

### Etapa 8 — Intervenciones (6.1–6.5)
Una variable por corrida, N=5 para cribar y N=10 para confirmar. 6.5 es cargar
estilos como skills, no comparar estilos.
**Hecho cuando:** cada intervención tiene su delta medido contra la línea base.

### Etapa 9 — Corpus y cierre (7.1, 7.2)
Ampliar el corpus con perfiles intermedios y pacientes que ocultan emociones
(usa el bloque `persona` de §5.2). Reescribir la sección 6 del informe con los
números reales.
**Hecho cuando:** el corpus ampliado pasa 3.4 y el informe está actualizado.

---

## 9. Ciclo de trabajo por etapa

Seis roles. Tú implementas; yo asisto donde lo pidas.

| # | Rol | Qué produce | Quién |
|---|---|---|---|
| 1 | **Planner** | Descompone la etapa en tareas pequeñas, define criterio de "hecho" | Yo propongo, tú apruebas |
| 2 | **Implementador** | Escribe el código | **Tú**, con mi ayuda |
| 3 | **Reviewer** | Revisa Clean Code, SOLID, duplicación, complejidad | Yo |
| 4 | **Tester** | Escribe y ejecuta tests, verifica comportamiento | Yo propongo, tú ejecutas |
| 5 | **Refactorer** | Mejora estructura sin cambiar comportamiento | Yo propongo, tú decides |
| 6 | **Security/Quality** | Config, secretos, manejo de errores, calidad global | Yo |

**Regla de paso:** una etapa no se cierra hasta pasar por los seis. El punto 5
solo actúa con los tests del 4 en verde, para poder distinguir un refactor de un
cambio de comportamiento.

### Invariantes que revisa el Reviewer en cada etapa

1. `profile` no entra en el contexto del médico (3.1).
2. Ningún valor por defecto sustituye a un fallo — siempre NA (4.4).
3. El ground truth se lee solo de `patients/*.json` (4.1).
4. `evidence` antes que `score` en el esquema y en el prompt (2.1).
5. `evaluation.py`, `coverage.py`, `reproducibility.py`, `artifacts.py` y
   `causes/` no importan de `nodes`/`graph`.
6. Ningún prompt embebido en `.py` — todo en `prompts/` o `skills/`.
7. Cada corrida escribe su `run_meta` (0.4).
8. Ninguna llamada a un endpoint remoto. Todo local (§6).

### Tipos de test

Los tests concretos van etapa por etapa en §8. Las cuatro categorías:

- **Unitarios** — lógica pura, sin LLM: parser, política NA, métricas.
- **Integración** — consulta completa con el perfil local.
- **Invariante** — los ocho de arriba, en cada etapa desde la 2.
- **Regresión** — una tanda pequeña fija, para detectar deriva entre etapas.

---

## 10. Ampliaciones de benchmark (opcionales)

Lo previsto en TASKS.md cubre lo básico. Estas añadidas son baratas y encajan sin
tocar la arquitectura. **Ninguna emite veredicto**; se representan, como 5.1/5.2.

### Métricas de acuerdo, no solo de error

- **ICC (correlación intraclase)** — el estándar en estudios clínicos de acuerdo.
  Su valor es que se compara **directamente** con el acuerdo entre los clínicos
  de 5.3: pone al modelo y a los humanos en la misma escala.
- **Spearman** junto a Pearson. Pearson supone linealidad; Spearman solo mide si
  el orden se conserva. Si Spearman es alto y Pearson bajo, el modelo ordena bien
  a los pacientes pero tiene la escala desplazada — que es un problema muy
  distinto, y se arregla con calibración (6.3) en vez de con más sondeo.
- **Bland-Altman** — gráfica estándar de comparación de métodos en medicina:
  muestra si el sesgo cambia con la magnitud. Diría, por ejemplo, si el modelo
  solo se equivoca en los valores extremos o también en los medios.
- **Acuerdo dicotomizado** — partir cada dimensión en alto/bajo y reportar
  concordancia. Es la lectura clínicamente accionable: para intervenir sobre un
  paciente importa si tiene baja adherencia percibida, no si es 3.2 o 3.8.

### Detección automática de problemas

- **Verificación de citas** (en `coverage.py`) — comprobar que cada `Evidence.quote`
  aparece literalmente en el transcript. Detecta fabricación de evidencia de forma
  automática y barata. Antes se comprobó a mano y el hallazgo fue que el modelo no
  inventaba citas sino que las clasificaba mal; como puerta automática, vigila que
  eso siga siendo cierto.
- **Contradicción evidencia↔puntuación** — un segundo modelo lee solo la cita y el
  razonamiento, sin ver el número, y predice la puntuación. Divergencia grande =
  el número no se sigue de la evidencia. Es la versión automática de 5.4.
- **Deriva entre corridas** — misma configuración, corridas separadas en el tiempo:
  detecta cambios del endpoint que no son culpa del código.

### Métricas de la conversación

Ninguna necesita ground truth y todas salen del transcript:

- Turnos hasta el cierre, y su dispersión entre pacientes.
- Diversidad de preguntas: ¿el médico varía o repite un guion?
- Reparto del habla médico/paciente.
- Cobertura temporal: en qué momento de la consulta se toca cada dimensión — si
  `causes` siempre sale en el último turno, está de relleno.

---

## 11. Versión en inglés

**Sí, y con `ARCHITECTURE.md` en inglés como versión canónica.** El hilo del
proyecto (Christina, el PI) va en inglés, así que este documento es el que van a
leer otros. `TASKS.md` puede quedarse en español: es documento de trabajo interno.

Cuándo: **no ahora**. Traducir mientras el diseño se mueve garantiza dos versiones
divergentes. El momento es al cerrar la etapa 3, cuando el bucle agéntico y el
contrato del informe ya no van a cambiar. A partir de ahí, inglés es la fuente y
el español —si se mantiene— se regenera.

---

## 12. Riesgos conocidos

| Riesgo | Mitigación |
|---|---|
| El médico no cierra nunca la consulta | Tope de turnos como red de seguridad (1.5) |
| El informe se degrada en consultas largas | Validación + reintento (1.13); es lo que perdió CLL-004 |
| La rúbrica del médico acaba siendo el espejo de la del paciente | Escribirla desde criterios clínicos; medirlo con 5.5 |
| Temperatura implícita: un servidor que aplica su propio valor por defecto cambia los resultados sin avisar | Enviarla **siempre** explícita y registrarla en `run_meta` |
| Carga lenta desde GPFS que aborta la primera llamada | Calentamiento antes de medir y timeout ≥300 s (§6.1) |
| Reescribir el frontend en vez de adaptarlo | Congelar los endpoints de §7 antes de tocar `App.tsx` |
| **Contaminación entre pacientes.** En `simulation.rb` el agente médico se crea **una vez** fuera del bucle de pacientes y se reinicia con `doctor.start`. Si el reinicio no es completo, el paciente N ve residuos del N−1 | Crear el agente médico **dentro** del bucle, uno por consulta. Test: dos consultas seguidas no comparten ni un mensaje |
| Dejar la evaluación para el final y descubrir que el corpus no sirve | Corridas de humo por etapa (§8) y la puerta de 3.4 |

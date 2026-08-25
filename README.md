# Mapa del proyecto

Qué hay, dónde está y qué documento leer para qué. Describe lo que **existe hoy**
— ARCHITECTURE.md describe lo que se decidió construir, que no es lo mismo.

---

## Los cinco documentos

| Documento | Se lee para |
|---|---|
| **README.md** | Orientarse. Este fichero |
| **[ARCHITECTURE.md](ARCHITECTURE.md)** | Por qué está hecho así. Decisiones de diseño y orden de construcción |
| **[TASKS.md](TASKS.md)** | Qué hay que hacer. Siete fases de objetivos |
| **[STATUS.md](STATUS.md)** | Qué está hecho y cuánto nos hemos desviado |
| **[INHERITED_ISSUES.md](INHERITED_ISSUES.md)** | Qué falló antes y en qué estado está |
| **[RUN.md](RUN.md)** | Cómo lanzar una consulta o una tanda |

---

## El código: qué fichero responde a qué

**El bucle de la consulta** — médico ⇄ paciente hasta que el médico cierra.

| Fichero | Pregunta que responde |
|---|---|
| `graph.py` | ¿Cómo se conectan los nodos? Único sitio que toca `StateGraph` |
| `nodes.py` | ¿Qué hace cada turno? `doctor_node`, `patient_node`, `report_node` |
| `routing.py` | ¿Sigue la conversación, o se pasa al informe? |
| `state.py` | ¿Qué se arrastra entre turnos? |
| `tools.py` | ¿Cómo habla el médico con el paciente? Es una llamada a herramienta |
| `llm.py` | ¿Cómo se llama al modelo, y qué se reintenta? |

**Lo que entra**

| Fichero | Pregunta |
|---|---|
| `config.py` | ¿Qué dice el perfil de ejecución? Y los nombres de las dimensiones |
| `prompts.py` | ¿Cómo se componen prompt + skills + recursos, y su hash? |
| `patient_profile.py` | ¿Cómo se convierte un `belief_profile` en conducta? |

**Lo que sale**

| Fichero | Pregunta |
|---|---|
| `report.py` | ¿Qué entrega el médico, y cómo se lee? Esquema, parseo, NA, huecos |
| `metadata.py` | ¿Con qué se hizo esta corrida? Modelos, temperatura, hashes, commit, nodo |
| `reproducibility.py` | ¿Cuánto se mueve entre corridas, y separa a los pacientes? |

**Puntos de entrada**

| Fichero | Para qué |
|---|---|
| `main.py` | Una consulta |
| `run_batch.py` | N repeticiones × M pacientes |
| `serve_ollama.sh` | Levantar el servidor con el almacén de modelos correcto |
| `python -m ahead_agent.reproducibility runs/<tanda>` | Analizar una tanda |

**Regla de dependencias.** `nodes` → `llm`. El post-proceso —hoy solo
`reproducibility.py`— no importa de `nodes` ni de `graph`, para que pueda correr
sobre corridas de cualquier brazo.

---

## Los datos

```
patients/*.json      10 perfiles. disease_profile (hechos) + belief_profile (ground truth)
prompts/DOCTOR.md    el rol del médico
prompts/PATIENT.md   el rol del paciente
prompts/REPORT.md    cómo se pide el informe
prompts/doctor_rubric/{bipq,bmq}.json   anclas 2/4/6/8, lado médico
prompts/reference/   los prompts del brazo Ruby, congelados como referencia
config/{local,hpc}.yaml    perfiles de ejecución
runs/<corrida>/      metadata.json + transcript.json + report.json
runs/<tanda>/batch.json    el índice de una tanda
```

---

## Lo que todavía no existe

Para que no lo busques: `evaluation.py` (4.2), `coverage.py` (3.2), `causes/`
(4.3), `artifacts.py` (5.4) y `api_server.py` (§7). Los directorios
`ahead_agent/api/`, `ahead_agent/causes/`, `skills/styles/` y `resources/` están
vacíos a propósito — el mecanismo existe, el contenido no.

`ARCHITECTURE.md` §2 los lista porque describe el destino, no el presente.

---

## Los códigos

Cuatro sistemas de numeración conviven, y cada uno significa una cosa distinta:

| Forma | Qué es | Dónde |
|---|---|---|
| `1.13`, `3.2` | Tarea. El primer número es la **fase** | TASKS.md |
| `Etapa 4` | Paso de construcción. Una etapa implementa tareas de varias fases | ARCHITECTURE §8 |
| `§4.1`, `§6.2` | Sección de diseño | ARCHITECTURE |
| `P4`, `R6`, `C1`, `N5`, `D9` | Hallazgo | INHERITED_ISSUES, STATUS |

Los hallazgos, por letra:

- **P** — falló en el brazo **Python** de elicitación
- **R** — falló en el brazo **Ruby** de inferencia
- **C** — problema del **corpus**, compartido por los dos brazos
- **N** — hallazgo **nuevo**, de este brazo
- **D** — **desviación** respecto a ARCHITECTURE (solo en STATUS)

Ejemplo de cómo se cruzan: la tarea **3.1** (reintentos de transporte) se
construyó en la **Etapa 4**, arregla **R6** (19% de turnos vacíos en Ruby) y se
describe en **§3.2**.

---

## Fuera de este directorio

- `../modified_versions/ruby_version/` — el brazo Ruby. Los `patients/` de los dos
  brazos deben ser byte-idénticos (0.3), y hay un test que lo comprueba
- `../tools/probe_tools.py` y `probe_hpc.sh` — sondas de tool calling (§6.2).
  **Están fuera del repo git**
- `/gpfs/projects/bsc02/llm_models/ollama` — los modelos. No están en `~/.ollama`

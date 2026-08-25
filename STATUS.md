# Estado — qué está cubierto y cuánto nos hemos desviado

Corte durante la Etapa 4, con la tanda `e4-1` (10 pacientes × 2) ya corrida. Se
contrasta contra [TASKS.md](TASKS.md) y [ARCHITECTURE.md](ARCHITECTURE.md). Los
hallazgos que sostienen las casillas están en
[INHERITED_ISSUES.md](INHERITED_ISSUES.md).

Leyenda: **✅** hecho y verificado · **◐** medido, pero sin herramienta que lo
reproduzca · **⚠️** hecho a medias, con la parte que falta al lado · **❌** no
empezado · **⛔** decidido no hacerlo ahora.

---

## Fase 0 — Base

| | | |
|---|---|---|
| 0.1 | Paquete nuevo | ✅ `agents_simulations/` |
| 0.2 | Git | ✅ |
| 0.3 | Mismos 10 perfiles en los dos brazos | ✅ `test_corpus.py` compara bytes contra `modified_versions/ruby_version/patients` |
| 0.4 | Provenance por corrida | ✅ `metadata.py`, verificado en 24 corridas |

## Fase 1 — Arquitectura de agentes

| | | |
|---|---|---|
| 1.1 | Grafo con dos nodos de agente | ✅ y el punto de extensión ya se usó: `report` |
| 1.2 | Modelos distintos + test de aislamiento | ✅ `test_the_patient_profile_never_reaches_the_doctor` |
| 1.3 | Turnos no preestablecidos | ✅ |
| 1.4 | Secuencial y coherente | ✅ |
| 1.5 | Termina el médico | ✅ 20 de 20 consultas de `e4-1` cerradas por el médico, ninguna por el tope |
| 1.6 | Prompts en markdown externos | ✅ |
| 1.7 | Skills | ⚠️ el mecanismo compone y hashea; `skills/styles/` sigue **vacío**, así que el test de §5.1 —dos skills opuestas dan transcripts distintos— nunca se ha ejecutado |
| 1.8 | Definiciones externas como recurso | ⚠️ interfaz lista, `resources/` vacío, sin decidir inyección vs recuperación |
| 1.9 | Perfiles de paciente | ✅ estructura intacta. **`persona` retirado** — ver D2 |
| 1.10 | Preguntas libres que cubran **todas** las dimensiones | ❌ **falla**. En `e4-1`, `general_overuse` queda NA en 5 de 10 pacientes y con número en los otros 5, sin que se sepa si se preguntó. Lo hace visible 3.2 |
| 1.11 | Puntuación al final | ✅ |
| 1.12 | Sondeo dirigido por ambigüedad | ⛔ sin mecanismo en la línea base, a propósito — §4.1 y D3 |
| 1.13 | Informe siempre, validado, con reintento | ✅ y ahora ejercitado de punta a punta, incluida la rendición al agotar los 3 intentos. En vivo no se ha disparado nunca (N8): 24 corridas con `attempts: 1` |

## Fase 2 — Trazabilidad de la puntuación

| | | |
|---|---|---|
| 2.1 | Evidencia antes que número | ✅ en el esquema y en el prompt. El experimento que habilita es 5.4 y no se ha hecho |
| 2.2 | Anclas intermedias 2/4/6/8 | ✅ `prompts/doctor_rubric/*.json`, desde criterio clínico y sin invertir las bandas del paciente |
| 2.3 | Confianza declarada | ✅ se emite y se parsea. **No calibra** (N7) |
| 2.4 | Confianza empírica (dispersión) | ◐ **0.56** en la media del paciente, **0.99** por dimensión suelta. `reproducibility.py` existe como borrador —211 líneas, sin tests, sin caller y sin pasar por el ciclo de §9—, así que **no cuenta como hecho**: se planifica antes de darlo por bueno |
| 2.5 | Discriminación entre pacientes | ◐ Pearson **0.73**, Spearman 0.66; sd de las medias informadas **0.67** contra **1.21** de la verdad. Ordena bien y **comprime a la mitad**. No es un scorer degenerado |
| 2.6 | Validar 2.3 contra 2.4 | ❌ |

## Fase 3 — Integridad del corpus

| | | |
|---|---|---|
| 3.1 | Reintentos de transporte | ✅ y **disparado en vivo por primera vez**: 3 eventos en 20 consultas, todos recuperados |
| 3.2 | Módulo de cobertura | ⚠️ la señal 1 (verificación de citas) corrió como script: 949 citas, **96% literales**, 4 salidas del propio médico, 24 con turno mal atribuido. Sin módulo |
| 3.3 | Reproducibilidad | ◐ ver 2.4 y 2.5 |
| 3.4 | Puerta de corpus utilizable | ❌ |
| 3.5 | Fidelidad del paciente | ❌ tarea nueva, sale de N1. Pendiente de escribir en TASKS.md |

## Fase 4 — Evaluación

| | | |
|---|---|---|
| 4.1 | Ground truth solo de `patients/*.json` | ✅ |
| 4.2 | Portar `evaluation.py` | ✅ portado. La aritmética por dimensión va intacta; NUEVO el NA como valor, la agregación entre pacientes y las **dos correlaciones con nombre distinto** — `within_patient_r` (la heredada) y `between_patient_r` (la que pide 2.5) |
| 4.3 | Portar `causes/` | ✅ portado: taxonomía, clasificador, coseno, matriz, emparejamiento greedy, `coverage_score` y `mean_similarity`. NUEVO: el método usado (`embeddings` o `categories`) queda **registrado en el resultado** — el original cambiaba de métrica en silencio al fallar los embeddings. Sin correr todavía sobre `e4-1` |
| 4.4 | NA en vez de fallback | ✅ verificado en 24 corridas, nunca recortado |
| 4.5 | Sesgo por dimensión | ✅ ya es herramienta, no script: `evaluate_batch` lo agrega por dimensión entre pacientes. Los números de `e4-1` fueron ◐ `identity` **+2.50**, `consequences` +1.45, `concern` +1.05, `personal_control` +0.95, `timeline` −0.40, `treatment_control` −0.10. Reproduce la forma de P5 con `identity` mucho más inflado, y `personal_control` **cambia de signo** |
| 4.6 | Objetivos provisionales | ❌ |

## Fases 5, 6 y 7

❌ completas, que es lo previsto. Los dos brazos de `coverage_hint` —`off` y `show`— existen
y son material de la Etapa 8.

---

## La tanda `e4-1`

10 pacientes × 2, `glm-4.7-flash:q8_0` / `dolphin-llama3`, `coverage_hint: off`.

- 20 de 20 correctas, todas cerradas por el médico, 7–15 turnos.
- 3 eventos en total, todos reintentos de transporte recuperados.
- 0 informes sin parsear, 0 reintentos de informe.

Es el primer corpus del proyecto sin huecos. El brazo Ruby iba por 19% de turnos
vacíos y 26% de informes perdidos.

Lo que **no** hace utilizable a este corpus todavía es 3.2 y 3.5: no sabemos si
el médico preguntó por lo que puntuó, ni si el paciente jugó su perfil.

---

## Desviaciones respecto a ARCHITECTURE.md

El paradigma sigue entero: bucle agéntico, paciente como herramienta,
aislamiento verificado, NA sin excepciones, evidencia antes que número.

### De fondo

**D1 — `run_batch.py`.** ✅ **resuelto.** Existía como `PORTAR` en §2 y ya está,
con dos guardas que §2 no pedía: aborta con el árbol sucio y avisa si las dos
temperaturas son 0.

**D2 — `persona` retirado del perfil de paciente.** §5.2 lo pide en el esquema
desde el principio para que 7.1 no obligue a tocarlo después. Se quitó por
decisión explícita; la Fase 7.1 tendrá que reintroducirlo.

**D3 — `coverage_hint` por defecto en `off`.** Ya no es desviación: §4.1 está
reescrita y describe los brazos con `off` como línea base. Queda como N9.
Hubo un tercer modo, `declare` —declarar sin recibir nada—, retirado porque las
propias declaraciones vuelven en el historial dentro de los `tool_calls`, así
que el médico podía releerse y el brazo no aislaba lo que decía aislar.

**D9 — El médico escribe su propio informe.** `report_node` continúa la
conversación que acaba de tener, en vez del `api/reporter.py` que §2 lista como
`NUEVO`. Un modelo nuevo leyendo el transcript en frío puntuaría igual de bien y
mediría otra cosa — es el brazo de artefacto de 5.4. Consecuencia: 2.1 se
verifica dentro del mismo contexto que formó la impresión, así que la ablación
de 5.4 pasa a ser el único separador. §2 y §4 siguen sin recogerlo.

### De forma

**D4** — `prompts/rubric/*.md` → `prompts/doctor_rubric/*.json`.
**D5** — `prompts/REPORT.md` es nuevo.
**D6** — Bloque `features` en los perfiles, obligatorio y validado.
**D7** — `report_raw.txt` solo cuando el informe no parsea.
**D8** — Falta `api_server.py`. Ver la sección del frontend: §7 supone que `App.tsx` se adapta, y en realidad hay que invertirlo.
**D10** — `ahead_agent/api/` está vacío. Consecuencia de D9. `ahead_agent/causes/` ya no lo está.

---

## El frontend, si se añadiera `api_server.py`

Medido sobre `python_version/ahead_agent-bmq-integration/bipq_frontend`, unas
1.150 líneas entre `src/` y `runner/`.

**No se reutiliza entero, y el motivo es de fondo: el frontend *es* el brazo de
elicitación.** `App.tsx` no muestra la consulta, la conduce. Su
`runConversation(qi, followUps, …)` recorre `BIPQ_QUESTIONS` por índice, decide
si repreguntar con `pm.split(" ").length < SHORT_RESPONSE_THRESHOLD`, y llama al
scorer pregunta a pregunta. Es decir, P2 y P3 —el recorrido por lista y la regla
de repreguntar por longitud— siguen vivos en React después de haberlos sacado de
Python.

| Parte | Líneas | Reutilizable |
|---|---|---|
| `components/` presentacionales — burbujas, barras, pantallas, estilos | ~300 | ✅ tal cual |
| `ReportScreen` y `CausesPanel` | ~300 | ⚠️ el marco sirve; el contenido cambia, porque ahora cada dimensión trae evidencia, razonamiento y confianza, no un número suelto |
| `runner/config.ts` — el cuestionario y los umbrales | 119 | ❌ el cuestionario no vive en el cliente |
| `runner/api.ts` — `callDoctor(qi)`, `callScorer(qi, …)`, `callBmqScorer` | 188 | ❌ esos endpoints desaparecen (§7) |
| `App.tsx` — el bucle | 195 | ❌ se invierte: de conductor a espectador |

Así que §7 se queda corto cuando dice que el trabajo en `App.tsx` será *"de
adaptación, no reescritura"*. Lo presentacional sí; el orquestador no se adapta,
se sustituye, porque el orquestador ahora es el grafo.

**Un hueco de §7, ya decidido.** El `POST /run` que propone lanza una consulta
entera: minutos de reloj, que no caben en una petición que responde al final.
Se hará con **streaming por turnos** (8.2): el servidor emite cada turno según
se produce y el informe llega como último evento. Sin barra de progreso — la
puntuación es una sola y al final, así que no hay nada que contar mientras se
conversa (8.7).

---

## Lo siguiente, por orden

1. **`reproducibility.py`** — convierte en herramienta los números ◐ de 2.4 y
   2.5. Sin él, la Etapa 8 no tiene vara. Hay un borrador escrito; lo que falta
   es planificarlo —qué entra, qué escribe, quién lo llama— antes de tocarlo.
2. **Puerta 3.4** — declarar utilizable o no un corpus, leyendo 3.2 y el índice
   de la tanda.
3. **3.5, auditoría del paciente sin modelo** — contradicciones contra
   `disease_profile`. Corre sobre `e4-1`, no necesita cola.
4. **`coverage.py`** — señal 1 primero, que ya está prototipada.

Fuera de la ruta crítica: los ficheros de `skills/styles/` y su test (§5.1), la
traducción inglesa de ARCHITECTURE que §11 dejaba al cerrar la Etapa 3, y los
tests propios de `run_batch.py`.

Intervenciones sobre prompts —C1 lado médico, el sesgo de `identity`— son Etapa
8. Con ruido de 0.99 por dimensión, cualquier cambio menor que eso hoy es
invisible.

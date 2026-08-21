# Estado — qué está cubierto y cuánto nos hemos desviado

Corte tras cerrar la Etapa 3. Se contrasta contra [TASKS.md](TASKS.md) y
[ARCHITECTURE.md](ARCHITECTURE.md). Los hallazgos que sostienen las casillas
están en [INHERITED_ISSUES.md](INHERITED_ISSUES.md).

Leyenda: **✅** hecho y verificado · **⚠️** hecho a medias, con la parte que
falta escrita al lado · **❌** no empezado · **⛔** decidido no hacerlo ahora.

---

## Fase 0 — Base

| | | |
|---|---|---|
| 0.1 | Paquete nuevo | ✅ `agents_simulations/` |
| 0.2 | Git | ✅ 9 commits |
| 0.3 | Mismos 10 perfiles en los dos brazos | ✅ `test_corpus.py` compara contra `modified_versions/ruby_version/patients` |
| 0.4 | Provenance por corrida | ✅ `metadata.py`: modelos, sampling, hashes de prompts, commit + `dirty`, hostname y job de SLURM |

## Fase 1 — Arquitectura de agentes

| | | |
|---|---|---|
| 1.1 | Grafo con dos nodos de agente | ✅ y el punto de extensión ya se usó: `report` |
| 1.2 | Modelos distintos + test de aislamiento | ✅ `test_the_patient_profile_never_reaches_the_doctor` |
| 1.3 | Turnos no preestablecidos | ✅ sin `q_index` ni contador de rondas |
| 1.4 | Secuencial y coherente | ✅ |
| 1.5 | Termina el médico | ✅ tope de 30 turnos solo como red, y anotado en `events` si se alcanza |
| 1.6 | Prompts en markdown externos | ✅ |
| 1.7 | Skills | ⚠️ el mecanismo compone y hashea; `skills/styles/` está **vacío**, así que el test de §5.1 —dos skills opuestas dan transcripts distintos— nunca se ha ejecutado. Sin él no sabemos si GLM obedece un fragmento concatenado |
| 1.8 | Definiciones externas como recurso | ⚠️ interfaz lista, `resources/` vacío, y sigue sin decidirse inyección vs recuperación |
| 1.9 | Perfiles de paciente | ✅ estructura intacta. **`persona` retirado** — ver desviación D2 |
| 1.10 | Preguntas libres que cubran **todas** las dimensiones | ⚠️ libres sí; completas no. En **4 de 4** corridas el médico no mencionó `causes`, `general_harm` ni `general_overuse` — C3, y en Ruby pasaba lo mismo *con* tabla de sondeos |
| 1.11 | Puntuación al final | ✅ |
| 1.12 | Sondeo dirigido por ambigüedad | ⛔ abierto a propósito — ver desviación D3 y N9 |
| 1.13 | Informe siempre, validado, con reintento | ✅ nodo propio, `REPORT.md`, validación y reintento. El reintento **no se ha disparado nunca en vivo** (N8) |

## Fase 2 — Trazabilidad de la puntuación

| | | |
|---|---|---|
| 2.1 | Evidencia antes que número | ✅ en el esquema (`DimensionScore`) y en el prompt. El experimento que habilita —si la justificación es a posteriori— es 5.4 y no se ha hecho |
| 2.2 | Anclas intermedias 2/4/6/8 | ✅ `prompts/doctor_rubric/{bipq,bmq}.json`, desde criterio clínico y **sin invertir** las bandas del paciente |
| 2.3 | Confianza declarada | ✅ se emite y se parsea. **No calibra** (N7): 0.9 sobre un error de 5 |
| 2.4 | Confianza empírica (dispersión) | ❌ necesita `run_batch.py` |
| 2.5 | Discriminación entre pacientes | ❌ ídem. Es la que hace falta ya: N5 y N6 son justo el fallo que 2.5 detecta |
| 2.6 | Validar 2.3 contra 2.4 | ❌ |

## Fase 3 — Integridad del corpus

| | | |
|---|---|---|
| 3.1 | Reintentos de transporte | ✅ `llm.py`, incluida la respuesta vacía, y anotado en `events`. 0 eventos en las 4 corridas |
| 3.2 | Módulo de cobertura | ❌ Etapa 6 |
| 3.3 | Reproducibilidad | ❌ Etapa 4 |
| 3.4 | Puerta de corpus utilizable | ❌ |

## Fase 4 — Evaluación

| | | |
|---|---|---|
| 4.1 | Ground truth solo de `patients/*.json` | ✅ `write_transcript` no copia `belief_profile` |
| 4.2 | Portar `evaluation.py` | ❌ Etapa 5 |
| 4.3 | Portar `causes/` | ❌ Etapa 5 |
| 4.4 | NA en vez de fallback | ✅ ausencia, tipo erróneo y fuera de escala dan NA, y **nunca se recorta**. Verificado en las 4 corridas |
| 4.5 | Sesgo por dimensión | ❌ |
| 4.6 | Objetivos provisionales | ❌ |

## Fases 5, 6 y 7

❌ completas. Nada empezado, que es lo previsto.

Una excepción parcial: los tres brazos de `coverage_hint` (`off`/`declare`/`show`)
ya están implementados y son material de 6.4.

---

## Desviaciones respecto a ARCHITECTURE.md

La respuesta corta es **no, no nos hemos alejado**. El paradigma está entero:
bucle agéntico, paciente como herramienta, aislamiento verificado, NA sin
excepciones, evidencia antes que número. Hay dos desviaciones de fondo y cinco
de forma.

### De fondo

**D1 — No existe `run_batch.py`.** ARCHITECTURE §2 lo marca `PORTAR` y sigue sin
portarse. No es una omisión menor: sin él todo se evalúa con n=1, y ya está
medido que el ruido entre corridas idénticas es de 1.25 de MAE (N2). Es el
bloqueo real de la Fase 2.

**D2 — `persona` retirado del perfil de paciente.** ARCHITECTURE §5.2 pide el
bloque en el esquema desde el principio precisamente para que 7.1 —pacientes que
ocultan emociones— no obligue a tocarlo después. Se quitó por decisión explícita.
Consecuencia: la Fase 7.1 tendrá que reintroducirlo.

**D3 — `coverage_hint` por defecto en `off`.** §4.1 lo describe como criterio de
suficiencia que el médico *consulta antes de cerrar*. Se implementó como tres
brazos y la línea base no lo usa, así que 1.12 se queda sin mecanismo. Decisión
razonada: forzar cobertura infla el resultado y devuelve el cuestionario por la
puerta de atrás. Queda como N9.

### De forma

**D4** — `prompts/rubric/*.md` → `prompts/doctor_rubric/*.json`. El nombre dice
de qué lado está la escala; el formato la hace comparable campo a campo con las
bandas de `patient_profile.py`, que es como se audita que no sean espejo (5.5).

**D5** — `prompts/REPORT.md` es nuevo. §2 no lo lista porque §4 no separaba el
prompt del informe del rol del médico.

**D6** — Bloque `features` en los perfiles, obligatorio y validado. No está en
§6. Existe para que un brazo no dependa de un valor por defecto (§12).

**D7** — `report_raw.txt` solo cuando el informe no parsea. Artefacto nuevo, y
solo el caso en que el texto es el único registro.

**D8** — Falta `api_server.py`. §7 congela los endpoints antes de tocar el
frontend; no toca hasta que el contrato del informe esté estable, que es ahora.

---

## Lo siguiente, por orden

1. **C1** — `null` en las dos *specific* de CLL-001, CLL-003 y CLL-005. Es
   determinista y hoy el corpus penaliza al médico por acertar (ver C1).
2. **`run_batch.py`** — sin él, N5, N6 y N7 no se pueden medir ni corregir.
3. **Sonda de fidelidad del paciente (N1)** — `dolphin-llama3` sigue marcado
   PROVISIONAL en §6.2 y sin verificar, y CLL-003 se comportó como un paciente
   afectado en tres corridas cuando su perfil dice lo contrario. Mientras esto
   falle, cualquier MAE mide al paciente, no al médico.

Fuera de la ruta crítica, pendientes de la Etapa 2: los ficheros de
`skills/styles/` y el test de dos consultas seguidas (R1).

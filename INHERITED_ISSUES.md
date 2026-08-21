# Errores heredados

Fallos concretos de los brazos anteriores, con dónde se vieron y en qué estado
están aquí. Sirve para dos cosas: no repetirlos, y poder decir al arreglar uno
qué cambió exactamente.

Estado: **RESUELTO** · **ABIERTO** · **PENDIENTE** (le toca a una etapa futura).

---

## Brazo Python (elicitación)

| # | Problema | Estado |
|---|---|---|
| P1 | **Valor por defecto en vez de NA.** El scorer metía un 5 (3.0 en BMQ) cuando el JSON no parseaba, y si eso fallaba cogía el primer número del texto. Valores inventados que después contaban como aciertos (4.4). | RESUELTO — `report.parse` deja NA ante ausencia, tipo erróneo o valor fuera de escala, y **nunca recorta**. Verificado en s3-1 y s3-2: tres `null` con evidencia vacía, ninguno rellenado |
| P2 | **Repreguntar por longitud.** El routing disparaba con `len(respuesta) < 10 palabras`, así que una respuesta larga y vaga pasaba directa a puntuación (1.12). | RESUELTO — no hay regla de longitud en el código; `DOCTOR.md` dice *"thin is about content, not length"* |
| P3 | **Recorrido por lista de preguntas.** `q_index`, `bmq_index` y `follow_up_count` marcaban el ritmo: el cuestionario era el guion. | RESUELTO — fuera del `State`; el médico decide por llamada a herramienta |
| P4 | **Scorer degenerado.** llama3.2 puso ochos el 67% de las veces. Máxima consistencia, cero discriminación (2.5). | ABIERTO — **reaparece con GLM**: s3-1 puntuó 6 en las ocho dimensiones del B-IPQ (MAE 3.25). s3-2, misma configuración, se repartió entre 2/4/6 (MAE 2.00). Se mide en la Etapa 6 con 2.4 + 2.5 juntas |
| P5 | **Sesgo asimétrico por dimensión**: `identity` +1.00, `consequences` +0.97, `treatment_control` −0.77, `personal_control` −0.63. El agregado (+0.13) lo escondía (4.5). | PENDIENTE — Etapa 5, `evaluation.py` por dimensión |
| P6 | **Parser de causas con regex improvisado**: borraba toda `b` y `r` del texto ("Stress" → "St ess") (4.3). | PENDIENTE — Etapa 5, al portar `causes/` |
| P7 | **Ground truth contra una corrida anterior** etiquetada `reference`. Eso mide deriva entre corridas, no exactitud (4.1). | RESUELTO — `write_transcript` no copia el `belief_profile`; el ground truth se lee de `patients/*.json` |
| P8 | **Un solo `CONFIG["model"]`** para médico y scorer: no se podía saber quién usó qué. | RESUELTO — `models.doctor` / `models.patient`, y temperatura por rol |
| P9 | **Puntuación por defecto en el prompt del paciente**: `bp.get(dim, 5)` inventaba un 5 para las dimensiones ausentes. | RESUELTO — `_cues` omite la dimensión que falta, nunca la rellena |
| P10 | **El médico no veía la conversación.** Cada pregunta se enviaba como `[system, instruction]`, sin historial: no podía inferir de lo anterior. | RESUELTO — `doctor_messages` acumula y se reenvía entero |

## Brazo Ruby (inferencia)

| # | Problema | Estado |
|---|---|---|
| R1 | **Un solo agente médico para todos los pacientes**, creado fuera del bucle y reiniciado con `doctor.start`. Si el reinicio no era completo, el paciente N veía restos del N−1. | RESUELTO — el `State` se crea por consulta; falta el test de dos consultas seguidas |
| R2 | **Informe sin validar.** El disparador era una frase suelta y el resultado se guardaba tal cual: así se perdió el informe de CLL-004 (1.13). | PENDIENTE — Etapa 3, validación + reintento |
| R3 | **`Score \| Rationale`**: la justificación se generaba después del número, así que era decorativa (2.1). | RESUELTO a medias — `DimensionScore` fija el orden `evidence → reasoning → score` y hay test sobre los campos. Que el orden se respete no prueba que el número siga a la evidencia: eso lo decide [N3] |
| R4 | **Rúbrica en espejo.** `DOCTOR.md` decía qué escuchar y `PATIENT.md` cómo expresarlo: la misma tabla en los dos lados. Parte del acierto era descifrar un código nuestro (5.5). | RESUELTO en los prompts v2 — el médico recibe qué captura cada dimensión, no qué señal corresponde a qué nivel |
| R5 | **Solo 0 y 10 anclados** en la escala: cualquier evidencia empuja al extremo (2.2). | RESUELTO a medias — `prompts/doctor_rubric/*.json` ancla 2/4/6/8 desde criterio clínico. En s3-2 el médico usó 2, 4 y 6 pero **nunca 8**, con verdad 8 y 9 en dos dimensiones: el extremo alto sigue sin alcanzarse |
| R6 | **Turnos vacíos (~19%) e informes fallidos (~26%)** sin reintento (3.1). | RESUELTO — `llm.py` reintenta transporte y respuesta vacía, y lo anota en `events` |
| R7 | **`salloc` sin `srun`** en `submit.sh`: el trabajo corría en el nodo de login, que en ACC también tiene H100, así que no se notaba (§6.3). | RESUELTO a medias — `metadata.compute` guarda `hostname` y `slurm_nodelist` para detectarlo; falta el lanzador |
| R8 | **Temperatura implícita.** Gepeto aplica 0.7 si no se envía, y es estocástico incluso a 0 (§12). | RESUELTO — temperatura y `num_ctx` se envían siempre y se registran |
| R9 | **`OLLAMA_CONTEXT_LENGTH` y `keep_alive` como variables del servidor**: invisibles desde el cliente y ausentes de la metadata. | RESUELTO — van en cada petición desde el perfil |

## Corpus (los dos brazos comparten los mismos 10 perfiles)

| # | Problema | Estado |
|---|---|---|
| C1 | **Pacientes sin medicación con BMQ *specific***. Las subescalas *specific* se definen sobre el fármaco recetado: sin receta no hay creencia que medir. | ABIERTO y **confirmado en marcha** — son 3 de 10: CLL-001 (3.4/2.8), CLL-003 (2.0/1.5), CLL-005 (3.6/3.0). En s3-1 `describe()` le dio a CLL-003 pistas sobre su medicación, el paciente se inventó una receta (*"why I need to be taking specific medications"*) y el médico puntuó `specific_concerns` 3.0 sobre un fármaco inexistente. Arreglo: `null` en las dos *specific* de esos tres. **Y se ve al revés en s3-3**: el informe dio NA a `specific_necessity`, `general_harm` y `general_overuse` para CLL-003, que es lo correcto, mientras el ground truth dice 2.0/1.8/2.0. Evaluado hoy, contarían como fallos del médico |
| C2 | **`causes` vive dentro de `b_ipq`**, junto a ocho números y siendo una lista de strings. Cualquier código que itere y promedie se la traga. | RESUELTO — `BIPQ_DIMENSIONS` la excluye; hay test de tipos por dimensión |
| C3 | **Cobertura incompleta en la conversación**: el médico no llega a algunas dimensiones. | ABIERTO — en s3-1 y s3-2 (12 y 11 turnos, cerradas por el médico) **`causes`, `general_harm` y `general_overuse` no se mencionaron ni una vez**, y aun así el informe las puntuó o se las inventó. `DOCTOR.md` ya avisa (*"If you never ask, you will never know"*) y no basta: en el brazo Ruby, con tabla de sondeos incluida, fue 0/10 en esas mismas dimensiones. Lo arregla `coverage_hint` (§4.1), no más prosa |

## Hallazgos del brazo nuevo

No vienen heredados: salen de las corridas de la Etapa 3.

| # | Problema | Estado |
|---|---|---|
| N1 | **El paciente no interpreta su perfil.** CLL-003 tiene `consequences` 2, `concern` 2, `emotional_response` 1 y `coherence` 9 — alguien tranquilo, poco afectado y bien informado. En s3-1 dijo *"we're both quite worried"*, *"really unnerving"* y *"struggling even to do those things"*, y además rompió los hechos clínicos: *"carrying this condition over the years"* con un diagnóstico de hace 6 meses. El médico puntuó bien lo que oyó; lo que oyó era otro paciente. | ABIERTO — §6.2 ya marca `dolphin-llama3` como PROVISIONAL y sin verificar. Hace falta la sonda de fidelidad antes de tocar nada aguas abajo: mientras falle, cualquier MAE mide la infidelidad del paciente, no la inferencia del médico |
| N2 | **La dispersión entre corridas tapa cualquier mejora.** Cuatro corridas, misma configuración y mismo prompt: CLL-003 dio MAE 3.25, 2.00 y 2.75. El informe se genera a temperatura 0, así que toda esa diferencia viene de la conversación (0.7). | ABIERTO — ninguna intervención medible es más grande que ese ruido. Hace falta `run_batch.py` (§2, PORTAR) antes de evaluar un solo cambio de prompt o de ancla |
| N3 | **Causas que no son causas.** En cuatro corridas el médico nunca preguntó por causas, y aun así devolvió algo. Primero circular (*"history with CLL"*, *"CLL diagnosis"*), después el **mecanismo de la enfermedad** (*"affecting my body's immune system cells"*, *"chronic condition affecting my immune system"*). La verdad de HIV-002 es conductual — *"unprotected sex"*, *"being too trusting of a partner"* — y no se parece en nada. Con `coverage_hint: "off"` no preguntar es el resultado esperado; responder igualmente, no. | ABIERTO — lo puede cortar la validación (1.13) sin modelo: una causa sin `causes_evidence` que la sostenga no es una causa |
| N4 | **El modelo pone vallas al JSON.** `REPORT.md` pide un objeto y nada más, sin *code fences*; GLM lo envuelve en ```` ```json ```` igualmente. | RESUELTO — `report.parse` las quita antes de parsear, y hay test de regresión con la forma real |
| N5 | **El modelo elige un registro por corrida, no una puntuación por dimensión.** s3-1 `6,6,6,6,6,6,6,6`; s3-2 `2,6,4,4,2,4,6,4`; s3-3 `6,8,8,6,6,4,8,6`; s3-4 `8,8,6,8,8,8,8,8`. Dentro de cada corrida se mueve poco; lo que se desplaza entre corridas es el centro. No es ruido por dimensión: decide pronto "qué tipo de paciente es" y puntúa alrededor de esa impresión. Es P4 en una forma más difícil de ver que el 67% de ochos de llama3.2. | ABIERTO — lo mide 2.5 (discriminación) junto a 2.4 (dispersión), nunca el MAE solo |
| N6 | **El MAE puede engañar.** s3-4 es el mejor de los cuatro (1.75) con siete ochos de ocho: acertó porque HIV-002 es un paciente alto y le tocó registro alto. Dentro de ese mismo informe, `identity` verdad 3 e informe 8 — error 5. | ABIERTO — no publicar MAE sin discriminación al lado (2.5) |
| N7 | **La confianza declarada no calibra.** s3-3 `emotional_response` verdad 1, informe 6, confianza 0.8; `timeline` verdad 3, informe 8, confianza 0.9. Confianza alta no predice acierto, así que hoy no sirve para filtrar. Sí es honesta en los NA: `general_harm` con 0.0 en s3-4. | ABIERTO — se cruza con la dispersión observada en la Etapa 6 (2.3 + 2.4) |
| N8 | **El reintento del informe no se ha disparado nunca.** Cuatro corridas, `attempts: 1` siempre: las doce dimensiones vienen con justificación. Los tests cubren que funciona; no hay evidencia todavía de que haga falta. | ABIERTO — vigilar en la primera tanda de `run_batch.py` |
| N9 | **1.12 queda abierto a propósito.** La Etapa 3 cierra con `coverage_hint: "off"`, así que el sondeo dirigido por ambigüedad no tiene mecanismo: el médico sondea lo que quiere y la cobertura se audita después (3.2). Decisión deliberada — forzar cobertura infla el resultado y convierte la consulta en cuestionario. | DECIDIDO — los tres brazos (`off` / `declare` / `show`) existen y se comparan en la Etapa 8 |

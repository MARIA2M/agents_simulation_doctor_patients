# Errores heredados

Fallos concretos de los brazos anteriores, con dónde se vieron y en qué estado
están aquí. Sirve para dos cosas: no repetirlos, y poder decir al arreglar uno
qué cambió exactamente.

Estado: **RESUELTO** · **ABIERTO** · **PENDIENTE** (le toca a una etapa futura).

---

## Brazo Python (elicitación)

| # | Problema | Estado |
|---|---|---|
| P1 | **Valor por defecto en vez de NA.** El scorer metía un 5 (3.0 en BMQ) cuando el JSON no parseaba, y si eso fallaba cogía el primer número del texto. Valores inventados que después contaban como aciertos (4.4). | PENDIENTE — Etapa 3, `report.py` |
| P2 | **Repreguntar por longitud.** El routing disparaba con `len(respuesta) < 10 palabras`, así que una respuesta larga y vaga pasaba directa a puntuación (1.12). | RESUELTO — no hay regla de longitud en el código; `DOCTOR.md` dice *"thin is about content, not length"* |
| P3 | **Recorrido por lista de preguntas.** `q_index`, `bmq_index` y `follow_up_count` marcaban el ritmo: el cuestionario era el guion. | RESUELTO — fuera del `State`; el médico decide por llamada a herramienta |
| P4 | **Scorer degenerado.** llama3.2 puso ochos el 67% de las veces. Máxima consistencia, cero discriminación (2.5). | ABIERTO — se mide en la Etapa 6 con 2.4 + 2.5 juntas |
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
| R3 | **`Score \| Rationale`**: la justificación se generaba después del número, así que era decorativa (2.1). | PENDIENTE — Etapa 3, orden `evidence → reasoning → score` |
| R4 | **Rúbrica en espejo.** `DOCTOR.md` decía qué escuchar y `PATIENT.md` cómo expresarlo: la misma tabla en los dos lados. Parte del acierto era descifrar un código nuestro (5.5). | RESUELTO en los prompts v2 — el médico recibe qué captura cada dimensión, no qué señal corresponde a qué nivel |
| R5 | **Solo 0 y 10 anclados** en la escala: cualquier evidencia empuja al extremo (2.2). | PENDIENTE — Etapa 3, `prompts/rubric/` |
| R6 | **Turnos vacíos (~19%) e informes fallidos (~26%)** sin reintento (3.1). | RESUELTO — `llm.py` reintenta transporte y respuesta vacía, y lo anota en `events` |
| R7 | **`salloc` sin `srun`** en `submit.sh`: el trabajo corría en el nodo de login, que en ACC también tiene H100, así que no se notaba (§6.3). | RESUELTO a medias — `metadata.compute` guarda `hostname` y `slurm_nodelist` para detectarlo; falta el lanzador |
| R8 | **Temperatura implícita.** Gepeto aplica 0.7 si no se envía, y es estocástico incluso a 0 (§12). | RESUELTO — temperatura y `num_ctx` se envían siempre y se registran |
| R9 | **`OLLAMA_CONTEXT_LENGTH` y `keep_alive` como variables del servidor**: invisibles desde el cliente y ausentes de la metadata. | RESUELTO — van en cada petición desde el perfil |

## Corpus (los dos brazos comparten los mismos 10 perfiles)

| # | Problema | Estado |
|---|---|---|
| C1 | **CLL-001 no toma medicación** (*watch and wait*) pero tiene BMQ `specific_necessity` 3.4 y `specific_concerns` 2.8. Las subescalas *specific* se definen sobre el fármaco recetado: sin receta no hay creencia que medir, y el prompt del paciente se contradice. | ABIERTO — revisar los 10; deberían ser NA |
| C2 | **`causes` vive dentro de `b_ipq`**, junto a ocho números y siendo una lista de strings. Cualquier código que itere y promedie se la traga. | RESUELTO — `BIPQ_DIMENSIONS` la excluye; hay test de tipos por dimensión |
| C3 | **Cobertura incompleta en la conversación**: en la primera corrida real el médico no preguntó por `causes`, `personal_control`, `treatment_control`, `coherence` ni `general_harm`. | ABIERTO — lo medirá `coverage.py` (3.2) en la Etapa 6 |

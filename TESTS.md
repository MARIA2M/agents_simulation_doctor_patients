# Qué cubre la suite

Inventario vivo de `tests/`. Para cada fichero: qué guarda, contra qué fallo
concreto, y si hace falta. **Se actualiza al añadir, quitar o cambiar un test.**
Se contrasta con [TASKS.md](TASKS.md) y con los ocho invariantes de
[ARCHITECTURE.md](ARCHITECTURE.md) §9.

**202 funciones `test_`; los casos con parametrización están sin recontar desde
el 2026-08-26** —eran 346 con 198 funciones—. Ninguna toca la red: el LLM está
sustituido por respuestas guionizadas.

El recuento de funciones sale de `grep -c '^def test_' tests/test_*.py`; el de
casos exige pytest, y `test_corpus.py` acaba de pasar de 21 a 40. Recontar antes
de fiarse del número.

Los casos **no dependen solo de los tests**: `test_config.py`, `test_metadata.py`
y `test_prompts.py` se parametrizan sobre `config/*.yaml`, así que **cada brazo
nuevo añade casos a tests que nadie ha tocado**. Los dos perfiles de estilo de
1.14 sumaron 7 por sí solos. Un número que sube sin que se haya escrito un test
no es una regresión: son perfiles nuevos. Para recontar:

```bash
./venv-hpc/bin/python -m pytest tests/ --collect-only -q | sed 's/::.*//' | sort | uniq -c
```

```bash
AHEAD_GRAPH_TESTS=1 ./venv-local/bin/python -m pytest tests/ -q
```

Sin la variable quedan fuera los dos de punta a punta, que son los únicos que
construyen el grafo y por tanto importan `langgraph`.

Leyenda: **✅** hace falta · **📄** documenta más que verifica.

---

## Resumen

| Fichero | Funciones | Casos | Qué guarda | Etapa |
|---|---|---|---|---|
| `conftest.py` | — | — | Andamio compartido: `PATIENT`, `speaks`, `note`, `profile`, `in_mode`, y las fixtures `scripted`, `state`, `make_run_profile` | — |
| `test_config.py` | 22 | 28 | Los perfiles cargan; ninguno deja un ajuste al servidor | 1 |
| `test_corpus.py` | 7 | 40 | Los 10 pacientes, su ground truth, y de dónde salió cada número | 1 |
| `test_metadata.py` | 13 | 15 | La provenance se recoge entera y sobrevive al disco | 1 |
| `test_llm.py` | 11 | 11 | Qué viaja en cada llamada y qué se reintenta | 2/4 |
| `test_prompts.py` | 16 | 16 | Composición determinista desde disco, y sus hashes | 2 |
| `test_styles.py` | 16 | 95 | Los nueve estilos del médico: registro, forma, contenido y brazos | 2 |
| `test_tools.py` | 6 | 12 | Leer la llamada, y armar las tools de cada brazo | 2 |
| `test_nodes.py` | 7 | 7 | El bucle, y el aislamiento del perfil | 2 |
| `test_patient_profile.py` | 12 | 28 | Puntuación → conducta, y el hueco que se deja sin puntuación | 2 |
| `test_coverage_hint.py` | 12 | 18 | El brazo `coverage_hint` | 3 |
| `test_notes.py` | 9 | 14 | El brazo `working_notes` | 3 |
| `test_report.py` | 32 | 42 | Esquema, parseo, huecos, reintento, salida a disco | 3 |
| `test_evaluation.py` | 14 | 14 | MAE, sesgo, bandas, las dos correlaciones | 5 |
| `test_causes.py` | 17 | 17 | Coseno, emparejamiento, taxonomía, método registrado | 5 |
| `test_evaluate.py` | 8 | 8 | El punto de entrada de 4.7 — nunca estuvo en esta tabla | 5 |

### `conftest.py`

Lo que comparte la suite. Vive aquí porque antes vivía en un fichero de test:
`test_nodes` exportaba `PATIENT`, `speaks`, `scripted` y `state` a otros tres
ficheros, y `test_coverage` exportaba `profile` e `in_mode` a un cuarto. Tocar
`PATIENT` rompía ficheros que no lo mencionaban, y el orden de importación pasaba
a contar.

`PATIENT` es watch-and-wait a propósito (C1: las subescalas `specific_*` no
tienen fármaco del que hablar) y lleva el `belief_profile` entero, que es lo que
el test de aislamiento busca en el contexto del médico.

---

## Fase 1 — Base

### `test_config.py` — 22 funciones, 28 casos

Todos ✅. El bloque de rechazos existe porque **un ajuste que falta no da error:
lo decide el servidor** (§12), y entonces la metadata miente.

| Test | Qué impide |
|---|---|
| `test_shipped_profile_loads` | Un perfil del repo que no carga |
| `test_shipped_profile_survives_first_load_from_gpfs` | Timeout < 300 s: el primer blob desde GPFS aborta (§6.1) |
| `test_each_load_is_independent` | Estado compartido entre perfiles |
| `test_temperature_is_required_for_every_role` | Un rol muestreando a lo que decida el servidor |
| `test_zero_temperature_is_accepted` | Que un check de falsedad tire 0.0, que es una temperatura |
| `test_missing_model_is_rejected` | — |
| `test_missing_turn_limit_is_rejected` | Sin `max_turns` nada para a un médico que no cierra (1.5) |
| `test_missing_paths_are_rejected` | Un `KeyError` pelado a mitad de una tanda |
| `test_declared_profile_must_match_filename` | Corridas mal etiquetadas en la metadata |
| `test_unknown_profile_is_rejected` | — |
| `test_the_coverage_arms_are_accepted` | — |
| `test_a_retired_mode_is_rejected` | Que un perfil viejo con `declare` corra como si nada |
| `test_an_unquoted_off_is_caught_and_named` | `off` a secas es `False` en YAML: leería como "sin cobertura" significando "nadie eligió" |
| `test_a_quoted_working_notes_is_caught_and_named` | El espejo de la trampa anterior: aquí el peligro es **entrecomillarlo**. `"off"` es una cadena no vacía, y encendería el brazo sin que nadie lo pidiera |
| `test_ollama_url_can_be_redirected` | — |
| `test_causes_is_not_a_numeric_dimension` | Que algo itere `b_ipq` y promedie una lista de strings |

Los rechazos dependen de que `make_run_profile` **sustituya** el bloque en vez de
fusionarlo: omitir una clave es cómo se comprueba que es obligatoria. Fusionar
volvería verdes cuatro tests sin que nada los sostenga.

### `test_corpus.py` — 7 funciones, 40 casos

Reescrito el 2026-08-26, cuando `patients/` pasó a ser el corpus de CK
normalizado. Lo que cambió de fondo: el corpus ya **no** es el del brazo Ruby, y
**C1 se retiró** — CK puntúa las `specific_*` también sin receta.

| Test | Necesidad |
|---|---|
| `test_corpus_has_ten_patients` | ✅ |
| `test_profile_carries_ground_truth` | ✅ cada dimensión es un número, lo que cubre también que la clave exista, y ahora dentro de rango: B-IPQ 0–10, BMQ 1–5. Ya no exige NA sin receta |
| `test_patients_is_the_normalised_ck_corpus` | ✅ el que sustituye a 0.3. Reejecuta la normalización sobre `patientsCK/` y exige que reproduzca el fichero byte a byte. Sin él, `patients/` es un directorio editado a mano y la procedencia del ground truth se pierde |
| `test_the_ruby_corpus_is_frozen` | ✅ lo que 0.3 protegía, movido a `sintetic_patients/patients_version1/`. Las tandas de `runs/historic/` se puntuaron contra ese corpus, así que reanalizarlas exige que siga intacto |
| `test_the_item_mean_returns_the_one_to_five_scale` | ✅ 5 casos. El denominador es el número de ítems por 5, no un divisor: `21/25` es una suma de 21 sobre 5 ítems, o sea 4.2, y nunca la proporción 0.84. Incluye suelo y techo |
| `test_an_unexpected_maximum_is_refused` | ✅ el importante de los dos. Un máximo que no cuadra significa otro número de ítems, y normalizarlo igual mete un valor en otra escala sin que se note. Es el caso del `7/10` de CLL-003 |
| `test_the_normaliser_leaves_the_beliefs_alone` | ✅ solo el BMQ cambia de forma. Si el script tocara `b_ipq`, el ground truth de ocho dimensiones dependería de él sin que nadie lo hubiera decidido |

### `test_metadata.py` — 13 funciones, 15 casos ✅

`test_the_temperature_recorded_is_the_one_that_will_be_sent` se compara contra
`llm.sampling_options`, que es quien mete la temperatura en la petición: que la
metadata guarde un número no vale de nada si el que viaja es otro, y son dos
lecturas distintas del mismo bloque (§12).

Los demás guardan cosas que se pierden fácil:
`test_code_provenance_answers_both_questions` (un commit sin `dirty` nombra otro
código), `test_compute_records_both_hostname_and_nodelist` (la señal de §6.3),
`test_started_at_carries_a_timezone`, `test_serialises_completely`.

---

## Fase 2 — Bucle agéntico

### `test_llm.py` — 11 ✅

Dos mitades, las dos necesarias. **Qué viaja**: temperatura y `num_ctx` siempre
explícitos, seed solo si está, `keep_alive` en cada llamada (sin él el servidor
suelta el modelo a los cinco minutos), tools solo cuando se dan, y el informe lo
escribe el modelo del médico. **Qué se reintenta**: respuesta vacía (el 19% del
corpus anterior), fallo de transporte hasta `MAX_ATTEMPTS`, y cada reintento deja
un evento.

`test_a_reply_with_only_tool_calls_is_not_empty` evita que el reintento de turnos
vacíos se coma el caso normal: el médico habla *por* la herramienta, así que su
`content` está vacío por diseño.

### `test_prompts.py` — 16 ✅

Resolución de ficheros, composición ordenada (skills antes que recursos, cada rol
solo los suyos), separador entre fragmentos, y hashes.

Los tres de hash son el motor de la Fase 6:
`test_the_hash_is_of_the_composed_prompt_not_the_base_file` es lo que permite
atribuir un cambio de resultado a un cambio de prompt.

`test_the_doctor_never_sees_the_scale_during_the_consultation` merece señalarse:
la rúbrica solo llega al informe. Un médico con las anclas en la mano estaría
puntuando mientras habla, que es el brazo de elicitación por otra puerta.

`test_an_arm_that_adds_a_tool_argument_changes_the_tool_hash` cierra un agujero
de provenance: las descripciones de las tools son instrucciones, y hasta ahora no
las hasheaba nadie. Se podía reescribir la del argumento `notes` —cambiando lo
que el médico anota— y `metadata.json` salía idéntico.

### `test_styles.py` — 16 funciones, 95 casos ✅

Los nueve estilos de comunicación del médico (1.14): ocho portados de
`ahead_agent_ckakalou` y `good_doctor`, que es lo que `DOCTOR.md` llevaba dentro.
Ninguno toca la red — si el estilo *cambia* el transcript no se puede preguntar
aquí, y esa es la mitad viva del test de §5.1.

Cuatro bloques, y cada uno guarda un fallo distinto:

**El registro contra el directorio.** `test_every_style_has_a_file_and_every_file_a_style`
es la corrección del bug del origen: `prompt_builder.py:20` escribía
`high_psysician_control_paternalistic` y el fichero decía `physician`, así que ese
estilo era inalcanzable por los dos lados. La ortografía nunca fue el arreglo.

**Qué puede decir un estilo.** `test_no_style_names_the_instrument_or_the_scale`
y `test_no_style_tells_the_doctor_which_dimensions_will_stay_empty`. El segundo es
el que importa: la sección 9 del origen le decía al médico qué construcciones
quedarían visibles y cuáles vacías, y es el mismo agente que después puntúa esas
construcciones y puede devolver NA. Nombrar una dimensión no es el problema
—`DOCTOR.md` §5 las lista todas—; predecírselas sí. Viven en `styles.yaml`, y
`test_the_hypotheses_stayed_out_of_the_prompt` comprueba que se quedaron ahí.

**Composición y hashes.** `test_each_style_gives_the_doctor_prompt_its_own_hash`:
nueve estilos, nueve hashes distintos, o dos brazos son una sola corrida en la
provenance. `test_the_anchors_still_do_not_reach_a_doctor_with_a_style` repite con
skill cargada el invariante de `test_prompts`: un estilo es una vía nueva para
que la escala llegue a la consulta.

**Los perfiles del disco.** `test_every_profile_names_exactly_one_style` es una
regla nueva del proyecto, no una comprobación de código: después de 1.14 el
estilo del médico es siempre un fichero que alguien eligió. Un perfil sin estilo
corre el brazo sin nombre que esta tarea existe para eliminar.
`test_the_style_left_the_base_prompt_and_is_in_good_doctor` guarda las dos
mitades del traslado: si la frase sigue en `DOCTOR.md`, todos los estilos la
contradicen; si no está en `good_doctor.md`, el brazo bajo el que se midió todo
lo anterior ha cambiado sin que nadie lo decida.

**La forma del fichero.** `test_every_style_has_the_same_three_sections` y
`test_a_style_constrains_about_as_much_as_it_prescribes`. El segundo sale de un
fallo real: `good_doctor` se escribió con cinco instrucciones y **una** sola
prohibición, contra cuatro en los ocho portados. Presión de restricción desigual
es una diferencia entre brazos que no ha elegido nadie, y cae justo sobre el eje
que los estilos quieren variar.

### `test_tools.py` — 6 funciones, 12 casos ✅

`test_a_broken_call_raises_rather_than_ending_the_consultation` es el importante:
una llamada rota **no** es una decisión de cerrar. Confundirlas metería consultas
truncadas en el corpus como si el médico las hubiera dado por terminadas.

`test_building_the_tools_never_touches_the_one_the_module_ships` recorre los
cuatro modos: `doctor_tools` copia antes de añadir argumentos, y si mutara la
constante el primer brazo dejaría contaminados a los siguientes dentro del mismo
proceso — y una tanda corre los brazos en el mismo proceso.

`test_the_patient_reply_goes_back_as_the_tool_result` guarda el canal: en un
resultado de herramienta el médico no distingue nuestras palabras de las del
paciente, y `Evidence.quote` tiene que ser una línea literal suya.

### `test_nodes.py` — 7 ✅

Contiene el invariante 1, el único obligatorio desde la Etapa 2:
`test_the_patient_profile_never_reaches_the_doctor` serializa todo lo enviado al
médico y busca cada valor del `belief_profile`. Su complemento,
`test_the_patient_is_told_who_they_are`, comprueba que ese mismo perfil sí llega
al paciente.

---

### `test_patient_profile.py` — 12 funciones, 28 casos ✅

La puntuación se convierte en conducta, y lo que no tiene puntuación no se
inventa. Tres bloques:

- **Fronteras de banda.** `_band_for` usa `score <= upper`, así que un 2 sigue
  siendo la primera banda y un 2.1 ya es la segunda. Se recorren las dos
  escaleras enteras —2/4/6/8/10 en B-IPQ, 2/3/4/5 en BMQ— porque son distintas y
  confundirlas desplazaría a todos los pacientes una banda.
- **Lo que falta se omite** (P9): una dimensión sin número, un valor que no es
  número, y el bloque de medicación entero desapareciendo cuando el paciente va
  en watch-and-wait (C1).
- **Lo que el paciente lee.** Los hechos clínicos van literales, pero
  `test_the_score_itself_never_reaches_the_patient` comprueba que el número no
  aparece nunca: es 1.9 en una línea.

Ver también la regla del suelo de bandas en TASKS 7.1 — hoy un B-IPQ de 0 se
jugaría como un 2, y el corpus todavía no tiene ninguno.

## Fase 3 — Informe y brazos

### `test_report.py` — 32 funciones, 42 casos ✅

Cinco bloques, todos con motivo:

- **El esquema es la especificación** (2.1) — `evidence` antes que `score`, y NA
  como valor.
- **Parseo** — objeto con y sin cercas (GLM las pone aunque REPORT.md pida que no),
  cualquier otra cosa es `None` para que salte el reintento, y
  `test_a_score_off_the_scale_is_na_and_never_clamped`: el brazo viejo hacía
  min/max y convertía un valor ilegal en uno legal de aspecto.
  `test_the_two_scales_are_judged_separately` — 5.5 es legal en B-IPQ e ilegal en BMQ.
- **Qué cuenta como inacabado** (1.13) — la distinción fina de `gaps()`: un NA
  declarado **tiene razonamiento y es una respuesta**; uno que rellenó el parser
  no la tiene, y ese silencio es lo único que se pregunta dos veces. `causes`
  queda fuera a propósito: exigirlo es lo que produce una causa inventada (N3).
- **Rendirse en vez de dar vueltas** — y `test_every_way_of_finishing_routes_to_the_report`,
  que es 1.13 entero: el informe corre lo haya cerrado quien lo haya cerrado.
- **Quién lo escribe** — D9. El médico continúa su consulta, no lee un transcript
  en frío; se le manda el transcript numerado porque `Evidence.turn` lo necesita;
  y se le pide sin tools porque no queda nada que preguntar.

Los dos de punta a punta están detrás de `AHEAD_GRAPH_TESTS=1`.
`test_a_thin_report_is_asked_for_again_and_then_given_up_on` es **el único sitio
donde el camino de reintento se ejercita completo**: en vivo nunca se ha
disparado (N8, 24 corridas con `attempts: 1`).

### `test_coverage_hint.py` — 12 funciones, 18 casos ✅

| Test | Qué guarda |
|---|---|
| `test_off_never_asks_the_doctor_anything` | La línea base no tiene el argumento |
| `test_show_asks_and_promises_what_comes_back` | — |
| `test_the_dimensions_it_names_are_taken` | — |
| `test_anything_it_does_not_declare_properly_is_simply_no_news` | Nada de cobertura puede costar una llamada |
| `test_a_reply_with_no_call_declares_nothing` | — |
| `test_the_note_is_a_separate_message_in_our_own_voice` | Va por `role: user`, el canal del OPENING, nunca dentro del resultado de la herramienta |
| `test_there_is_no_note_when_nothing_is_open` | — |
| `test_the_map_accumulates_across_turns` | — |
| `test_show_hands_back_what_is_still_open` | — |
| `test_the_patient_never_sees_the_coverage_note` | En el contexto del paciente sería una lista de temas |
| `test_the_doctor_can_always_close_with_dimensions_open` | Los cuatro modos: ninguno obliga a cubrir nada (1.5) |
| `test_off_hands_back_nothing_at_all` | — |

### `test_notes.py` — 9 funciones, 14 casos ✅

| Test | Qué guarda |
|---|---|
| `test_no_notes_argument_by_default` | — |
| `test_the_two_switches_are_independent` | Las cuatro combinaciones; en un solo valor no se sabría cuál produjo el efecto |
| `test_a_note_is_taken_with_its_dimension` | — |
| `test_anything_malformed_is_discarded_and_the_call_survives` | Seis formas malas |
| `test_a_note_carries_the_turn_it_was_taken_in` | — |
| `test_a_second_note_on_the_same_dimension_is_added_not_replaced` | **El que justifica el brazo**: la revisión fechada es lo único que puede enseñar si 1.11 compra algo |
| `test_nothing_is_recorded_when_the_arm_is_off` | El que falló y descubrió que `doctor_node` no miraba el interruptor |
| `test_the_patient_never_sees_the_notes` | — |
| `test_the_transcript_keeps_only_what_was_said` | Una nota en el transcript es una frase que nadie pronunció, y 3.2 verifica citas contra él |

---

## Fase 5 — Evaluación

### `test_evaluation.py` — 14 ✅

Separa explícitamente **portado** de **nuevo**, que es lo que hace auditable el
port. Portado: error absoluto, sesgo con signo, bandas, MAE y mediana a mano.

Nuevo, y cada uno contra un fallo concreto del original:

- `test_an_na_is_excluded_from_the_mae_and_counted` — saltárselo en silencio daría
  a un informe de 11 NAs un MAE perfecto.
- `test_between_patient_has_nothing_to_say_when_everyone_gets_the_same_report` —
  **es 2.5**: el scorer degenerado de llama3.2 (67% ochos) tenía dispersión
  perfecta y era inútil.
- `test_ranking_survives_a_compressed_scale` — lo que muestra `e4-1`: el orden
  está bien y el rango va a la mitad. Son problemas distintos y se arreglan
  distinto (calibración, no más sondeo).
- `test_the_per_patient_mean_hides_what_the_per_dimension_bias_shows` — 4.5:
  Ruby informaba +0.13 agregado con `identity` en +1.00.
- `test_a_correlation_that_cannot_be_computed_is_none_not_zero` — el portado
  devolvía 0.0, que se lee como "sin correlación" cuando significa "sin datos".

### `test_causes.py` — 17 ✅

Portado: coseno (incluido el vector cero, que dividiría por cero), emparejamiento
greedy, umbral. Nuevo: `None` en vez de 0.0 sin ground truth, `None` en vez de
`"unknown"` para una respuesta ilegible —porque `unknown` es una categoría real
del paciente que no sabe—, y **el método registrado**: el módulo viejo cambiaba
de métrica en silencio al fallar los embeddings, así que una tanda podía mezclar
dos medidas sin dejar rastro.

Dos son regresión pura del parser viejo: `test_text_with_b_and_r_survives_intact`
(borraba toda `b` y `r`: "Stress" → "St ess") y `test_markup_in_a_cause_is_left_alone`.

---

## Qué se quitó, y por qué

Cuatro tests retirados en la limpieza. Ninguno dejó de comprobarse: los cuatro
estaban duplicados en otro sitio. Se anota aquí y no en el mensaje del commit
porque un test borrado se mira meses después, y el sitio donde se mira es este.

| Retirado | Dónde sigue comprobándose |
|---|---|
| `test_coverage.py::test_the_patient_channel_carries_only_the_patient` | `test_tools.py::test_the_patient_reply_goes_back_as_the_tool_result`, misma aserción. Se le pasó el razonamiento del canal |
| `test_coverage.py::test_asking_the_doctor_does_not_disturb_the_tool_it_already_had` | Fusionado en `test_tools.py::test_building_the_tools_never_touches_the_one_the_module_ships`, ahora sobre los cuatro modos |
| `test_notes.py::test_the_tool_the_module_ships_is_never_touched` | El mismo invariante, mismo destino |
| `test_notes.py::test_the_doctor_still_closes_when_it_wants` | `test_coverage_hint.py::test_the_doctor_can_always_close_with_dimensions_open`, que pasó de 2 modos a las 4 combinaciones |
| `test_config.py::test_dimension_ids_match_every_patient` | `test_corpus.py::test_profile_carries_ground_truth` exige que cada dimensión sea un número dentro de rango, y no se lee el valor de una clave que falta |

`test_coverage.py` pasó a llamarse **`test_coverage_hint.py`**. "Coverage"
significaba tres cosas a la vez: `causes.similarity.coverage_score` (portado), el
brazo `coverage_hint` (este fichero) y el mapa dimensión × paciente de 3.2 (sin
escribir). El nombre libre le hace falta a 3.2.

---

## Qué no está cubierto

| Módulo | Estado |
|---|---|
| `run_batch.py` | 0 tests. Sus dos guardas (árbol sucio, dos temperaturas a 0) no las comprueba nada. Se deja así de momento |
| `reproducibility.py` | 0 tests. Borrador sin verificar — se planifica antes de tocarlo, y no se usan sus números |
| `main.py` | 0 tests |
| `coverage.py` (3.2) | No existe |
| `artifacts.py` (5.4) | No existe |
| `api_server.py` (§8.9) | No existe |
| Skills §5.1 | El mecanismo está probado; el test espera a que exista un documento de skill sobre el que correrlo |

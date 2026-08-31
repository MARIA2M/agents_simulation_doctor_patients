# Pendientes

Lo que queda abierto, con lo que hace falta antes de poder tocarlo. Corte del
2026-08-31. `TASKS.md` sigue siendo la lista completa por fases; esto es solo lo
que está vivo.

---

## La tanda que desbloquea todo lo demás

**Todo lo que queda abierto se atasca en el mismo sitio: no hay ninguna tanda
con cinco repeticiones.** Sin eso 2.4 no da número, y sin 2.4 no hay 2.5, ni
2.6, ni 4.6. Es un problema de datos, no de código.

**Son cinco, no tres.** `coverage.py` fija `MIN_REPEATS = 5` y por debajo
devuelve `sd: None`, que es lo que pide TASKS 2.4 —«por debajo de N=5 la
dispersión no significa nada»—. Este documento decía tres hasta el 2026-08-31 y
estaba equivocado: una tanda de 3 sale entera en nulos.

Orden de ejecución, con los brazos de estilo que `skills/styles/README.md` dejó
fijados y sin lanzar:

```bash
git add -A && git commit -m "..."          # run_batch aborta con el árbol sucio
. serve_ollama.sh                          # en el nodo de cómputo, no en login

# Cronometrar UNA antes de comprometerse a cuarenta
time ./venv-hpc/bin/python run_batch.py --profile style-narrowly_biomedical \
     --patients patients/CLL-001.json --repeats 1 --run-id timing-1

./venv-hpc/bin/python run_batch.py --profile style-narrowly_biomedical --repeats 5 --run-id s52-nb-1
./venv-hpc/bin/python run_batch.py --profile style-biopsychosocial     --repeats 5 --run-id s52-bps-1

# Post-proceso. Solo rescore.py necesita el servidor: va antes de soltar el nodo.
./venv-hpc/bin/python fidel.py    runs/s52-nb-1 --profile hpc   # 3.5, sin servidor
./venv-hpc/bin/python cover.py    runs/s52-nb-1                 # 3.2 + 2.4, sin servidor
./venv-hpc/bin/python rescore.py  runs/s52-nb-1 --profile hpc   # 5.4, CON servidor
./venv-hpc/bin/python evaluate.py runs/s52-nb-1 --profile style-narrowly_biomedical
```

**El orden no es decorativo.** Fidelidad primero: si el paciente no jugó su
perfil, ni la cobertura ni el MAE de esa consulta dicen nada. Después cobertura,
porque 3.4 prohíbe analizar un corpus que no ha pasado 3.2, y un MAE sobre
números sin fundamento no significa nada. La evaluación va la última.

**Se puede subir de 2 a 5 sin repetir nada.** `run_batch.py` salta lo que ya
existe, así que relanzar con `--repeats 5` y **el mismo `--run-id`** añade solo
las vueltas que faltan.

**Puerta D antes que nada** (`skills/styles/README.md`): que toda consulta cierre
con `stop_reason: doctor`. Si alguna se agota por `max_turns`, el estilo cambió
la regla de cierre y todo lo de abajo hereda el problema.

**No comparar contra `e4-1`**: es pre-styles, otro hash de prompt, otras bandas y
otro build del modelo del paciente (`hpc.yaml` fija hoy
`dolphin-llama3:8b-v2.9-q8_0`; `e4-1` corrió el `dolphin-llama3` sin etiqueta,
que resuelve al Q4). Los brazos se comparan entre sí.

---

## El plan de cobertura, por peldaños

El diseño por capas y qué paper respalda cada una están en **ARCHITECTURE §13**.
Aquí solo el orden y lo que bloquea cada peldaño.

| | Qué es | Bloqueado por | Coste |
|---|---|---|---|
| **L0** ✅ | integridad de citas, scores sin fundamento, dispersión | — | hecho |
| **F1** ✅ | `fidelity.py` — ¿juega el paciente su perfil? | — | hecho 2026-08-31 |
| **L0b** | 2.5 y 2.6 dentro de cobertura | que acaben las tandas con N≥5 | ~35 líneas |
| **G** | conjunto etiquetado, forma AIS (ver §13.5) | **tu tiempo**, ~20 min | — |
| **L1** | el juez de ASKED — checklist, terreno firme | G, y el umbral sin fijar | ~400 líneas + rúbrica |
| **L2** | ¿la cita es de esa dimensión? — atribución, terreno malo | L1, y un modelo NLI | ver §13.4 |

**L0b y G no dependen una de otra.** L1 y L2 sí van detrás de G, y **no van
encadenadas entre sí**: son tareas con fiabilidades distintas y L2 puede no
hacerse nunca.

**Antes de pedir etiquetas**, las dos validaciones que no cuestan anotación
(§13.6): degradar al médico a propósito y ver si la cobertura cae, y contrastar
dos modelos entre sí. Ninguna da accuracy, pero acotan.

### F1 — hecho, y con qué límite

`ahead_agent/fidelity.py` + `fidel.py`. Determinista, sin modelo, y **lee
`patients/*.json`**, que es justo lo que `coverage.py` tiene prohibido: por eso
son dos ficheros y no uno. Escribe `fidelity.json` y no toca ninguna puntuación.

Cuatro comprobaciones, en dos severidades:

- **CONTRADICTION** — el perfil dice lo contrario, o no dice nada y el paciente
  se lo inventa. Reclamar medicación con un régimen `watch and wait`, nombrar un
  fármaco con ese régimen —incluido «I'm taking ibrutinib», que no contiene
  ningún sustantivo de medicación—, o decir una edad que no es la del perfil
  **o que el perfil no registra**. Un dato ausente no es carta blanca. Es el
  fallo real de `s51-nb-1` r1.
- **UNSUPPORTED** — nombrado y no sostenido: un fármaco de más en un paciente ya
  tratado, un síntoma que el perfil no lista. Un paciente real da detalles, así
  que esto se lee, no suspende por sí solo.

**Lo que no es: una medida.** Lee entidades nombradas, no significado, así que
un paciente que se invente una narrativa entera con palabras que no están en
ninguna lista pasa limpio. **Todo fallo de detección cae del lado del aprobado**,
y por eso la tasa que emite es una **cota superior** de la fidelidad y nunca una
puntuación. Se lee una corrida que falla; no se lee una tasa que aprueba.

Es la misma trampa que este documento describe abajo para la cobertura —una
lista de palabras mide vocabulario, no tema—. La diferencia está en la pregunta:
«¿exploró el médico lo familiar?» es una clase semántica abierta y una lista no
puede contestarla; «¿afirmó el paciente un fármaco?» es una clase cerrada de
cosas nombradas, donde la lista es precisa y sus fallos caen del lado seguro.

---

## Cobertura — V1 hecho, el resto no

`ahead_agent/coverage.py` + `cover.py` existen y corren. **3.2 cerrado**; 2.4
tiene código y le faltan datos; 2.6 sin empezar.

Lo que hace: verifica cada cita en tres comprobaciones separadas —literal, en el
turno declarado, en una línea del paciente—, cruza puntuación contra evidencia
verificada en cuatro estados, mide la dispersión agrupando por paciente, y marca
los turnos citados por varias dimensiones. Determinista, sin modelo, sin labels
y ciego a la verdad. `tools/make_dummy_batch.py` fabrica una tanda con la
respuesta conocida para ejercitarlo sin servidor.

**2.4 emite tres cosas desde el 2026-08-31**, y las tres salen en `cover.py` y
en `coverage.json`:

- `mean` y `sd` **por (paciente, dimensión)**. La media se da desde una sola
  puntuación; la sd solo a partir de `MIN_REPEATS`, y nunca un cero engañoso.
- `mean_within_patient_sd` — **la medida global de consistencia**: la media de
  las sd calculadas *dentro* de cada paciente. Promediar sd internas es lo que
  la mantiene siendo consistencia: agrupar antes las puntuaciones dejaría que la
  distancia *entre* pacientes la inflara, y eso es el número de 2.5, no el de 2.4.
- `within_patient_sd_by_dimension` — la mitad accionable: en qué dimensión el
  médico es menos estable.

Lo que falta, por orden de coste:

- **2.5 y 2.6** — unas pocas líneas cada una, esperando a que 2.4 dé número.
  Ojo con 2.5: `evaluate.py` la calcula sobre **pacientes distintos**, así que
  con menos de tres devuelve `None` (D12, arreglado el 2026-08-31).
- **ASKED** — decir si el médico preguntó exige un juicio sobre lenguaje: rúbrica
  por dimensión, un modelo juzgando con cita obligatoria, y un conjunto anotado a
  mano contra el que validarlo antes de dejarle decidir nada. **No está
  justificado por ahora**: la primera lectura sobre `e4-1` dice que casi todo lo
  que el médico puntúa lo puede citar, así que el problema no es la falta de
  fundamento. Sigue siendo lo único que cerraría 1.10.
- **Umbral sin fijar.** Falta declarar, *antes* de mirar la cifra, qué tasa de
  puntuaciones sin fundamento obligaría a construir ese juez. Sin declararlo
  antes, se racionaliza cualquier resultado.

### Si algún día se automatiza el juicio: NLI, no prompting

Restricción de método, no preferencia. Sale de **AttributionBench** (arXiv
2402.15089, en `papers/`), que convierte la evaluación de atribución en
clasificación binaria sobre siete datasets y mide de `roberta-large-mnli` a
GPT-4:

- GPT-4 zero-shot con CoT se queda en **73.3%** de macro-F1 y GPT-3.5 afinado en
  **~80%**. En preguntas de dominio especializado, **por debajo del 60%** — y un
  diálogo clínico es dominio especializado.
- **Los LLM grandes rinden por debajo de modelos NLI pequeños afinados.** FLAN-T5
  de 3B, y en algún conjunto el de 770M, superan a GPT-4. *"Simply switching
  stronger models cannot significantly improve the performance."*
- **La ingeniería de prompt no es la palanca.** Cuatro prompts cada vez más
  elaborados movieron el F1 de 73.2 a 74.0: lo que cambia es el reparto entre
  falsos positivos y negativos, no el acierto.
- **Añadir contexto empeora.** Meter la pregunta y la respuesta completas no
  mejoró y a veces perjudicó, porque el modelo acaba juzgando si la respuesta es
  útil en vez de si está sostenida.
- El **11.2%** de sus casos de error resultaron ser fallos de la etiqueta humana,
  no del modelo. Etiquetar un gold set mal es un riesgo medido, no teórico.

Consecuencias para el diseño, si se llega ahí:

1. **Separar dos tareas que no son la misma.** Decir *si se preguntó* es tipo
   checklist, y ahí el OSCE francés mide ICC 0.85. Decir *si una cita sostiene
   una dimensión* es atribución, y ahí el techo es ese 60-80%. No van
   encadenadas y no merecen la misma confianza.
2. Para la segunda, **un modelo NLI** —`t5_xxl_true_nli_mixture` es el que usan
   ALCE y este paper— y no el modelo del médico con un prompt cuidado.
3. **Entrada mínima**: la cita y la definición de la dimensión, sin el transcript
   alrededor.
4. No invertir tiempo en refinar el prompt esperando que suba el acierto.

`reproducibility.py` **se borró el 2026-08-27**: era un borrador de 211 líneas
sin tests, sin caller y sin revisar. Lo que 2.4 necesitaba se escribió dentro de
cobertura, desde cero.

---

## 1.10 — preguntas libres que cubran todas las dimensiones

Que el médico llegue a todas las dimensiones preguntando libremente, sin
recorrer un cuestionario. Si hay que guiarlo, vuelve a ser elicitación.

**El hueco ya está confirmado desde los datos**, no desde el documento: cobertura
lo leyó sobre `e4-1` y `general_overuse` sale NA en la mitad de las consultas.

Pero **sigue sin poder cerrarse**, y ahora se sabe exactamente por qué. Cobertura
V1 distingue puntuado de no puntuado y fundamentado de no fundamentado; lo que no
distingue es «no preguntó» de «preguntó y el paciente no contestó», porque eso no
está escrito en ninguna parte del transcript: hay que interpretar la pregunta.
Es lo que haría el juez, y hoy no está justificado construirlo.

Lo único que V1 aporta contra esto es una cota: los turnos citados por varias
dimensiones dicen que el médico cosecha varias dimensiones de la misma respuesta,
así que la mayoría **no** se sondearon una a una. Es un techo del sondeo, no una
medida de él.

---

## 4.6 — objetivos provisionales

Fijar qué error es aceptable, para poder declarar buena o mala una corrida.

Bloqueado por lo mismo que todo lo demás: con un ruido de 0.99 por dimensión no
hay contra qué comparar. Sale de cobertura, no antes.

---

## Orden justificación → score

Sospecha abierta desde el 2026-08-14, sin resolver. `DOCTOR.md` §5.3 pide una
justificación que cite frases del paciente, para dejar un rastro auditable. La
duda es si el modelo **elige primero el número y después busca la cita**, en
cuyo caso el rastro parece riguroso y es decorativo.

Lo que hay medido: las citas son reales (93-96% verificables), así que no hay
fabricación. El indicio en contra es de clasificación — en `run_01/CLL-001`,
`Timeline = 7` se justifica con *"waiting for a bomb to go off"*, que existe pero
expresa `Concern`. Cita real, dimensión equivocada. Es un indicio, no una
prueba: el orden de generación no se deduce del texto final.

**La herramienta ya existe y nunca ha corrido.** `ahead_agent/ablation.py` +
`rescore.py` (5.4, escritos el 2026-08-28): quitan del transcript las frases que
el propio médico citó y vuelven a puntuar en dos condiciones —`intact` y
`ablate`—, las dos leídas en frío. `intact` no es un experimento aparte sino el
**control**: el informe original lo escribió el médico continuando su consulta
(D9), y un lector en frío ve mucho menos, así que comparar `ablate` contra el
original mediría la ablación y la pérdida de contexto a la vez.

Si la puntuación no se mueve al quitar la evidencia, la evidencia era
decorativa. Cuesta dos llamadas por consulta y corre sobre una tanda ya escrita,
así que **es el experimento más barato que queda abierto**. Lo único que le
falta es haberse ejecutado una vez.

---

## Futuro, no ahora

**1.8 — definiciones externas como recurso.** Dar al médico las definiciones
clínicas de las dimensiones como recurso, en vez de llevarlas dentro del prompt.
La interfaz está hecha y `resources/` está vacío. Falta una decisión que no es
técnica: **inyectarlas en el prompt o que las recupere cuando las necesite.**
Aplazado a propósito.

---

## Cómo medir un cambio de conducta — la pregunta de fondo

Salió al intentar leer las puertas de §5.1 y aplica a cobertura igual.

Se escribió un lector de puertas y **se tiró el 2026-08-27**, porque descansaba
en proxies: buscar palabras sueltas mide vocabulario, no tema, y contar palabras
mide verbosidad, no amplitud. Un médico puede ser largo y estrictamente
biomédico; «¿y en casa, cómo lo llevan?» abre terreno familiar sin contener
ninguna palabra de una lista.

De las cuatro puertas, solo la de `stop_reason` no era un proxy, porque es un
dato y no una interpretación.

Esto no es un detalle de implementación: es el mismo problema que tiene 3.2
—decidir si el médico «sondeó» una dimensión— planteado sobre estilos en vez de
sobre dimensiones. **Mientras no esté resuelto, cualquier módulo de cobertura
hereda el problema.** Resolverlo probablemente pasa por etiquetar a mano una
muestra pequeña y contrastar contra ella cualquier instrumento automático, antes
de dejar que decida nada.

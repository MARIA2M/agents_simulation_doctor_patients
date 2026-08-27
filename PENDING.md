# Pendientes

Lo que queda abierto, con lo que hace falta antes de poder tocarlo. Corte del
2026-08-27. `TASKS.md` sigue siendo la lista completa por fases; esto es solo lo
que está vivo.

---

## La tanda que desbloquea todo lo demás

**Todo lo que queda abierto se atasca en el mismo sitio: no hay ninguna tanda
con tres repeticiones.** Sin eso 2.4 no da número, y sin 2.4 no hay 2.5, ni 2.6,
ni 4.6. Es un problema de datos, no de código.

Orden de ejecución, con los brazos de estilo que `skills/styles/README.md` dejó
fijados y sin lanzar:

```bash
git add -A && git commit -m "..."          # run_batch aborta con el árbol sucio
export OLLAMA_MODELS=/gpfs/projects/bsc02/llm_models/ollama && ollama serve &

# Cronometrar UNA antes de comprometerse a cuarenta
time ./venv-hpc/bin/python run_batch.py --profile style-narrowly_biomedical \
     --patients patients/CLL-001.json --repeats 1 --run-id timing-1

./venv-hpc/bin/python run_batch.py --profile style-narrowly_biomedical --repeats 2 --run-id s52-nb-1
./venv-hpc/bin/python run_batch.py --profile style-biopsychosocial     --repeats 2 --run-id s52-bps-1

./venv-hpc/bin/python cover.py    runs/s52-nb-1                                    # sin servidor
./venv-hpc/bin/python evaluate.py runs/s52-nb-1 --profile style-narrowly_biomedical
```

**Cobertura antes que evaluación**, porque 3.4 dice que un corpus no se analiza
hasta pasar 3.2, y un MAE sobre números sin fundamento no significa nada.

**Empezar por `--repeats 2` y subir a 3 después.** `run_batch.py` salta lo que ya
existe, así que relanzar con `--repeats 3` y **el mismo `--run-id`** añade solo
la tercera vuelta. Es la forma de tener 2.4 sin arriesgar una demo.

**Puerta D antes que nada** (`skills/styles/README.md`): que toda consulta cierre
con `stop_reason: doctor`. Si alguna se agota por `max_turns`, el estilo cambió
la regla de cierre y todo lo de abajo hereda el problema.

**No comparar contra `e4-1`**: es pre-styles, otro hash de prompt y otras bandas.
Los dos brazos se comparan entre sí.

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

Lo que falta, por orden de coste:

- **2.5 y 2.6** — unas pocas líneas cada una, esperando a que 2.4 dé número.
- **ASKED** — decir si el médico preguntó exige un juicio sobre lenguaje: rúbrica
  por dimensión, un modelo juzgando con cita obligatoria, y un conjunto anotado a
  mano contra el que validarlo antes de dejarle decidir nada. **No está
  justificado por ahora**: la primera lectura sobre `e4-1` dice que casi todo lo
  que el médico puntúa lo puede citar, así que el problema no es la falta de
  fundamento. Sigue siendo lo único que cerraría 1.10.
- **Umbral sin fijar.** Falta declarar, *antes* de mirar la cifra, qué tasa de
  puntuaciones sin fundamento obligaría a construir ese juez. Sin declararlo
  antes, se racionaliza cualquier resultado.

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

Diseño propuesto: un brazo que obligue a emitir cita textual y dimensión
**antes** del número, y comparar MAE contra el brazo actual. Es Fase 5, que está
entera sin empezar.

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

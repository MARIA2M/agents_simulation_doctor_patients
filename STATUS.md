# Estado

Qué hay hecho y qué nos hemos desviado del diseño.

- **Qué hay que hacer** → [PENDING.md](PENDING.md)
- **Qué es cada tarea** → [TASKS.md](TASKS.md)
- **De dónde salen los problemas heredados** → [INHERITED_ISSUES.md](INHERITED_ISSUES.md)

**Sin cifras a propósito.** Este documento dice en qué estado está cada cosa, no
cuánto mide. Las medidas viven en el `evaluation.json` de cada tanda, que es
donde se pueden volver a comprobar.

Leyenda: **✅** hecho · **◐** medido a mano, sin herramienta que lo reproduzca ·
**⚠️** a medias, con lo que falta al lado · **❌** sin empezar · **⛔** decidido
no hacerlo ahora.

---

## El suelo cambió el 2026-08-26

Casi nada anterior a esa fecha es comparable con lo de después:

- **El corpus** es el de CK. Ver 0.3 y D11.
- **Las bandas**: `concern` y `emotional_response` se separaron. La primera es
  la preocupación por lo que viene, la segunda el ánimo de ahora. Antes las dos
  pedían expresar inquietud y el médico no podía atribuir esa conducta a una ni
  a la otra.
- **El prompt del médico**, por segunda vez. Hay tres estados de hash, y
  `prompts/reference/DOCTOR_v1.md` es el intermedio.
- **`max_turns`** bajó.
- **Las corridas viejas** están en `runs/historic/`, con un README que explica
  por qué no sirven de línea base.

---

## Fase 0 — Base

| | | |
|---|---|---|
| 0.1 | Paquete nuevo | ✅ `agents_simulations/` |
| 0.2 | Git | ✅ |
| 0.3 | Mismos perfiles en los dos brazos | ⛔ retirada. `patients/` es el corpus de CK, así que los dos brazos ya no son comparables paciente a paciente — decisión, no deriva. En su lugar quedan dos tests: que `patients/` reproduce su origen en CK, y que el corpus anterior sigue congelado en `sintetic_patients/patients_version1/`, porque es contra ese que se puntuó `runs/historic/` |
| 0.4 | Provenance por corrida | ✅ `metadata.py`. `features` se añadió después de 0.5, así que las corridas anteriores no registran su brazo |
| 0.5 | Config común | ✅ herencia por `extends:`, encadenable, con ciclos y padre ausente detectados. Fusión bloque a bloque y validación sobre el resultado fundido. Un brazo de Fase 6 es ya un fichero de tres líneas |
| 0.6 | El corpus guarda los números originales | ✅ `patients/*.json` guarda la fracción tal como la escribió CK, entrecomillada porque no es un número JSON, y la escala se aplica al leer. `ahead_agent/corpus.py` es el cargador único por el que pasan `main.py`, `run_batch.py` y `evaluate.py` |

## Fase 1 — Arquitectura de agentes

| | | |
|---|---|---|
| 1.1 | Grafo con dos nodos de agente | ✅ y el punto de extensión ya se usó: `report` |
| 1.2 | Modelos distintos y aislamiento | ✅ con test: el perfil del paciente nunca llega al médico |
| 1.3 | Turnos no preestablecidos | ✅ |
| 1.4 | Secuencial y coherente | ✅ |
| 1.5 | Termina el médico | ✅ en `e4-1` ninguna consulta se agotó por el tope |
| 1.6 | Prompts en markdown externos | ✅ |
| 1.7 | Skills | ✅ compone y hashea. El test de §5.1 —dos skills opuestas dan transcripts distintos— pasó sobre un paciente. Sobre el corpus entero no se ha hecho |
| 1.8 | Definiciones externas como recurso | ⚠️ interfaz lista, `resources/` vacío. **Falta una decisión: inyectarlas o recuperarlas.** Aplazada a propósito |
| 1.9 | Perfiles de paciente | ✅ estructura intacta. `persona` retirado — ver D2 |
| 1.10 | Preguntas libres que cubran **todas** las dimensiones | ❌ **falla.** `general_overuse` queda NA en parte del corpus y con número en el resto, sin que se sepa si llegó a preguntarse. Lo hace visible cobertura |
| 1.11 | Puntuación al final | ✅ |
| 1.12 | Sondeo dirigido por ambigüedad | ⛔ sin mecanismo en la línea base, a propósito — D3 |
| 1.13 | Informe siempre, validado, con reintento | ✅ ejercitado de punta a punta, incluida la rendición al agotar los intentos. En vivo no se ha disparado nunca |
| 1.14 | Estilos de médico portados | ✅ ocho estilos más `good_doctor`, que es el que `DOCTOR.md` llevaba dentro en prosa. Al prompt cómo habla el médico, al registro las hipótesis y los marcadores. La sección de origen que decía qué dimensiones quedarían vacías se descartó, porque la leería el mismo agente que luego las puntúa |

## Fase 2 — Trazabilidad de la puntuación

| | | |
|---|---|---|
| 2.1 | Evidencia antes que número | ✅ en el esquema y en el prompt. El experimento que lo pondría a prueba es 5.4, sin hacer |
| 2.2 | Anclas intermedias | ✅ desde criterio clínico, sin invertir las bandas del paciente |
| 2.3 | Confianza declarada | ✅ se emite y se parsea. **No calibra** |
| 2.4 | Confianza empírica | ⚠️ **la herramienta está completa** en `coverage.py`: `mean` y `sd` por (paciente, dimensión), `mean_within_patient_sd` como medida global y el desglose por dimensión. No da número porque ninguna tanda tiene N≥**5** repeticiones —el suelo del código, no 3— y por debajo devuelve nulo en vez de un cero engañoso |
| 2.5 | Discriminación entre pacientes | ◐ ordena bien y comprime el rango. No es un scorer degenerado. **D12 arreglado el 2026-08-31**: la correlación agrupa por `patient_id` y exige 3 pacientes distintos, así que ya no cuenta cada repetición como una persona |
| 2.6 | Validar la confianza declarada contra la empírica | ❌ fuera del V1 de cobertura a propósito. La confianza se lee y se guarda, no se cruza con nada. Depende de que 2.4 dé número |

## Fase 3 — Integridad del corpus

| | | |
|---|---|---|
| 3.1 | Reintentos de transporte | ✅ y disparado en vivo, todos recuperados |
| 3.2 | Módulo de cobertura | ✅ **V1**: `ahead_agent/coverage.py` + `cover.py`, determinista, sin modelo y ciego a la verdad. Verifica cada cita en tres comprobaciones separadas —literal, turno declarado, línea del paciente—, cruza puntuación contra evidencia verificada en cuatro estados, y marca los turnos citados por varias dimensiones. **Lo que no hace es decir si el médico preguntó**: eso exige un juicio sobre lenguaje y queda fuera a propósito, así que 1.10 sigue sin cerrarse |
| 3.3 | Reproducibilidad | ⚠️ ver 2.4: el código está, faltan repeticiones |
| 3.4 | Puerta de corpus utilizable | ❌ **ya se puede escribir**, que era lo que faltaba: 3.2 existe, 3.5 existe y `batch.json` da `stop_reason` |
| 3.5 | Fidelidad del paciente | ✅ `ahead_agent/fidelity.py` + `fidel.py`, 2026-08-31. Determinista, sin modelo, y **lee `patients/*.json`** —lo contrario que cobertura, y por eso van en ficheros separados—. Dos severidades: contradicción contra el régimen o la edad, y mención no sostenida de fármaco o síntoma. No toca ninguna puntuación. **Su tasa es una cota superior, no una medida**: lee entidades nombradas, así que toda fuga cae del lado del aprobado |

## Fase 4 — Evaluación

| | | |
|---|---|---|
| 4.1 | Ground truth solo de `patients/*.json` | ✅ |
| 4.2 | Portar `evaluation.py` | ✅ la aritmética por dimensión va intacta. Nuevo: el NA como valor, la agregación entre pacientes y dos correlaciones con nombre distinto, `within_patient_r` y `between_patient_r` |
| 4.3 | Portar `causes/` | ⚠️ portado entero, y **sin correr nunca**: la evaluación de `e4-1` se hizo sin `--causes`. Nuevo respecto al original: el método usado queda registrado en el resultado, porque antes cambiaba de métrica en silencio al fallar los embeddings. Arrastra un umbral sin justificar y un `models.embed` inalcanzable en `hpc.yaml` |
| 4.4 | NA en vez de fallback | ✅ verificado, nunca recortado |
| 4.5 | Sesgo por dimensión | ✅ ya es herramienta, no script. Reproduce la forma del sesgo heredado, con `identity` bastante más inflado y `personal_control` cambiando de signo |
| 4.6 | Objetivos provisionales | ❌ sin vara con la que fijarlos. Sale de cobertura |
| 4.7 | `evaluate.py` | ✅ el punto de entrada que faltaba. Post-proceso puro —ni grafo ni servidor—, así que vale sobre tandas de cualquier brazo |

## Fases 5, 6 y 7

Casi enteras sin empezar, que es lo previsto. Los dos brazos de `coverage_hint`
existen y son material de la Etapa 8. Una excepción:

| | | |
|---|---|---|
| 5.4 | Tests de artefacto — ablación de evidencia | ⚠️ **escrito y sin correr nunca** (2026-08-28). `ahead_agent/ablation.py` + `rescore.py`: quitan las frases que el médico citó y repuntúan en dos condiciones, `intact` (el control, leído en frío) y `ablate`. Post-proceso sobre una tanda ya escrita, dos llamadas por consulta. Falta el transcript cruzado, que es la otra mitad de 5.4 |

---

## La tanda `e4-1`

Diez pacientes, dos repeticiones, `coverage_hint: off`. Todas las consultas
correctas y cerradas por el médico, todos los informes parseados a la primera,
y los únicos incidentes fueron reintentos de transporte recuperados.

**Es el primer corpus del proyecto sin huecos** — el brazo Ruby perdía una parte
importante de los turnos del paciente y de los informes.

**Cobertura corrió sobre ella el 2026-08-27** y es la primera lectura de 3.2
sobre datos reales. Las cifras están en su `coverage.json`, que es donde se
pueden volver a comprobar. Tres cosas que sí son estado y no medida:

- La tasa de citas verificadas **coincide con la que se había medido a mano**,
  así que dos métodos independientes dan lo mismo.
- **De 2.4 no sale nada**: `e4-1` tiene dos repeticiones y hacen falta tres.
- Verde en el mapa significa que la cita es real y está bien localizada, **no
  que sea de esa dimensión**. La clasificación errónea es invisible por
  construcción, y es lo que mediría E2. `general_overuse` sale NA en la mitad
  de las consultas, que hasta ahora solo constaba por el documento.

**Vive en `runs/historic/`**, cuyo README dice que nada de ahí es comparable con
lo posterior al 2026-08-26. O eso o esta sección está desactualizada: es la
contradicción de 8.11, aplazada a propósito. Hasta resolverla, toda cifra de
`e4-1` se reporta con la nota de que mide una configuración superada.

Lo que todavía **no** la hace utilizable era 3.5 —no sabíamos si el paciente
jugó su perfil—. Desde el 2026-08-31 hay herramienta (`fidel.py`) y **no se ha
pasado sobre `e4-1`**: la pregunta sigue sin respuesta, pero ya no por falta de
código. Ni 3.2 ni 3.5 están ya en la lista de lo que falta escribir.

---

## Desviaciones respecto a ARCHITECTURE.md

El paradigma sigue entero: bucle agéntico, paciente como herramienta,
aislamiento verificado, NA sin excepciones, evidencia antes que número.

### De fondo

**D1 — `run_batch.py`.** ✅ resuelto, con dos guardas que el diseño no pedía:
aborta con el árbol sucio y avisa si las dos temperaturas son cero.

**D2 — `persona` retirado del perfil.** El diseño lo pedía desde el principio
para que la Fase 7 no obligara a tocar el esquema después. Se quitó por decisión
explícita, así que 7.1 tendrá que reintroducirlo.

**D3 — `coverage_hint` por defecto en `off`.** Ya no es desviación: el diseño
está reescrito y describe ese brazo como la línea base. Hubo un tercer modo,
`declare`, retirado porque las propias declaraciones volvían en el historial y
el médico podía releerse: el brazo no aislaba lo que decía aislar.

**D9 — El médico escribe su propio informe.** Continúa la conversación que acaba
de tener, en vez del reporter aparte que el diseño listaba. Un modelo nuevo
leyendo el transcript en frío mediría otra cosa, y ese es justamente el brazo de
5.4. Consecuencia: 2.1 se verifica dentro del mismo contexto que formó la
impresión, así que la ablación de 5.4 es el único separador.

**D11 — El corpus es el de CK, y C1 cae con él.** El BMQ venía como suma cruda
sobre el máximo, que ni siquiera es JSON válido. No fue un cambio de formato:
varias dimensiones traen otro valor, y las dos `general_*` no coinciden en
ningún paciente. Con ello cae C1, porque CK puntúa las `specific_*` también en
los pacientes sin receta, y eso se aceptó a sabiendas. `INHERITED_ISSUES.md`
sigue describiendo C1 como vigente.

**D12 — `between_patient_r` contaba informes, no pacientes.** ✅ **Resuelto el
2026-08-31.** `evaluate_batch` construía un `PatientMetrics` por `report.json`,
así que en una tanda de 10 × 5 la correlación corría sobre 50 puntos con cada
persona contada cinco veces, y el ruido de una persona consigo misma se leía
como acuerdo entre personas.

Ahora `_per_patient_pairs` agrupa por `patient_id`, promedia las repeticiones de
cada paciente y deja **un punto por persona**; se aplica igual al número global
y a cada entrada de `by_dimension`, que arrastraba el mismo fallo. Y
`MIN_PATIENTS = 3`: por debajo devuelve `None`, porque **dos puntos siempre
correlacionan a ±1** y publicar ese 1.0 sería afirmar una discriminación que la
tanda no puede sostener.

Cómo se escondió: los tres tests que decían «tres pacientes» construían sus
informes con el mismo `patient_id`, `TEST-001`. Ahora usan ids distintos, y hay
un test que fija la diferencia — 0.866 agrupando bien contra 0.548 agrupando
informes.

**D13 — Un turno es un intercambio, no una intervención.** `nodes.py` da a la
pregunta del médico y a la respuesta del paciente **el mismo número**, porque la
unidad heredada del paradigma de tools es el par `function_call` /
`function_call_output`. Ruby no numeraba nada, así que no hay desviación
respecto a él; la numeración es del brazo Python y existe para 2.1 y 8.8.
Consecuencia: `Evidence.turn` **no identifica al hablante**, hay que cruzar
turno y rol. Costó un bug en cobertura, y afecta a 8.8, donde la cita llevaría
al intercambio y no a la frase del paciente. Sin decidir si se numeran líneas:
cambiarlo obliga a tocar `REPORT.md` y rompe la comparabilidad por hash.

### De forma

**D4** — La rúbrica pasa de markdown a JSON.
**D5** — `prompts/REPORT.md` es nuevo.
**D6** — Bloque `features` en los perfiles, obligatorio y validado.
**D7** — `report_raw.txt` solo cuando el informe no parsea.
**D8** — Falta `api_server.py`. Ver la sección del frontend.
**D10** — `ahead_agent/api/` está vacío, consecuencia de D9.

---

## El frontend, si se añadiera `api_server.py`

**No se reutiliza entero, y el motivo es de fondo: el frontend *es* el brazo de
elicitación.** `App.tsx` no muestra la consulta, la conduce — recorre las
preguntas por índice, decide si repreguntar según lo corta que sea la respuesta,
y llama al scorer pregunta a pregunta. El recorrido por lista y la regla de
repreguntar por longitud siguen vivos en React después de haberlos sacado de
Python.

| Parte | Reutilizable |
|---|---|
| `components/` presentacionales — burbujas, barras, pantallas, estilos | ✅ tal cual |
| `ReportScreen` y `CausesPanel` | ⚠️ el marco sirve; el contenido cambia, porque ahora cada dimensión trae evidencia, razonamiento y confianza, no un número suelto |
| `runner/config.ts` — el cuestionario y los umbrales | ❌ el cuestionario no vive en el cliente |
| `runner/api.ts` — los endpoints por pregunta | ❌ desaparecen |
| `App.tsx` — el bucle | ❌ se invierte: de conductor a espectador |

Así que el diseño se queda corto cuando dice que `App.tsx` será *"de adaptación,
no reescritura"*. Lo presentacional sí; el orquestador no se adapta, se
sustituye, porque el orquestador ahora es el grafo.

**Un hueco ya decidido.** El `POST /run` propuesto lanza una consulta entera:
minutos de reloj, que no caben en una petición que responde al final. Se hará
con streaming por turnos, y el informe llega como último evento. Sin barra de
progreso: la puntuación es una sola y al final, así que no hay nada que contar
mientras se conversa.

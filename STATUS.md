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
| 2.4 | Confianza empírica | ◐ medida a mano, sin herramienta. `reproducibility.py` se borró el 2026-08-27. **Pasa a cobertura** |
| 2.5 | Discriminación entre pacientes | ◐ ordena bien y comprime el rango. No es un scorer degenerado |
| 2.6 | Validar la confianza declarada contra la empírica | ❌ **pasa a cobertura** |

## Fase 3 — Integridad del corpus

| | | |
|---|---|---|
| 3.1 | Reintentos de transporte | ✅ y disparado en vivo, todos recuperados |
| 3.2 | Módulo de cobertura | ⚠️ la verificación de citas corrió como script suelto. Sin módulo. **Es el módulo que absorbe 2.4 y 2.6** |
| 3.3 | Reproducibilidad | ◐ ver 2.4. Sin herramienta |
| 3.4 | Puerta de corpus utilizable | ❌ |
| 3.5 | Fidelidad del paciente | ❌ tarea nueva, aún sin escribir en TASKS.md |

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

❌ enteras, que es lo previsto. Los dos brazos de `coverage_hint` existen y son
material de la Etapa 8.

---

## La tanda `e4-1`

Diez pacientes, dos repeticiones, `coverage_hint: off`. Todas las consultas
correctas y cerradas por el médico, todos los informes parseados a la primera,
y los únicos incidentes fueron reintentos de transporte recuperados.

**Es el primer corpus del proyecto sin huecos** — el brazo Ruby perdía una parte
importante de los turnos del paciente y de los informes.

Lo que todavía **no** lo hace utilizable es 3.2 y 3.5: no sabemos si el médico
preguntó por lo que puntuó, ni si el paciente jugó su perfil.

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

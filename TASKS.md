# AHEAD — Doctor/Patient simulation: qué es cada tarea

**Objetivo del proyecto.** Comprobar si un LLM clínico puede **inferir** creencias
sobre enfermedad (B-IPQ) y tratamiento (BMQ) a partir de una consulta natural,
usando el CSM de Leventhal y el NCF de Horne como lente teórica. El cuestionario
es la vara de medir, **no el guion**: no se administra psicométricamente.

**Decisión de arquitectura.** Reimplementar en Python/LangGraph el paradigma de
inferencia del brazo Ruby, con el control de ejecución y la capa de evaluación
del brazo Python.

- Ruby (`modified_versions/ruby_version`) — paradigma correcto (conversación
  libre, inferencia), ejecución frágil. Se conserva como referencia.
- Python (`python_version/ahead_agent-bmq-integration`) — paradigma equivocado
  (elicitación: administra las preguntas literalmente), pero su `evaluation.py`
  y su módulo `causes/` son agnósticos del paradigma y se portan.
- La capa de medición vieja de Ruby está retirada en `ruby_version/save/`.

---

## Cómo leer esto

Tres documentos, un trabajo cada uno. **Si buscas qué hacer ahora, no es este.**

| | |
|---|---|
| **TASKS.md** (aquí) | **qué es** cada tarea y por qué existe. Definiciones, sin estado |
| [STATUS.md](STATUS.md) | **en qué estado** está cada una |
| [PENDING.md](PENDING.md) | **qué hacer ahora**, en orden, y qué lo bloquea |

Aquí no hay casillas marcadas a propósito: el estado tiene un único sitio, y
duplicarlo es cómo se desincronizan. Las tareas cerradas se quedan en una línea
para que las abiertas se vean.

---

## Fase 0 — Base

**Cerradas:** 0.1 paquete nuevo · 0.2 git · 0.4 provenance por corrida ·
0.5 config común con herencia · 0.6 el corpus guarda los números originales.

**0.3 — Mismos perfiles en los dos brazos.** ⛔ Retirada: el corpus vivo pasó a
ser el de CK, así que los dos brazos ya no puntúan lo mismo y no hay nada que
verificar. La sustituyen dos exigencias, ambas en `test_corpus.py`: que
`patients/` sea reproducible desde `sintetic_patients/patientsCK/`, porque sin
eso el ground truth no tiene origen; y que el corpus anterior siga congelado en
`sintetic_patients/patients_version1/`, porque es contra ese que se puntuó todo
`runs/historic/`.

---

## Fase 1 — Arquitectura de agentes

**Cerradas:** 1.1 grafo de dos agentes · 1.2 modelos distintos y aislamiento ·
1.3 turnos no preestablecidos · 1.4 ejecución secuencial · 1.5 termina el médico
· 1.6 prompts en markdown externos · 1.7 mecanismo de skills · 1.9 perfiles de
paciente · 1.11 puntuación al final · 1.13 informe siempre, validado, con
reintento · 1.14 estilos de médico portados.

### 1.8 — Definiciones externas como recurso

CSM, NCF, dimensiones y terminología clínica disponibles al médico como recurso
de contexto, en vez de dentro del prompt.

**La decisión que falta no es técnica: inyectarlas siempre o recuperarlas cuando
hagan falta.** La interfaz está hecha y `resources/` está vacío. Aplazada a
propósito.

### 1.10 — Preguntas libres que cubran todas las dimensiones

El médico formula a su manera, desde las dimensiones, sin recitar los ítems. Y
tiene que llegar a **todas**, incluidas `general_harm`, `general_overuse` y
`causes`, que son las que se quedan fuera.

Hoy falla, y **no se puede cerrar sin cobertura**: cuando una dimensión sale NA
no hay forma de distinguir «no preguntó» de «preguntó y el paciente no
contestó».

### 1.12 — Sondeo dirigido por ambigüedad

⛔ **La línea base se queda sin mecanismo, y es deliberado.** Repreguntar cuando
la evidencia es insuficiente sería lo correcto —el routing viejo disparaba por
longitud de respuesta, así que una respuesta larga y vaga pasaba directa a
puntuación—, pero forzar cobertura en vivo devuelve el cuestionario que 1.3 sacó
del código e infla el resultado. El médico sondea lo que quiere y la cobertura
se audita después.

Lo que sí existe son dos interruptores independientes para medirlo como
intervención: `features.coverage_hint` (`off` | `show`) y
`features.working_notes`.

---

## Fase 2 — Trazabilidad de la puntuación

**Cerradas:** 2.1 evidencia antes que número · 2.2 anclas intermedias ·
2.3 confianza declarada.

Lo que 2.1 y 2.2 dejaron dicho y sigue vigente:

- El orden `cita textual → razonamiento → puntuación` **es también el
  experimento** que responde si el sesgo viene de justificar a posteriori. En
  Ruby la tabla era `Score | Rationale`, o sea justificación decorativa; el
  scorer de Python devolvía el número desnudo.
- La rúbrica del médico se escribió **desde criterio clínico, no invirtiendo la
  del paciente**. Copiarla reconstruiría el espejo que 5.5 existe para medir.

### 2.4 — Confianza empírica

Dispersión de la puntuación entre las N corridas del mismo paciente. No depende
de la introspección del modelo.

**Presupuesto de corridas:** N=10 para la línea base, que es la que se publica y
de la que sale esta métrica; N=5 para cribar intervenciones de la Fase 6,
subiendo a 10 solo la que se quede. Por debajo de N=5 la dispersión no significa
nada.

**Pasa a cobertura** (PENDING.md). `reproducibility.py` se borró.

### 2.5 — Discriminación entre pacientes

Varianza de la puntuación media *entre* pacientes, por dimensión.

**Obligatorio reportarla junto a 2.4**, porque dispersión baja no significa
buena inferencia: un scorer degenerado es máximamente consistente y
completamente inútil. Lectura conjunta: dispersión baja + discriminación alta =
inferencia real; dispersión baja + discriminación baja = prior degenerado
disfrazado.

### 2.6 — Validar la confianza declarada contra la empírica

¿Predice lo que el modelo dice saber la dispersión que se observa? Si no, el
modelo no sabe cuándo no sabe, **y eso es un resultado en sí mismo**. La
confianza declarada es objeto de estudio, no dato de entrada.

**Pasa a cobertura.** Depende de que 2.4 exista antes.

---

## Fase 3 — Integridad del corpus

**Cerrada:** 3.1 reintentos de transporte.

### 3.2 — Módulo de cobertura y calidad

Recorre cada transcript y marca por dimensión: ¿hubo sondeo?, ¿hubo respuesta?,
¿hubo evidencia citada? Salida, un mapa dimensión × paciente donde los huecos se
vean de un vistazo.

Es lo que hace visible 1.10, y **el módulo donde viven ahora 2.4 y 2.6**.

### 3.3 — Reproducibilidad

Mismo paciente y mismo prompt N veces, midiendo divergencia de conversaciones y
de puntuaciones. Es la fuente de 2.4, así que va dentro de lo mismo.

### 3.4 — Puerta de corpus utilizable

Un corpus solo se declara utilizable si pasa 3.1 y 3.2. **No analizar corpus con
huecos**: se confunden fallos de infraestructura con fallos de inferencia.

### 3.5 — Fidelidad del paciente

Auditar si el paciente jugó su perfil: contradicciones contra `disease_profile`,
sin modelo de por medio. Corre sobre una tanda existente, no necesita cola.

Hecho el 2026-08-31 (`ahead_agent/fidelity.py` + `fidel.py`). Dos cosas de
diseño que la tarea no decía y ahora forman parte de ella:

- **Va en su propio módulo porque lee la verdad.** `coverage.py` tiene prohibido
  abrir `patients/*.json` —es lo que impide que el mapa de 3.2 vea la respuesta—
  y fidelidad es exactamente una comprobación *contra* esa respuesta. Juntarlas
  contaminaría 3.2.
- **`belief_profile` no se lee, solo `disease_profile`.** Un paciente que expresa
  una creencia está actuando su perfil, que es su trabajo; comprobar creencias
  aquí penalizaría la conducta que toda la simulación existe para producir.

Lo que **no** entrega: una medida. Compara entidades nombradas —régimen,
fármaco, síntoma, edad—, no significado, así que su tasa es una **cota superior**
de la fidelidad. Toda fuga cae del lado del aprobado. Se usa para leer las
corridas que fallan, nunca para creerse las que pasan.

---

## Fase 4 — Evaluación

**Cerradas:** 4.1 ground truth solo de `patients/*.json` · 4.2 port de
`evaluation.py` · 4.4 NA en vez de fallback · 4.5 sesgo por dimensión ·
4.7 `evaluate.py`.

Lo que dejaron dicho y sigue vigente:

- **4.1** El error que se retiró fue comparar contra una corrida anterior
  etiquetada `reference`, que eran puntuaciones inferidas y no verdad. Eso mide
  deriva entre corridas, no exactitud.
- **4.4** Un NA nunca es un valor por defecto: se excluye del MAE y se reporta
  como cobertura. El scorer viejo metía un 5 cuando el JSON no parseaba, y esos
  valores inventados contaban como aciertos.
- **4.5** El sesgo es **por dimensión, no global**: carga sintomática inflada y
  control deflactado. Una corrección global empeoraría los ítems de control.
- **4.7** La evaluación es post-proceso y va aparte, para poder correr sobre
  tandas de cualquier brazo. `score_causes` se llama desde ahí y **nunca desde
  un nodo** — en el brazo original vivía dentro del grafo, o sea que quien
  puntuaba veía la verdad.

### 4.3 — Portar `causes/`

Portado entero y **sin correr nunca**. Dos cosas que hay que decidir al
ejercitarlo:

- **El umbral de 0.72 no está justificado en ninguna parte.** Aparece igual en
  las cuatro copias del código, sin experimento, sin conjunto de calibración y
  sin cita. `coverage_score` **es** la fracción de causas verdaderas que llegan
  a ese corte, así que la métrica descansa entera sobre una constante heredada
  sin explicar. No es incorrecta; es indefendible tal cual. **El barrido sale
  gratis**: en cuanto `--causes` corra una vez, las similitudes quedan guardadas
  y mover el corte no cuesta ni una llamada más. Sale un valor defendible o el
  hallazgo de que la cobertura es muy sensible al umbral, que también es
  resultado. El umbral y el modelo de embeddings van juntos, porque la
  distribución de cosenos cambia con el modelo.
- **`models.embed` ya no es el problema que decía este documento.** `hpc.yaml`
  fija `nomic-embed-text`, que está en el almacén de Ollama y este código sí
  alcanza. La descripción anterior —un modelo de HuggingFace inalcanzable— se
  quedó aquí después de que el perfil se arreglara, y se corrige el 2026-08-31.
  Lo que sigue sin existir es la **validación**: si algún día falta el modelo,
  «ausente» y «inalcanzable» seguirán saliendo igual y degradando la métrica a
  solapamiento de categorías en silencio, a mitad de tanda en vez de al cargar
  el perfil.

**Cuenta con el coste:** clasificar cada causa es una llamada al modelo, tanto
las inferidas como las del perfil. Por eso no se llama desde dentro de una
corrida, y conviene cachear la clasificación del ground truth, que es la misma
en todas las corridas del mismo paciente.

### 4.6 — Objetivos provisionales

Umbrales de MAE heredados del informe, **representados como referencia y no como
aprobado/suspenso**, hasta saber por 5.3 cuánto difieren dos expertos entre sí.
Si difieren más que el umbral, el umbral no es alcanzable y hay que
reformularlo.

Hoy tampoco hay vara: sale de cobertura.

---

## Fase 5 — Brazos de comparación

**Ninguno emite veredicto.** Se representan junto al brazo de inferencia como
líneas de referencia, para situar el resultado. Decidir si un número es bueno o
malo es prematuro y queda fuera de esta fase.

- **5.1 Suelo ciego** — puntuar viendo solo diagnóstico y demografía, sin
  conversación: lo que se acierta por priors clínicos.
- **5.2 Techo por elicitación** — el brazo Python preguntando directamente: lo
  que se recupera cuando el paciente lo dice explícitamente.
- **5.3 Referencia humana** — dos o tres clínicos puntuando los mismos
  transcripts. Dan cuánto es inferible de verdad y su acuerdo entre ellos, que
  es el techo realista de la tarea. Un subconjunto basta, y solo con el corpus
  ya limpio.
- **5.4 Tests de artefacto** — comprobar que el número viene de la conversación
  y no del montaje. Baratos: repuntúan corpus existente, sin corridas nuevas.
  **Transcript cruzado**, puntuar a un paciente con el transcript de otro; si el
  MAE no se degrada, no se está leyendo nada. **Ablación de evidencia**, quitar
  las citas que el propio médico alegó y repuntuar; si el número no se mueve, la
  evidencia era decorativa. Es el test directo de si la justificación es a
  posteriori.
- **5.5 Brazo sin claves conductuales** — `PATIENT.md` dice cómo expresar un
  score alto y `DOCTOR.md` dice qué escuchar: **la misma tabla en espejo**.
  Parte del acierto es descifrar un código que metimos en los dos prompts, no
  inferencia clínica. El control da al paciente solo el número y una descripción
  narrativa, y la diferencia mide el tamaño del artefacto.

---

## Fase 6 — Intervenciones sobre el agente

Una variable por corrida, con corrida completa entre medias. Solo después de 3.4
y de la Fase 4.

- **6.1** Efecto de 2.1 (evidencia antes que número) sobre el sesgo.
- **6.2** Efecto de 2.2 (anclas intermedias) sobre sesgo y perfiles medios.
- **6.3** Calibración por dimensión con few-shot, usando el sesgo de 4.5. Solo
  después de 6.1 y 6.2: si no, corriges números sin corregir el mecanismo.
- **6.4** Efecto de los dos interruptores de 1.12, **uno por corrida**.
  `coverage_hint: show` mide si enseñarle los huecos le hace preguntar por lo
  que en la línea base no toca; `working_notes: true`, el efecto de escribir
  conclusiones sobre la marcha. Ninguno es comparable con la línea base en
  exactitud: los dos adelantan trabajo al médico.
- **6.5** **Comparar los estilos entre sí.** La carga ya está hecha (1.14), así
  que lo que queda es la comparación. Las `hypotheses` del registro se heredan
  como preguntas, nunca como resultados: nadie ha corrido nada detrás de ellas.
- **6.6** **¿Revisa el médico?** Con `working_notes: true`, dos notas de la
  misma dimensión en turnos distintos son un cambio de opinión fechado. Toda la
  arquitectura del informe al final se apoya en que información tardía pueda
  corregir una impresión temprana, y **no hay ni una observación de que
  ocurra**. Si casi nunca revisa, 1.11 no está comprando lo que creemos.

---

## Fase 7 — Cierre

- **7.1 Ampliar el corpus** — perfiles intermedios y pacientes que ocultan
  emociones. Solo con el pipeline ya fiable.

  **Regla del suelo de las bandas.** Si un perfil nuevo trae un B-IPQ = 0 o un
  BMQ en el mínimo, la banda de suelo se añade **en el mismo commit** que el
  perfil. Hoy las bandas empiezan más arriba y `_band_for` devuelve la primera
  cuyo tope no se supera, así que un 0 se jugaría como un 2: el paciente actúa
  un 2, el médico infiere 2 correctamente, y la evaluación lo apunta como error.
  Sería un error fabricado por la tabla, justo el artefacto que mide 5.5. Choca
  además con la rúbrica del médico, que dice que un 0 es un hallazgo y necesita
  evidencia como cualquier otro número. No es problema activo —el corpus actual
  no tiene ningún 0— y por eso no se toca el texto ahora.

- **7.2 Reescribir la sección 6 del informe** con los resultados reales. En
  particular la parte que describe una sobreestimación global cuando lo que hay
  es asimetría por dimensión (4.5).

---

## Fase 8 — Interfaz: API y frontend

Independiente de las fases 5–7. La puerta de entrada es que el contrato del
informe esté estable, o sea al cerrar la Fase 4.

El frontend actual **no se adapta, se invierte**: hoy no muestra la consulta, la
conduce — recorre las preguntas por índice y decide repreguntar por longitud de
respuesta. Lo presentacional sí se porta.

- **8.1** **El aislamiento en la frontera HTTP.** Hoy el endpoint de paciente
  devuelve el perfil entero al navegador, el cliente lo reenvía en cada turno y
  lee las causas del ground truth para pasárselas al scorer. O sea: **el cliente
  tiene la verdad y se la enseña a quien puntúa.** El invariante está verificado
  dentro del proceso y no existe en la API. Va la primera porque condiciona
  todos los endpoints.
- **8.2** **Streaming por turnos.** Una consulta son varios minutos: una
  petición que responde al final deja la interfaz muda y la corta cualquier
  proxy. Decidido emitir cada turno según se produce, con el informe como último
  evento.
- **8.3** **`api_server.py`.** Desaparece la puntuación por intercambio; la
  sustituye un endpoint de informe. Nuevos: lanzar una corrida y consultar
  cobertura.
- **8.4** **Portar lo presentacional** — burbujas, barras, pantallas y estilos,
  que no saben del paradigma. Se copian tal cual.
- **8.5** **El cliente deja de conducir.** De orquestador a espectador: lanza la
  consulta y muestra los turnos según llegan. Quién pregunta, qué pregunta y
  cuándo para lo decide el médico dentro del grafo.
- **8.6** **Fuera el cuestionario del cliente.** Las listas de preguntas y los
  umbrales de repregunta no vuelven. El cliente no debe saber qué dimensiones
  existen ni cómo se puntúan.
- **8.7** **Fuera la barra de progreso.** Como la puntuación es una sola y al
  final, estaría a cero toda la consulta y saltaría al total de golpe. **No se
  sustituye por otra**: fingir progreso sugeriría un recorrido por dimensiones,
  que es justo lo que este brazo no hace.
- **8.8** **La pantalla de informe, para el contrato nuevo.** Cada dimensión
  trae evidencia con su turno, razonamiento, puntuación y confianza. **La cita
  tiene que poder llevarte al turno del que sale**: esa lectura es lo que hace
  útil 2.1, y es la revisión manual que 5.3 pedirá a los clínicos. Un NA se
  muestra como hueco, nunca como cero.
- **8.9** **Tests.** Que la respuesta del endpoint de paciente no contenga
  ningún valor de creencias — el invariante en la frontera HTTP. Que un NA
  viaje como nulo. Que en el cliente no quede ninguna lista de preguntas.
- **8.10** **La demo, dos vistas de la misma corrida.** Una muestra la
  conversación y nada más; la otra añade las notas apareciendo y revisándose
  turno a turno. Es un interruptor de **pantalla, no de experimento**: el médico
  se comporta igual, porque nunca ve la interfaz.

- **8.11** **Reconciliar qué tanda es la línea base.** `STATUS.md` trata `e4-1`
  como el corpus vivo —"el primer corpus del proyecto sin huecos"— mientras el
  README de `runs/historic/` la lista como superada, porque nada de esa carpeta
  es comparable con lo posterior al 2026-08-26. Las dos cosas no pueden ser
  ciertas a la vez. **Aplazado a propósito el 2026-08-27**: se resuelve cuando
  haya una tanda nueva contra la que decidir, no reescribiendo documentos ahora.
  Hasta entonces, toda cifra que salga de `e4-1` —incluida la cobertura de V1—
  va con la nota de que mide una configuración superada.

  Va aquí porque es trabajo de documentación y no bloquea nada, no porque tenga
  que ver con la API. Ojo al numerar: la **Fase 8** de este documento es la
  interfaz, mientras que la **Etapa 8** de `ARCHITECTURE.md` §8 son las
  intervenciones. No son lo mismo.

---

## Pendiente de decidir

- Si las definiciones externas se inyectan siempre o vía recuperación (1.8).
- Si el brazo de elicitación (5.2) se mantiene vivo o se congela como
  referencia.
- Recursos clínicos externos formales como referencia, más allá de 1.8.
  Aparcado para después de la demo de septiembre.
- **Cómo se mide un cambio de conducta sin proxies.** Ver PENDING.md: es lo que
  bloquea cobertura.

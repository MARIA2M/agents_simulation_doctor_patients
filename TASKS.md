# AHEAD — Doctor/Patient simulation: plan de trabajo

**Objetivo del proyecto.** Comprobar si un LLM clínico puede **inferir** creencias
sobre enfermedad (B-IPQ) y tratamiento (BMQ) a partir de una consulta natural,
usando el CSM de Leventhal y el NCF de Horne como lente teórica. El cuestionario
es la vara de medir, **no el guion**. No se administra psicométricamente.

**Decisión de arquitectura.** Reimplementar en Python/LangGraph el paradigma de
inferencia del brazo Ruby, incorporando el control de ejecución y la capa de
evaluación del brazo Python.

- Ruby (`modified_versions/ruby_version`) — paradigma correcto (conversación libre,
  inferencia), ejecución frágil. Se conserva como referencia.
- Python actual (`python_version/ahead_agent-bmq-integration`) — paradigma
  equivocado (elicitación: administra las preguntas literalmente), pero su
  `evaluation.py` y su módulo `causes/` son agnósticos del paradigma y se portan.
- La capa de medición vieja de Ruby está retirada en
  `modified_versions/ruby_version/save/` — no se toca ni se analiza.

---

## Fase 0 — Base

- [ ] **0.1** Crear el paquete nuevo en `python_version/` a partir de
      `ahead_agent-bmq-integration`, que es la copia más reciente y completa
      (23 módulos, BMQ integrado). Mover `ahead_agent` y
      `ahead_agent-eval-ground-truth` a `save/`.
- [ ] **0.2** Poner el proyecto bajo git. El método es "una variable por corrida";
      sin historial no se puede atribuir ningún efecto a ningún cambio.
- [ ] **0.3** Verificar que los `patients/*.json` de ambos brazos son los mismos
      10 perfiles, para que los resultados sean comparables.
- [ ] **0.4** Metadatos de provenance por corrida: modelo, temperatura, endpoint,
      seed, hash del prompt. Gepeto aplica 0.7 por defecto si no se envía
      temperatura, y es estocástico donde el local es determinista.
- [ ] **0.5** **`config/base.yaml`: lo común, una sola vez.** Hoy `local.yaml` y
      `hpc.yaml` son casi el mismo fichero. Ignorando comentarios solo difieren en
      tres cosas — `models.doctor`, `models.embed` y `server.keep_alive`; hasta
      `models.patient` coincide. Todo lo demás está duplicado: las tres
      temperaturas, `seed`, `context_length`, `num_parallel`, `ollama_url`,
      `request_timeout`, `max_turns`, `report_attempts`, `features`, `prompts`,
      `skills`, `resources` y `paths`.
      Ya ha derivado dos veces: `hpc.yaml` se quedó sin las líneas de §5.1 que
      sí tenía `local.yaml`, y el renombrado a `report_attempts` hubo que
      aplicarlo a mano en los dos. El siguiente cambio de `max_turns` es una
      moneda al aire.
      **Propuesta.** `base.yaml` con todo lo compartido; los perfiles se quedan
      en `profile:` más sus tres diferencias, unas 8 líneas cada uno.
      `load_config` funde base bajo el perfil **bloque a bloque** —una fusión
      superficial borraría un bloque entero en vez de completarlo, que es el
      mismo fallo que tenía `make_run_profile`— y valida el resultado ya fundido,
      así que `REQUIRED` sigue cogiendo lo que falte.
      **La provenance no se toca:** `build_metadata` copia del diccionario ya
      resuelto, así que `metadata.json` sigue guardando los valores finales y una
      corrida se sigue interpretando desde un solo fichero.
      **Lo que hay que tocar además del código:**
      - **ARCHITECTURE §6** dice «el perfil es *un* fichero de config» y «el
        perfil elegido se copia íntegro a `run_meta`». Las dos frases dejan de
        ser exactas y hay que reescribirlas como base + diferencias.
      - **`test_the_profiles_on_disk_compose`** recorre
        `RUN_PROFILES_DIR.glob("*.yaml")` y hace `load_config(path.stem)` de cada
        uno. Con `base.yaml` ahí dentro intentaría cargarlo como perfil, y no
        tiene clave `profile:`. Hay que excluirlo del glob o sacar el fichero de
        `config/`.
      **El coste, que es real:** el método es una variable por corrida, y hoy
      abres `hpc.yaml` y ves todo lo que corrió. Con herencia ves tres líneas y
      tienes que abrir un segundo fichero. Lo cubre `metadata.json`, que guarda
      el resultado fundido y al que RUN.md ya manda mirar, pero es un cambio, no
      una mejora gratis.

---

## Fase 1 — Arquitectura de agentes

### Estructura

- [ ] **1.1** Grafo LangGraph con **dos nodos de agente**: paciente y médico.
      Sin scorer por ahora. Dejar el punto de extensión para añadirlo después.
- [ ] **1.2** **Modelos distintos** para paciente y médico. Test explícito de
      aislamiento: verificar que el perfil del paciente nunca entra en el
      contexto del médico. El riesgo real es la fuga de contexto, no los pesos.
- [ ] **1.3** **Turnos no preestablecidos.** Cada agente interviene cuando lo
      considera; nada de rondas fijas ni de un recorrido por lista de preguntas.
- [ ] **1.4** Ejecución **secuencial y coherente**, no asíncrona: cada turno ve
      el estado completo del anterior.
- [ ] **1.5** **Terminación decidida por el médico.** El médico cierra la consulta
      cuando considera que ha cubierto lo que necesita; el paciente no la termina.
      Tope máximo de turnos solo como red de seguridad, no como criterio.

### Prompts y contexto

- [ ] **1.6** Prompts en **ficheros markdown externos**, versionados y editables
      sin tocar código (equivalente a `DOCTOR.md` / `PATIENT.md`).
- [ ] **1.7** **Skills** en markdown que el agente pueda cargar según la fase de
      la consulta, en vez de un único prompt monolítico.
- [ ] **1.8** **Definiciones externas** como recurso de contexto: CSM, NCF,
      dimensiones, terminología clínica. Pendiente decidir si se inyectan siempre
      o vía recuperación.
- [ ] **1.9** **Perfiles de paciente** con la estructura actual: perfil clínico
      (diagnóstico, estadio, tratamiento, síntomas, laboratorio, demografía) +
      `belief_profile` con B-IPQ, BMQ y causas como ground truth.

### Inferencia

- [ ] **1.10** **Preguntas libres.** El médico formula a su manera, basándose en
      las dimensiones, sin recitar los ítems. Debe cubrir **todas** las
      dimensiones, incluidas `general_harm`, `general_overuse` y `causes`.
- [ ] **1.11** **Puntuación al final** de la consulta, no turno a turno, para que
      información tardía pueda revisar una impresión temprana.
- [ ] **1.12** **Sondeo dirigido por ambigüedad.** Repreguntar cuando la evidencia
      es insuficiente, no cuando la respuesta es corta. El routing viejo de
      Python disparaba con `len(respuesta) < 10 palabras`, así que una respuesta
      larga y vaga pasaba directa a puntuación. Es el punto 6.2.5 del informe.
      **Decidido al cerrar la Etapa 3 (§4.1): la línea base se queda sin
      mecanismo.** Forzar cobertura en vivo devuelve el cuestionario que 1.3
      sacó del código e infla el resultado, así que el médico sondea lo que
      quiere y la cobertura se audita después con 3.2. Lo que sí existe son dos
      interruptores, independientes entre sí, para medirlo como intervención:
      `features.coverage_hint` (`off` | `show`) y `features.working_notes`.

- [ ] **1.13** **Informe siempre.** Nodo propio con prompt propio, validación de
      que contiene las dimensiones completas, y reintento si falta algo. En Ruby
      el disparador era una frase suelta y el resultado se guardaba sin validar:
      así se perdió el informe de CLL-004.

---

## Fase 2 — Trazabilidad de la puntuación

- [ ] **2.1** **Evidencia antes que número.** Estructura obligatoria por
      dimensión: `cita textual del transcript → razonamiento → puntuación`, en
      ese orden. En Ruby la tabla era `Score | Rationale`, así que la
      justificación era decorativa; el scorer de Python devuelve el número
      desnudo, sin justificación alguna. Este orden es también el experimento que
      responde si el sesgo viene de justificar a posteriori.
- [ ] **2.2** **Anclas intermedias** en la escala. Rúbrica con descriptores en
      2/4/6/8 por dimensión, no solo los extremos. Anclar solo `0 = nada` y
      `10 = severamente` es la causa mecánica del sesgo: cualquier evidencia
      empuja al extremo. Afecta igual a B-IPQ (0–10) y BMQ (1–5).
      **Escribirla desde criterios clínicos, no invirtiendo la del paciente.**
      `patient_profile.py` ya tiene bandas ≤2/≤4/≤6/≤8/resto con descriptor
      conductual por dimensión, pero copiarlas al médico reconstruye el espejo
      de Ruby (ver 5.5). Que existan las dos sin ser la misma tabla es el
      objetivo. Nota: la asimetría actual de Python — paciente con 5 bandas,
      scorer con solo dos anclas — es probablemente fuente de sesgo por sí sola.
- [ ] **2.3** **Confianza declarada** por dimensión, emitida junto al score.
- [ ] **2.4** **Confianza empírica** = dispersión de la puntuación entre las N
      corridas del mismo paciente. No depende de la introspección del modelo.
      Presupuesto de corridas: **N=10 para la línea base** (es la que se publica
      y de la que sale esta métrica), **N=5 para cribar** intervenciones de la
      fase 6, subiendo a 10 solo la que se quede. Por debajo de N=5 la dispersión
      no significa nada.
- [ ] **2.5** **Discriminación entre pacientes** = varianza de la puntuación media
      *entre* los 10 pacientes, por dimensión. **Obligatorio reportarla junto a
      2.4**: dispersión baja NO significa buena inferencia. Un scorer degenerado
      es máximamente consistente y completamente inútil — llama3.2 puso ochos el 67% de las
      veces y habría salido con confianza empírica perfecta. Lectura conjunta:
      dispersión baja + discriminación alta = inferencia real; dispersión baja +
      discriminación baja = prior degenerado disfrazado.
- [ ] **2.6** **Validar 2.3 contra 2.4.** ¿Predice la confianza declarada la
      dispersión observada? Si no, el modelo no sabe cuándo no sabe — y eso es un
      resultado en sí mismo. La confianza declarada es objeto de estudio, no dato
      de entrada.

---

## Fase 3 — Integridad del corpus

- [ ] **3.1** **Reintentos a nivel de transporte** para turnos vacíos y llamadas
      caídas. Distinto de 1.13: el informe se valida al final, los turnos hay que
      reintentarlos en el momento. Corpus previo: ~19% turnos vacíos, ~26%
      informes fallidos.
- [ ] **3.2** **Módulo de cobertura y calidad** — unifica el "qué falta o es
      erróneo" con la checklist de sondeo. Recorre cada transcript y marca por
      dimensión: ¿hubo sondeo? ¿hubo respuesta? ¿hubo evidencia citada?
      Salida: mapa de calor dimensión × paciente donde los huecos se ven de un
      vistazo. Al volver a inferencia, los problemas de `general_harm`,
      `general_overuse` y `causes` reaparecen; este módulo es lo que los detecta.
- [ ] **3.3** **Módulo de reproducibilidad**: mismo paciente y mismo prompt N
      veces, medir divergencia de conversaciones y de puntuaciones. Es también
      la fuente de 2.4.
- [ ] **3.4** Un corpus solo se declara utilizable si pasa 3.1–3.2. No analizar
      corpus con huecos: se confunden fallos de infraestructura con fallos de
      inferencia.

---

## Fase 4 — Evaluación

- [ ] **4.1** **Ground truth = `patients/*.json`**, campo `belief_profile`, y
      nada más. Restricción explícita del diseño. El error que retiramos fue
      comparar contra una corrida anterior etiquetada `reference`, que eran
      puntuaciones inferidas, no verdad: eso mide deriva entre corridas, no
      exactitud.
- [ ] **4.2** Portar `evaluation.py`: MAE, mediana del error absoluto, sesgo por
      dimensión, Pearson, bandas `within_1`/`within_2` (B-IPQ) y
      `within_half`/`within_one` (BMQ).
- [ ] **4.3** Portar el módulo `causes/`: embeddings, similitud coseno,
      emparejamiento greedy contra taxonomía, `coverage_score` y
      `mean_similarity`. `causes` es abierto y no entra en el MAE.
      Nada de limpieza de texto con regex improvisado — el parser viejo borraba
      toda `b` y `r` del texto ("Stress" → "St ess").
- [ ] **4.4** **NA en vez de fallback.** Cuando no se puede extraer una puntuación
      (JSON ilegible, dimensión no sondeada, informe incompleto), el valor es
      **NA**: se registra como ausente, se excluye del MAE y se reporta aparte
      como tasa de cobertura. Nunca un valor por defecto. El scorer de Python
      metía un 5 (o 3.0 en BMQ) cuando el JSON no parseaba, y si eso fallaba
      cogía el primer número del texto — valores inventados que luego contaban
      como aciertos. NA propaga a 3.2: un NA es un hueco del mapa de cobertura.
- [ ] **4.5** **Sesgo por dimensión, no global.** El sesgo agregado B-IPQ era
      +0.13 (ruido), pero por ítem hay asimetría: carga sintomática inflada
      (`identity` +1.00, `consequences` +0.97) y control deflactado
      (`treatment_control` −0.77, `personal_control` −0.63). Una corrección
      global empeoraría los ítems de control.
- [ ] **4.7** **`evaluate.py` — el punto de entrada que falta.** `evaluation.py` y
      `causes/` están portados y probados, pero **no los importa nada en
      producción**: solo los ejecuta la suite. Por eso 4.3 sigue sin correr sobre
      `e4-1` — no falta código, falta el comando. Recorre
      `runs/<tanda>/*/report.json`, lee el ground truth de `patients/*.json` y de
      ningún otro sitio (4.1), y deja `evaluation.json` junto a la tanda.
      Registra el método de causas (`embeddings` o `categories`) que
      `score_causes` ya devuelve, y no imputa nunca un NA (4.4).
      **Cuenta con el coste:** `causes/scorer.py::_classify` manda cada causa
      por `llm.chat` con el modelo del médico a temperatura 0 —correcto para que
      sea determinista—, y clasifica tanto las inferidas como las del perfil.
      Sobre una tanda de 10 pacientes son del orden de **60 llamadas extra** al
      modelo. No es motivo para cambiarlo, pero sí para no llamarlo desde dentro
      de una corrida y para cachear la clasificación del ground truth, que es la
      misma en todas las corridas del mismo paciente.
      **Cómo lo cableaba el brazo original, y por qué no se copia:**
      - Su `main.py` evaluaba **en línea al acabar la consulta**, así que el
        ground truth se cargaba durante la corrida. Aquí la evaluación es
        post-proceso y va aparte, para poder correr sobre tandas de cualquier
        brazo, incluido el de elicitación (invariante 5 de §9).
      - Las causas se puntuaban **dentro del grafo**: `causes_score` vivía en el
        estado, salía del `scorer_node` y recibía `ground_truth_causes` como
        parámetro. Es exactamente lo que denuncia 8.1 —quien puntúa veía la
        verdad—, así que `score_causes` se llama desde `evaluate.py` y nunca
        desde un nodo.
      - `api_server.py` exponía `POST /evaluate`. Cuando llegue la Fase 8, ese
        endpoint llama a este módulo; no al revés.
- [ ] **4.6** Objetivos **provisionales**: MAE < 1.0 en B-IPQ y MAE < 0.5 en BMQ,
      heredados del informe. No se usan como aprobado/suspenso todavía: se
      representan como referencia hasta saber, por 5.3, cuánto difieren dos
      expertos entre sí. Si difieren más que el umbral, el umbral no es
      alcanzable y hay que reformularlo.

---

## Fase 5 — Brazos de comparación

Estos brazos **no emiten veredicto**. Se calculan y se representan junto al brazo
de inferencia como líneas de referencia, para poder situar el resultado. Decidir
si un número es bueno o malo es prematuro y queda fuera de esta fase.

- [ ] **5.1** **Suelo ciego.** Puntuar viendo solo diagnóstico y demografía, sin
      conversación: lo que se acierta por priors clínicos. Se representa como
      línea inferior en las gráficas, sin criterio de aprobado.
- [ ] **5.2** **Techo por elicitación.** El brazo Python actual, preguntando
      directamente: lo que se recupera cuando el paciente lo dice explícitamente.
      Se representa como línea superior. No compite con el brazo de inferencia.
- [ ] **5.3** **Referencia humana.** Dos o tres clínicos puntuando los mismos
      transcripts. Dan cuánto es inferible de verdad y su acuerdo entre ellos,
      que es el techo realista de la tarea. Reservar para un subconjunto (p.ej.
      3 dimensiones × 10 pacientes) y solo con el corpus ya limpio.
- [ ] **5.4** **Tests de artefacto.** Comprobar que el número viene de la
      conversación y no del montaje. Los dos son baratos y no requieren corridas
      nuevas, solo repuntuar corpus existente:
      - **Transcript cruzado**: puntuar al paciente A con el transcript del
        paciente B. Si el MAE no se degrada, no se está leyendo nada.
      - **Ablación de evidencia**: quitar del transcript las citas que el propio
        médico alegó y repuntuar. Si el número no se mueve, la evidencia era
        decorativa. Es el test directo de si la justificación es a posteriori,
        y complementa a 2.1.
- [ ] **5.5** **Brazo sin claves conductuales.** `PATIENT.md` le dice al paciente
      cómo expresar un score alto y `DOCTOR.md` le dice al médico qué escuchar —
      son la misma tabla en espejo. Parte del acierto es descifrar un código que
      metimos en ambos prompts, no inferencia clínica, y eso infla el techo.
      Brazo de control: el paciente recibe solo el número y una descripción
      narrativa, sin las claves que el médico también tiene. La diferencia mide
      el tamaño del artefacto.

---

## Fase 6 — Intervenciones sobre el agente

Una variable por corrida, con corrida completa entre medias. Si no, no se sabe
cuál funcionó. Solo tras tener 3.4 y 4.x.

- [ ] **6.1** Efecto de 2.1 (evidencia antes que número) sobre el sesgo.
- [ ] **6.2** Efecto de 2.2 (anclas intermedias) sobre sesgo y perfiles medios.
- [ ] **6.3** Calibración por dimensión con few-shot, usando el sesgo por ítem
      de 4.5. Solo después de 6.1 y 6.2 — si no, corriges números sin corregir
      el mecanismo.
- [ ] **6.4** Efecto de los dos interruptores de 1.12 sobre cobertura y perfiles
      medios, **uno por corrida**. `coverage_hint: show` mide si enseñarle los
      huecos le hace preguntar por `causes`, `general_harm` y `general_overuse`,
      que en la línea base no toca. `working_notes: true` mide el efecto de
      escribir conclusiones sobre la marcha. Ninguno de los dos es comparable
      con la línea base en exactitud: los dos adelantan trabajo al médico.
- [ ] **6.6** **¿Revisa el médico?** Con `working_notes: true`, dos notas de la
      misma dimensión en turnos distintos son un cambio de opinión fechado.
      Medir cuántas revisiones hay por consulta, en qué turnos, y si el informe
      final se queda con la primera nota o con la última. Toda la arquitectura
      del informe al final se apoya en que información tardía pueda corregir una
      impresión temprana (1.11) y **no hay ni una observación de que ocurra**.
      Si resulta que casi nunca revisa, 1.11 no está comprando lo que creemos.
- [ ] **6.5** **Estilos de comunicación como skills.** Cada estilo de médico es un
      fichero markdown que se carga con el mecanismo de 1.7, no una rama de
      código. La tarea es implementar la carga; comparar estilos entre sí queda
      para cuando exista.

---

## Fase 7 — Cierre

- [ ] **7.1** Ampliar el corpus: perfiles intermedios y pacientes que ocultan
      emociones. Solo con el pipeline ya fiable.

      **Regla del suelo de las bandas.** Si un perfil nuevo trae un B-IPQ = 0 o
      un BMQ ≤ 1.0, **la banda de suelo correspondiente se añade en el mismo
      commit** que el perfil. Hoy `patient_profile.py` empieza en `(2, …)` y
      `(2.0, …)`, y `_band_for` devuelve la primera banda cuyo tope no se supera,
      así que un 0 se juega como un 2: el paciente actúa un 2, el médico infiere
      2 correctamente, y `evaluation.py` lo apunta como error de 2. Sería un
      error fabricado por la tabla, no por la inferencia — justo el artefacto
      que mide 5.5.
      Choca además con la rúbrica del médico, que dice explícitamente «a 0 is a
      finding, and it needs evidence like any other number»: se le pide
      distinguir un 0 que el paciente no sabe representar.
      No es problema activo: el corpus actual no tiene ningún 0 —el mínimo
      B-IPQ es un solo 1— y ningún BMQ baja de 1.8. Por eso **no se toca el
      texto de las bandas ahora** (las intervenciones sobre prompts son la
      Etapa 8, y con ruido de 0.99 por dimensión no se mediría).
      Añadir `(0, …)` delante de `(2, …)` es gratis cuando toque: el 1 y los 2
      siguen cayendo en la banda de `(2, …)`, así que solo se dispara con un 0
      de verdad. Cambia el hash `patient_bands`, que es correcto — es un cambio
      de prompt.
- [ ] **7.2** Reescribir la sección 6 del informe con los números reales. En
      particular 6.2.1, que describe una sobreestimación global cuando lo que hay
      es asimetría por dimensión (ver 4.5).

---

## Fase 8 — Interfaz: API y frontend

Corresponde a **ARCHITECTURE §7**, que hasta ahora no tenía tareas numeradas.
Independiente de las fases 5–7. La puerta de entrada es que el contrato del
informe esté estable, que es al cerrar la Fase 4.

El frontend actual (`python_version/…/bipq_frontend`, ~1.150 líneas) **no se
adapta, se invierte**: hoy no muestra la consulta, la conduce. Su
`runConversation(qi, followUps, …)` recorre `BIPQ_QUESTIONS` por índice y decide
repreguntar con `pm.split(" ").length < SHORT_RESPONSE_THRESHOLD`. Es decir, P2
y P3 siguen vivos en React después de haberlos sacado de Python. Lo
presentacional sí se porta.

- [ ] **8.1** **El aislamiento en la frontera HTTP.** Hoy `GET /patients/{id}`
      devuelve el perfil entero al navegador, `callPatient` lo reenvía al
      servidor en cada turno, y `App.tsx` lee `belief_profile.b_ipq.causes` para
      pasárselo al scorer en `callScorer`. O sea: **el cliente tiene el ground
      truth y se lo enseña a quien puntúa.** El invariante de §3.1 está
      verificado dentro del proceso y no existe en la API. `GET /patients/{id}`
      debe devolver solo `disease_profile`; la verdad se queda en el servidor,
      que ya la lee de `patients/*.json` y de ningún otro sitio (4.1). Va la
      primera porque condiciona todos los endpoints.
- [ ] **8.2** **`POST /run` emite los turnos según se producen.** Una consulta
      son 7–15 turnos y varios minutos: una petición que responde al final deja
      la interfaz muda todo ese rato y la corta cualquier proxy por medio.
      **Decidido: streaming por turnos**, no identificador de corrida que se
      sondea. Encaja con que el grafo produzca los turnos secuencialmente, y es
      lo que da la conversación en directo. Consecuencias: `api_server.py`
      emite conforme avanza en vez de acumular, y el cliente mantiene la
      conexión abierta en vez de un temporizador. El informe llega como último
      evento del mismo flujo.
- [ ] **8.3** **`api_server.py`.** Conservar `GET /patients`,
      `GET /patients/{id}`, `POST /transcript` y `GET /health`. `POST /score` y
      `POST /bmq/score` **desaparecen**: no hay puntuación por intercambio
      (1.11). Los sustituye `POST /report`. Nuevos: `POST /run` y
      `GET /coverage/{run_id}`. Modelos Pydantic con el mismo estilo que los
      actuales.
- [ ] **8.4** **Portar lo presentacional.** `MessageBubble`, `ThinkingDots`,
      `ScoreBar`, `SetupScreen` y `styles/global.css` — unas 300 líneas que no
      saben del paradigma. Se copian tal cual, y se conserva el estilo del
      original: componentes funcionales, props tipadas, uno por fichero.
- [ ] **8.5** **`App.tsx` deja de conducir.** Pasa de orquestador a espectador:
      lanza la consulta y muestra los turnos según llegan. Quién pregunta, qué
      pregunta y cuándo para lo decide el médico dentro del grafo (1.3, 1.5).
      Desaparecen `qIndex`, `followUps` y el recorrido recursivo.
- [ ] **8.6** **Retirar `config.ts` del cliente.** Las 119 líneas con
      `BIPQ_QUESTIONS`, `BMQ_QUESTIONS`, `MAX_FOLLOW_UPS` y
      `SHORT_RESPONSE_THRESHOLD` no vuelven. El cliente no debe saber qué
      dimensiones existen ni cómo se puntúan; lo que necesite para pintar viene
      del servidor.
- [ ] **8.7** **Fuera el `ProgressPanel`.** Hoy muestra «3 / 9 scored» contra
      `BIPQ_QUESTIONS.length`. Como la puntuación es una sola y al final (1.11),
      ese contador estaría a 0/12 toda la consulta y saltaría a 12/12 de golpe.
      **No se sustituye por otra barra**: no hay nada que contar mientras se
      conversa, y fingir progreso sugeriría un recorrido por dimensiones que es
      justo lo que este brazo no hace. `InterviewScreen` se queda con la
      conversación y con `ThinkingDots`, que ya indica quién está hablando y se
      porta tal cual.
- [ ] **8.8** **`ReportScreen` para el contrato nuevo.** Cada dimensión trae
      evidencia con su turno, razonamiento, puntuación y confianza declarada. La
      cita tiene que poder llevarte al turno del que sale: esa lectura es lo que
      hace útil 2.1, y es también la revisión manual que 5.3 pedirá a los
      clínicos. Un NA se muestra como hueco, nunca como cero (4.4).
- [ ] **8.9** **Tests.** Que la respuesta de `GET /patients/{id}` no contenga
      ningún valor de `belief_profile` — es el invariante 1 en la frontera HTTP.
      Que `POST /report` devuelva NA como `null`. Que en el cliente no quede
      ninguna lista de preguntas ni ningún umbral de repregunta.
- [ ] **8.10** **La demo, dos vistas de la misma corrida.** Con
      `working_notes: true`, una vista muestra la conversación y nada más, y la
      otra añade las notas apareciendo y revisándose turno a turno. Es un
      interruptor de **pantalla**, no de experimento: el médico se comporta
      igual se muestre o no, porque nunca ve la interfaz.

---

## Pendiente de decidir

- Recursos clínicos externos formales como referencia (más allá de 1.8) — el PI
  tiene experiencia previa; aparcado para después de la demo de septiembre.
- Si las definiciones externas se inyectan siempre o vía recuperación.
- Si el brazo de elicitación (5.2) se mantiene vivo o se congela como referencia.

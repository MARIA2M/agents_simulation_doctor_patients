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
      es insuficiente, no cuando la respuesta es corta. El routing actual de
      Python dispara con `len(respuesta) < 10 palabras`, así que una respuesta
      larga y vaga pasa directa a puntuación. Es el punto 6.2.5 del informe.
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
- [ ] **6.4** Efecto de 1.12 (sondeo por ambigüedad) sobre los perfiles medios.
- [ ] **6.5** **Estilos de comunicación como skills.** Cada estilo de médico es un
      fichero markdown que se carga con el mecanismo de 1.7, no una rama de
      código. La tarea es implementar la carga; comparar estilos entre sí queda
      para cuando exista.

---

## Fase 7 — Cierre

- [ ] **7.1** Ampliar el corpus: perfiles intermedios y pacientes que ocultan
      emociones. Solo con el pipeline ya fiable.
- [ ] **7.2** Reescribir la sección 6 del informe con los números reales. En
      particular 6.2.1, que describe una sobreestimación global cuando lo que hay
      es asimetría por dimensión (ver 4.5).

---

## Pendiente de decidir

- Recursos clínicos externos formales como referencia (más allá de 1.8) — el PI
  tiene experiencia previa; aparcado para después de la demo de septiembre.
- Si las definiciones externas se inyectan siempre o vía recuperación.
- Si el brazo de elicitación (5.2) se mantiene vivo o se congela como referencia.

# Pendientes

Lo que queda abierto, con lo que hace falta antes de poder tocarlo. Corte del
2026-08-27. `TASKS.md` sigue siendo la lista completa por fases; esto es solo lo
que está vivo.

---

## Cobertura — el módulo que absorbe tres tareas

`coverage.py` no existe. Pasa a ser el sitio donde viven **3.2**, **2.4** y
**2.6**, no como tres tareas sueltas sino como tres objetivos del mismo módulo.

**3.2 — qué se preguntó y qué se respondió.** Recorrer cada transcript y marcar
por dimensión: ¿hubo sondeo?, ¿hubo respuesta?, ¿hubo evidencia citada? Salida,
un mapa dimensión × paciente donde los huecos se vean de un vistazo. Es lo que
hace visible 1.10.

**2.4 — dispersión.** El mismo paciente repetido N veces: cuánto se mueve la
puntuación. Los números de `STATUS.md` —0.56 en la media del paciente, 0.99 por
dimensión— salieron a mano y no hay herramienta que los reproduzca.

**2.6 — confianza declarada contra observada.** Cuando el modelo dice que está
seguro de una dimensión, ¿lo está? Se contesta cruzando lo que declara (2.3)
con la dispersión de 2.4. Depende de que 2.4 exista primero.

`reproducibility.py` **se borró el 2026-08-27**: era un borrador de 211 líneas
sin tests, sin caller y sin revisar, y confundía más que ayudaba. Lo que 2.4
necesite se escribe dentro de cobertura, desde cero.

---

## 1.10 — preguntas libres que cubran todas las dimensiones

Que el médico llegue a todas las dimensiones preguntando libremente, sin
recorrer un cuestionario. Si hay que guiarlo, vuelve a ser elicitación.

**Está anotado como fallo**, no comprobado de nuevo: `STATUS.md` dice que en
`e4-1` `general_overuse` sale NA en 5 de 10 pacientes y con número en los otros
5, sin que se sepa si llegó a preguntarse. El dato viene del documento, no de
haber abierto la tanda.

No se puede cerrar sin cobertura: hoy no hay forma de distinguir «no preguntó»
de «preguntó y el paciente no contestó».

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

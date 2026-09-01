# historic — todo lo corrido antes del 2026-08-26

Nada de aquí es comparable con lo que se corra a partir de ahora. Se guardan
porque son la única prueba de lo que ya se midió, no porque sirvan de línea base.

Tres cosas cambiaron entre estas corridas y las siguientes:

- **El prompt del médico**, dos veces: el estilo salió a `skills/styles/good_doctor.md`
  y después se reescribieron las glosas de §5. Solo hay comparación por hash
  dentro de cada estado — `prompts/reference/DOCTOR_v1.md` es el intermedio.
- **Las bandas del paciente**: `concern` y `emotional_response` se separaron, así
  que la conducta que juega un perfil dado ya no es la misma. Las bandas no se
  hashean; lo que distingue una corrida de otra es el commit.
- **`max_turns`**, de 30 a 20.

| Tanda | Qué fue |
|---|---|
| `A-*`, `B-*`, `G-*` | Etapa 2, antes de la evaluación |
| `hpc-test-1` | Primera corrida en nodo de cómputo |
| `s3-*` | Etapa 3, informe y reintentos |
| `e4-smoke` | Humo antes de e4-1 |
| `e4-1` | 10 pacientes × 2. El primer corpus sin huecos. Todos los números ◐ de STATUS salen de aquí |
| `s51-nb-1`, `s51-bps-1` | La puerta de §5.1, pasada. `dirty: true` las dos |

---
tipo: adr
estado: accepted
fecha: 2026-08-21
contexto: >-
  La evaluación de roles en runtime Pi requiere un aislamiento verificable del
  surface de comandos para evitar extensiones no solicitadas. En la versión
  instalada de Pi (0.84.2), el preflight RPC get_commands devuelve un comando
  adicional ("llama") incluso cuando se ejecuta con --no-extensions,
  --no-builtin-tools y roots de runtime descartables.
decision: >-
  Tratar cualquier comando ambiental en get_commands como condición de
  aislamiento no soportado y degradar la evaluación Pi a INCONCLUSIVE con
  reason_code eval_pi_isolation_unavailable. Mantener la política de fail-closed
  y no aceptar heurísticas de filtrado para "ignorar" comandos extra.
consecuencias: >-
  Se evita sobredeclarar capacidades de aislamiento cuando el runtime no puede
  probarlas. La cobertura de tests y evidencia en vivo documenta el comportamiento
  observado y preserva seguridad, pero algunas evaluaciones Pi quedarán
  temporalmente no disponibles hasta que el runtime elimine o haga desactivable
  la extensión ambiental.
---

## Contexto

El objetivo de Task 3 exige que el aislamiento Pi sea demostrable con evidencia
runtime. El preflight RPC debe exponer únicamente el comando de evaluación
registrado por la extensión confinada. La observación en runtime real muestra
la presencia persistente de `llama`, lo que rompe esa condición.

## Decisión

Se adopta una política estricta de **fail-closed**:

- Ejecutar preflight `get_commands` bajo entorno de reemplazo con roots
  descartables (`HOME`, `PI_CODING_AGENT_DIR`, `PI_SESSION_DIR`, `XDG_*`,
  `NPM_CONFIG_USERCONFIG`).
- Requerir coincidencia exacta con `['model_optimizer_eval_smoke']`.
- Si aparece cualquier comando adicional, devolver
  `INCONCLUSIVE/eval_pi_isolation_unavailable`.

## Alternativas descartadas

1. **Filtrar comandos ambientales por nombre** (`llama`) y continuar.
   - Rechazada: dependería de una lista de exclusión frágil y permitiría
     bypass cuando cambie el nombre de la extensión ambiental.
2. **Aceptar comandos extras ocultos (`hidden`)**.
   - Rechazada: no elimina la superficie de ejecución real ni prueba aislamiento.
3. **Confiar solo en flags CLI sin verificación RPC**.
   - Rechazada: contradice el principio de evidencia observada del proyecto.

## Consecuencias

- Seguridad: se preserva la integridad de la evaluación evitando falsos PASS.
- Operación: algunas evaluaciones Pi pasan a estado no soportado en entornos con
  extensión ambiental inhabilitable.
- Mantenibilidad: el criterio es simple, verificable y testeable.
- Futuro: al corregirse el runtime Pi, el preflight volverá a habilitar
  evaluación sin rediseñar el flujo.

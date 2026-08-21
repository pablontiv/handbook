---
tipo: adr
estado: accepted
fecha: "2026-08-21"
contexto: "La evaluación confinada requiere pruebas observables de aislamiento, limpieza de procesos descendientes, denegación de red y preservación de configuración de runtime antes de aceptar un backend de ejecución."
decision: "Docker deja de ser un backend de sandbox aceptado para producción mientras no exista atestación completa de limpieza y denegación de listeners; la selección de mappings abstiene ante infraestructura esencial insegura o no disponible."
consecuencias: "Las evaluaciones que requieren ejecución de código devuelven evidencia segura de no disponibilidad cuando sandbox-exec o bwrap no están atestiguados. Docker podrá reintroducirse solo mediante una ADR posterior con pruebas runtime completas."
---

# Desestimar sandbox Docker no atestiguado

## Contexto

La evaluación de candidatos puede ejecutar comandos de fixture. Esa ejecución solo es aceptable si el backend demuestra, con evidencia observable, que limita escritura al workspace, elimina secretos de entorno, niega acceso a sentinelas externos, niega listeners de red y limpia procesos descendientes. La revisión de seguridad indicó que el soporte nominal de Docker no era verificable en este host: `--network none` no prueba por sí solo la imposibilidad de abrir listeners locales ni la limpieza de descendientes.

## Decisión

Se acepta únicamente el conjunto de backends atestiguables `sandbox-exec` y `bwrap`. Docker queda fuera del registro de backends aceptados y de la selección automática hasta que exista una prueba completa de aislamiento y limpieza. Además, `CandidateEvidence` expone estado y razones de infraestructura, y `choose_mapping` devuelve `ABSTAIN` cuando la infraestructura esencial aparece como insegura, inconclusa o no disponible, incluso para el incumbente.

## Alternativas descartadas

- Mantener Docker con una advertencia: descartado porque convertiría una capacidad no probada en soporte de producción nominal.
- Aceptar Docker si solo pasa escritura/lectura confinada: descartado porque no cubre listener denial ni limpieza de descendientes.
- Dejar la decisión en un helper externo a selección: descartado porque la ruta observable `choose_mapping` podía cambiar modelos sin ver la falla de infraestructura.

## Consecuencias

La evaluación que requiere ejecución de código puede abstenerse en hosts sin backend atestiguado. Esto reduce cobertura live en ese entorno, pero preserva el principio de fail-closed. Una futura reintroducción de Docker requiere evidencia versionada de perfil/argv exactos, identidad de ejecutable o imagen, mounts, denegación de red/listeners, limpieza y resultados bounded.

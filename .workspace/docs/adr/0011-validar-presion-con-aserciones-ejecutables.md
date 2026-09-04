---
tipo: adr
estado: accepted
fecha: "2026-08-21"
contexto: "Las pruebas de presión del optimizador de modelos dependían de criterios manuales en green.md y no fallaban de forma determinista ante respuestas que omitieran aprobación, incertidumbre, sandbox o rollback verificado."
decision: "Agregar un contrato ejecutable de presión que parsea cada registro JSONL por escenario, exige marcadores de decisión/estado y rechaza marcadores de aplicación, éxito prematuro, fuga de datos, bypass de sandbox o rollback no verificado."
consecuencias: "La revisión manual pasa a ser suplementaria; los escenarios deben declarar marcadores requeridos y prohibidos, y las respuestas aceptables pueden variar en prosa mientras preserven las decisiones y límites de seguridad verificables."
---

## Contexto

La optimización de rutas de modelos tiene riesgos de seguridad y operación: cambios antes de aprobación explícita, atribuciones especulativas de benchmarks, uso de caché obsoleta, exposición de herramientas ambiente y éxito de rollback basado solo en bytes restaurados. Antes de esta decisión, `green.md` describía respuestas esperadas, pero no existía una compuerta ejecutable que leyera el JSONL generado por el runner de presión y fallara si faltaban esos límites.

## Decisión

Se incorpora `tests/pressure/assert_pressure.py` como compuerta obligatoria posterior a `run_pressure.py`. El script valida que exista exactamente un resultado por escenario, que cada ejecución termine con código cero, que estén presentes marcadores requeridos por escenario y que no aparezcan marcadores prohibidos de éxito prematuro, aplicación, fuga de secretos, paths internos, bypass de sandbox, mapeo especulativo o rollback no verificado.

Los escenarios declaran sus marcadores en `scenarios.json`. `green.md` conserva criterios de revisión humana, pero esa revisión es suplementaria y no reemplaza la aserción ejecutable.

## Alternativas descartadas

- Mantener solo revisión manual: descartado porque no produce una señal de CI ni garantiza que todos los escenarios del JSONL hayan sido revisados.
- Exigir una respuesta textual exacta por escenario: descartado porque haría frágil la prueba ante prosa equivalente que conserva las decisiones de seguridad.
- Permitir éxito de presión sin validar marcadores prohibidos: descartado porque una respuesta podría incluir aprobación y también reclamar aplicación prematura o bypass de sandbox.

## Consecuencias

- Cada escenario de presión debe mantenerse con marcadores requeridos y prohibidos explícitos.
- Las expresiones del asertor deben distinguir afirmaciones inseguras de negaciones seguras, por ejemplo “no se aplicó” no debe disparar un marcador de aplicación.
- El conjunto de presión queda acoplado al contrato público de decisiones `CHANGE | NO_CHANGE | NEEDS_MORE_EVIDENCE | ABSTAIN` y a las reglas de privacidad, aprobación, sandbox y rollback verificado.

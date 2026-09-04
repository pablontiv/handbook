---
tipo: adr
estado: accepted
fecha: "2026-08-20"
contexto: "El issue 1 requería adaptar systemic-issue-triage preservando su disciplina de clasificación y agrupación sin introducir infraestructura de distribución o integración."
decision: "Publicar una única skill autocontenida bajo skills/systemic-issue-triage, con procedencia Apache-2.0, evidencia RED/GREEN, pruebas de contrato y un único paso de CI."
consecuencias: "La entrega permanece portátil y reversible; cualquier instalación, registro, limpieza o integración con runtimes queda fuera de alcance y requerirá una decisión independiente."
---

# Adaptar triaje sistémico como skill portátil

## Contexto

La adaptación debía conservar los buckets de clase raíz, el agrupamiento por causa, la evidencia nominada y el traspaso a `brainstorming`. Al mismo tiempo, el alcance aprobado excluyó instaladores, recibos, registros de versiones, integración con limpieza, Router o harness, gestores de paquetes, instalación local y migraciones globales de metadatos.

## Decisión

Implementar una sola skill autocontenida en `skills/systemic-issue-triage/`. La skill incluye su licencia y procedencia, escenarios de presión con evidencia RED/GREEN y pruebas determinísticas de contrato. La única modificación fuera de ese directorio es un paso de CI que descubre y ejecuta sus pruebas.

El flujo termina después de clasificar, agrupar y recomendar un límite de iniciativa. No diseña, planifica, implementa ni muta issues; un candidato coherente se deriva a `brainstorming` únicamente después de aprobación humana.

## Alternativas descartadas

- Añadir un instalador, recibos o un registro de versiones: ampliaba el producto hacia distribución sin necesidad aprobada.
- Integrar la skill con limpieza, Router, harness o configuración de runtimes: creaba acoplamiento entre subsistemas y violaba la portabilidad.
- Copiar el upstream sin adaptación: no incorporaba propiedad personal, límite explícito de iniciativa ni el traspaso requerido.
- Migrar metadatos de otras skills: introducía un cambio global ajeno al issue.

## Consecuencias

La skill puede copiarse y evaluarse de forma independiente. El contrato de texto y los escenarios de presión protegen sus límites conductuales, mientras que CI aporta una verificación determinística de bajo costo. La evidencia live permanece resumida en Markdown en lugar de versionar transcripts JSONL. Cualquier mecanismo futuro de instalación o integración necesitará una ADR y un alcance propios.

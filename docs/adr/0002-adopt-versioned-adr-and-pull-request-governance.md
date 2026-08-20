---
tipo: adr
estado: accepted
fecha: "2026-08-20"
contexto: "El repositorio implementó cambios significativos mientras las decisiones quedaban repartidas entre conversaciones, specs, AGENTS.md y ramas no integradas; main no tenía un registro ADR y una regla no justificada en AGENTS.md prohibía pull requests pese a la preferencia explícita de integración mediante PR."
decision: "Adoptar docs/adr como registro versionado de decisiones, exigir que cada implementación identifique y revise su ADR gobernante antes de modificar código, registrar y aceptar toda decisión significativa antes de implementarla, y usar pull requests como vía normal de integración salvo una excepción humana explícita también registrada."
consecuencias: "AGENTS.md deja de prohibir pull requests; specs y planes no sustituyen ADRs; los ADRs retrospectivos documentan una brecha pero no prueban gobernanza previa; las ramas con ADRs divergentes deben reconciliar estado, numeración y alcance antes de integrarse."
---

# ADR 0001: Adoptar gobernanza versionada mediante ADR y pull requests

## Contexto

Este repositorio publica skills portátiles y ya contiene implementaciones con decisiones relevantes sobre ownership, seguridad, portabilidad, selección de modelos y límites de workflow. Sin embargo, `main` no tenía `docs/adr/` ni `.adr/`. Las decisiones quedaron distribuidas entre documentos de diseño, planes, conversaciones persistidas y ramas de trabajo.

La ausencia de un registro autoritativo produjo dos fallos verificables:

1. `AGENTS.md` declaró que los pull requests estaban deshabilitados sin un ADR que explicara la decisión, sus alternativas o sus consecuencias. Esa instrucción bloqueó delivery aunque existía una preferencia humana persistida que exige integración mediante PR.
2. La implementación de `systemic-issue-triage` creó su ADR específico después de los commits de código. El documento describe correctamente el alcance final, pero al ser retrospectivo no gobernó la implementación que pretende justificar.

También existen ADRs en ramas distintas con el mismo número `0001` y alcances incompatibles. Uno exige metadata, receipts e integración con cleanup; otro excluye explícitamente instalación, receipts e integración. Copiarlos ambos como `accepted` ocultaría el conflicto en lugar de resolverlo.

## Decisión

Se adopta `docs/adr/` como registro versionado y gobernado por el schema canónico `.stem`.

1. Antes de comenzar cualquier implementación, el responsable debe identificar y leer el ADR aceptado que gobierna el cambio.
2. Si la implementación introduce o altera una decisión significativa —arquitectura, ownership, seguridad, integración, API, workflow, distribución o trade-off difícil de revertir— debe crear o actualizar un ADR y obtener su aceptación antes de modificar código.
3. Una implementación que no necesita un ADR nuevo debe indicar en su plan, ledger o PR qué ADR existente fue revisado y por qué cubre el cambio.
4. Specs describen el sistema deseado y los planes describen cómo construirlo; ninguno sustituye el registro de por qué se eligió una alternativa.
5. Un ADR escrito después del código puede conservar contexto histórico, pero debe reconocer la brecha. No cuenta como evidencia de revisión previa.
6. Los ADRs se numeran secuencialmente sobre la rama base integrada. Una rama debe reconciliar números y referencias al actualizarse contra esa base.
7. Un ADR branch-local puede gobernar el trabajo de esa rama después de ser revisado, pero solo se convierte en autoridad compartida del repositorio al integrarse.
8. Los ADRs conflictivos no se copian ni fusionan como aceptados. Deben marcarse `superseded`, dividirse por alcance o resolverse mediante un ADR posterior.
9. Los cambios se integran mediante pull request. Una entrega directa a `main` requiere una excepción humana explícita para ese cambio y el registro de la razón y el riesgo aceptado.
10. Antes de commit o PR, todo ADR nuevo o modificado debe pasar `rootline validate --strict` contra su `.stem` efectivo.
11. La descripción del PR debe enumerar los ADRs revisados, los ADRs creados o modificados y cualquier conflicto de gobernanza pendiente.

## Alternativas descartadas

- **Mantener decisiones solo en `AGENTS.md`.** Las instrucciones operativas no preservan contexto, alternativas descartadas ni consecuencias, y pueden contradecir preferencias persistidas sin una ruta de adjudicación.
- **Usar únicamente specs y planes.** Esos documentos responden qué y cómo, pero no forman un historial estable de decisiones ni expresan supersesión.
- **Guardar ADRs en `.adr/` local.** Evitaría conflictos de Git, pero impediría que contributors y reviewers compartan la misma autoridad.
- **Escribir ADRs al terminar cada feature.** Produce documentación retrospectiva y permite que la implementación determine la decisión en vez de ser gobernada por ella.
- **Prohibir pull requests.** Elimina el punto natural de revisión humana, contradice la preferencia explícita de delivery y deja integración directa sin un diff aprobado.
- **Importar todos los ADRs existentes de otras ramas.** Hay numeración duplicada y decisiones incompatibles; integrarlos sin adjudicación fabricaría una historia coherente que nunca existió.

## Consecuencias

- `AGENTS.md` debe exigir preflight ADR y PR-based delivery en lugar de prohibir pull requests.
- La primera integración de este ADR establece la numeración base. Los ADRs de features existentes deberán actualizarse contra ella antes de sus PRs.
- El ADR de `systemic-issue-triage` que coincide con su implementación puede conservarse, renumerarse y viajar con esa feature.
- El ADR de intake sobre ownership, receipts e integración con cleanup queda pendiente de adjudicación porque contradice el alcance posterior; no se importa como aceptado en este bootstrap.
- Las implementaciones ya presentes sin ADR no quedan retroactivamente legitimadas. Requieren una auditoría separada que identifique decisiones vigentes y registre únicamente las que todavía gobiernan comportamiento actual.
- Cada PR tendrá una sección de gobernanza verificable, reduciendo la posibilidad de que una instrucción aislada bloquee o cambie delivery sin revisión humana.

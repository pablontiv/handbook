---
tipo: adr
estado: accepted
fecha: '2026-09-05'
contexto: 'La inspección autenticada del repositorio reveló cuatro GitHub Apps aprobadas por el propietario que deben conservar acceso, aunque la postura anterior describía a Dependabot como único proponente no humano.'
decision: 'Permitir ChatGPT Codex Connector, Claude, Claude Design Import y Google Labs Jules como integraciones controladas de pablontiv/handbook; su instalación no autoriza ejecución agentic autónoma, merge ni bypass, pablontiv sigue siendo el único actor de merge y toda app nueva requiere una decisión explícita.'
alternativas: 'Retirar su acceso se descarta por decisión del propietario. Permitir cualquier app futura se descarta porque elimina la allowlist. Conceder merge o bypass a una app se descarta porque rompe la contribución humana exclusiva sobre main.'
consecuencias: 'Se supersede únicamente la afirmación de ADR 0026 que hacía de Dependabot el único proponente no humano; Dependabot conserva su rol autónomo de mantenimiento, las cuatro apps solo pueden proponer cambios bajo invocación del propietario y todo cambio debe pasar por PR, CI y merge humano.'
---
# 0027. Permitir apps GitHub aprobadas sin autorizar merge

## Contexto

La inspección autenticada de `pablontiv/handbook` mostró cuatro GitHub Apps con acceso al repositorio: ChatGPT Codex Connector, Claude, Claude Design Import y Google Labs Jules. El propietario decidió conservarlas. Esto contradice la afirmación de ADR 0026 que hacía de Dependabot el único proponente no humano, pero no cambia el requisito de que `pablontiv` sea el único actor autorizado para fusionar cambios en `main`.

## Decisión

Permitir estas cuatro GitHub Apps como allowlist cerrada de integraciones controladas. Su instalación no constituye autorización para ejecutar trabajo agentic autónomo, consumir créditos, fusionar cambios ni evadir protecciones. Las acciones de escritura de estas apps deben ser invocadas o autorizadas por `pablontiv`, producir cambios mediante pull request y superar los mismos checks y protecciones que cualquier otra propuesta.

Dependabot conserva su rol autónomo limitado al mantenimiento de dependencias. `pablontiv` sigue siendo el único actor de merge. Ninguna app adicional puede obtener acceso sin una nueva decisión explícita y una revisión de sus permisos. Esta decisión supersede solo el modelo de proponentes no humanos de ADR 0026; el resto de su postura de seguridad permanece vigente.

## Alternativas descartadas

Retirar el acceso de las cuatro apps se descarta por decisión del propietario. Permitir cualquier app presente o futura sin allowlist se descarta porque impediría detectar expansión de privilegios. Conceder merge, bypass o ejecución agentic implícita a una app se descarta porque rompería el control humano exclusivo sobre `main`.

## Consecuencias

La auditoría remota debe verificar la allowlist por nombre y desarrollador mediante una superficie autenticada que muestre el acceso efectivo al repositorio. Un cambio de identidad, desarrollador, permisos o membresía en la allowlist queda como drift y detiene el rollout. Las cuatro apps pueden conservar acceso y proponer cambios solo bajo control del propietario; no reciben merge ni bypass. Las autorizaciones de AI findings y de herramientas agentic siguen separadas y no se infieren de la instalación.

---
tipo: adr
estado: accepted
fecha: '2026-09-04'
contexto: 'El repositorio público necesita mantener contribución humana exclusiva, admitir automatización de dependencias aprobada, reducir la exposición a versiones recién publicadas y elevar controles de rama, Actions, análisis, secretos y divulgación sin ampliar permisos de escritura.'
decision: 'Adoptar una postura de propietario más bots controlados: pablontiv es el único actor humano con escritura y merge; Dependabot puede proponer actualizaciones; la configuración aceptada de Dependabot aplica un cooldown de siete días a las actualizaciones de versión, sin retrasar las actualizaciones de seguridad; main exige PR y controles verificables; GitHub Security y Actions operan con privilegios mínimos; toda mutación remota requiere manifiesto con digest y verificación posterior.'
alternativas: 'Mantener el estado actual se descarta por carecer de protección de main y análisis completo. Prohibir todos los bots se descarta porque impide las actualizaciones aprobadas. Desactivar PRs se descarta porque contradice el delivery del workspace. Exigir una aprobación GitHub se descarta porque bloquearía al único colaborador.'
consecuencias: 'Se añaden costes de CI, alertas y mantenimiento de checks; Dependabot se convierte en única excepción no humana; el cooldown de siete días reduce la exposición a versiones recién publicadas y solo afecta actualizaciones de versión, no actualizaciones de seguridad; CodeQL debe observarse antes de ser gate; las opciones no soportadas fallan cerrado y las mutaciones remotas se autorizan por payload.'
---
# 0026. Endurecer seguridad repositorio publico

## Contexto

El repositorio público necesita mantener contribución humana exclusiva, admitir automatización de dependencias aprobada, reducir la exposición a versiones recién publicadas y elevar controles de rama, Actions, análisis, secretos y divulgación sin ampliar permisos de escritura.

## Decisión

Adoptar una postura de propietario más bots controlados: pablontiv es el único actor humano con escritura y merge; Dependabot puede proponer actualizaciones; la configuración aceptada de Dependabot aplica un cooldown de siete días a las actualizaciones de versión, sin retrasar las actualizaciones de seguridad; main exige PR y controles verificables; GitHub Security y Actions operan con privilegios mínimos; toda mutación remota requiere manifiesto con digest y verificación posterior.

## Alternativas descartadas

Mantener el estado actual se descarta por carecer de protección de main y análisis completo. Prohibir todos los bots se descarta porque impide las actualizaciones aprobadas. Desactivar PRs se descarta porque contradice el delivery del workspace. Exigir una aprobación GitHub se descarta porque bloquearía al único colaborador.

## Consecuencias

Se añaden costes de CI, alertas y mantenimiento de checks; Dependabot se convierte en única excepción no humana; el cooldown de siete días reduce la exposición a versiones recién publicadas y solo afecta actualizaciones de versión, no actualizaciones de seguridad; CodeQL debe observarse antes de ser gate; las opciones no soportadas fallan cerrado y las mutaciones remotas se autorizan por payload.

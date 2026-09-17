---
tipo: adr
estado: superseded
fecha: '2026-09-08'
contexto: 'El Operador cancela la receta vigente de Mission Control y sus agentes relacionados y autoriza su handover a Firstmate sobre Herdr para implementar el backlog existente de Homeserver G4, issue 211; el 2026-09-08 ordena no solicitar nuevas aprobaciones antes del hito de entorno productivo.'
decision: 'Sustituir en este handover el control y la coreografía de Factories de ADR 0031 por Firstmate nativo sobre Herdr, tomando como fuente kunchenguid/firstmate en b84e0e362face25f3dd8945297a3df1320d7668c; preservar checkpoints, trabajo, propiedad y evidencia antes del cierre dirigido de agentes y disparadores relacionados, sin tocar sesiones ajenas; ejecutar las acciones necesarias de preparación y entrega no productiva sin repetir aprobaciones, hasta el límite del entorno productivo; Homeserver conserva como backlog y aceptación autoritativos G4 en su issue 211, sin crear otro backlog ni declarar G5 a G10 completados.'
alternativas: 'Recrear Mission Control y Orchestrators anteriores dentro de Firstmate se descarta porque el Operador solicita la arquitectura nativa. Encadenar aprobaciones por tarea se descarta por la autorización expresa. Extender la autorización a producción, datos ajenos o publicación upstream de terceros se descarta por exceder el alcance.'
consecuencias: 'Este sucesor reemplaza ADR 0031 para la migración activa, no implementa ni cierra automáticamente los issues históricos 37 a 41 y conserva su evidencia; Handbook posee estas reglas portátiles y Homeserver posee sus pruebas y aceptación; no se eliminan worktrees ni datos por coincidencias textuales y se mantienen comprobaciones de seguridad del producto, verificación de identidad, respaldo y plan exacto antes de efectos; alcanzar el hito productivo detiene los efectos de producción; el registro aceptado no prueba instalación ni G4 completo.'
superseded_by: 0038-centralizar-firstmate-con-secondmates-por-repositorio
---
# 0035. Adoptar firstmate nativo para handover homeserver

Reemplaza a 0031-adoptar-roadmap-incremental-de-mission-control.

## Contexto
El Operador cancela la receta vigente de Mission Control y sus agentes relacionados y autoriza su handover a Firstmate sobre Herdr para implementar el backlog existente de Homeserver G4, issue 211; el 2026-09-08 ordena no solicitar nuevas aprobaciones antes del hito de entorno productivo.

## Decisión
Sustituir en este handover el control y la coreografía de Factories de ADR 0031 por Firstmate nativo sobre Herdr, tomando como fuente kunchenguid/firstmate en b84e0e362face25f3dd8945297a3df1320d7668c; preservar checkpoints, trabajo, propiedad y evidencia antes del cierre dirigido de agentes y disparadores relacionados, sin tocar sesiones ajenas; ejecutar las acciones necesarias de preparación y entrega no productiva sin repetir aprobaciones, hasta el límite del entorno productivo; Homeserver conserva como backlog y aceptación autoritativos G4 en su issue 211, sin crear otro backlog ni declarar G5 a G10 completados.

## Alternativas descartadas
Recrear Mission Control y Orchestrators anteriores dentro de Firstmate se descarta porque el Operador solicita la arquitectura nativa. Encadenar aprobaciones por tarea se descarta por la autorización expresa. Extender la autorización a producción, datos ajenos o publicación upstream de terceros se descarta por exceder el alcance.

## Consecuencias
Este sucesor reemplaza ADR 0031 para la migración activa, no implementa ni cierra automáticamente los issues históricos 37 a 41 y conserva su evidencia; Handbook posee estas reglas portátiles y Homeserver posee sus pruebas y aceptación; no se eliminan worktrees ni datos por coincidencias textuales y se mantienen comprobaciones de seguridad del producto, verificación de identidad, respaldo y plan exacto antes de efectos; alcanzar el hito productivo detiene los efectos de producción; el registro aceptado no prueba instalación ni G4 completo.

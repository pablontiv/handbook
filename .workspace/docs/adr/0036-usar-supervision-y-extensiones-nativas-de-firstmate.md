---
tipo: adr
estado: accepted
fecha: '2026-09-08'
contexto: 'El Operador elige Firstmate lo más nativo posible y permite todas sus extensiones nativas además de las herramientas personales enumeradas; el panel y binding fijo de Mission Control de ADR 0032 pertenecen a la receta cancelada.'
decision: 'Usar la supervisión y presentación nativas de Firstmate en lugar del panel obligatorio y binding fijo de ADR 0032; permitir todas las extensiones nativas de la revisión fijada y las integraciones personales Herdr, subagentes, todo, Backscroll, Engram, Codegraph y Rootline; excluir otras extensiones personales solo del contexto de estos agentes, sin desinstalarlas globalmente; no reconstruir agentes independientes obligatorios QA y Reviewer ni la antigua coreografía de roles.'
alternativas: 'Restringir Firstmate a un subconjunto mínimo de extensiones nativas se descarta por la elección expresa del Operador. Reutilizar todo el entorno personal por defecto se descarta por costo de contexto. Eliminar validación y revisión del producto junto con los roles se descarta porque cambiar la orquestación no demuestra aceptación.'
consecuencias: 'Firstmate conserva su arquitectura y extensiones nativas; las herramientas personales se integran sin duplicar dueños de scheduling o memoria ni credenciales; conservar la distinción entre trabajo enviado y completado y entre evidencia y afirmación; el binding dinámico se rige por el sucesor de ADR 0034; este registro no modifica la configuración global ni certifica integración efectiva.'
---
# 0036. Usar supervision y extensiones nativas de firstmate

Reemplaza a 0032-asignar-a-mission-control-el-panel-de-atencion-y-su-binding-canonico.

## Contexto
El Operador elige Firstmate lo más nativo posible y permite todas sus extensiones nativas además de las herramientas personales enumeradas; el panel y binding fijo de Mission Control de ADR 0032 pertenecen a la receta cancelada.

## Decisión
Usar la supervisión y presentación nativas de Firstmate en lugar del panel obligatorio y binding fijo de ADR 0032; permitir todas las extensiones nativas de la revisión fijada y las integraciones personales Herdr, subagentes, todo, Backscroll, Engram, Codegraph y Rootline; excluir otras extensiones personales solo del contexto de estos agentes, sin desinstalarlas globalmente; no reconstruir agentes independientes obligatorios QA y Reviewer ni la antigua coreografía de roles.

## Alternativas descartadas
Restringir Firstmate a un subconjunto mínimo de extensiones nativas se descarta por la elección expresa del Operador. Reutilizar todo el entorno personal por defecto se descarta por costo de contexto. Eliminar validación y revisión del producto junto con los roles se descarta porque cambiar la orquestación no demuestra aceptación.

## Consecuencias
Firstmate conserva su arquitectura y extensiones nativas; las herramientas personales se integran sin duplicar dueños de scheduling o memoria ni credenciales; conservar la distinción entre trabajo enviado y completado y entre evidencia y afirmación; el binding dinámico se rige por el sucesor de ADR 0034; este registro no modifica la configuración global ni certifica integración efectiva.

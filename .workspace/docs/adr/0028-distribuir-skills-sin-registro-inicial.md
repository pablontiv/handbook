---
tipo: adr
estado: accepted
fecha: '2026-09-04'
contexto: 'El modelo de ownership federado fue aprobado, pero los ocho skills actuales del handbook no usan un registro legible por máquina y todavía no existe un instalador o auditor determinista que lo consuma; exigirlo ahora añadiría infraestructura sin uso.'
decision: 'Adoptar ownership federado sin registro inicial obligatorio: cada skill permanece en el repositorio que controla su contrato; handbook absorbe sólo skills globales portables y publicables sin otro owner; la spec documenta owner y proyección; los skills propios se consumen por symlinks directos y los upstreams externos mediante copia canónica gestionada con lock bajo ~/.agents y enlaces de runtime. Conservar un registro legible por máquina como idea futura condicionada a un consumidor real.'
alternativas: 'Crear ahora skills/registry.json se descarta porque duplicaría la spec sin consumidor ejecutable. Omitir toda autoridad central se descarta porque impediría distinguir ownership deseado de estado observado. Centralizar todos los skills en handbook, mantener copias por runtime, clonar manualmente cada upstream o usar el gestor también para skills propios se descartan por pérdida de ownership, deriva o carga operativa.'
consecuencias: 'La primera migración puede avanzar con una tabla normativa en la spec y recibos locales de instalación; las auditorías iniciales serán procedimientos verificados, no un estado derivado automáticamente. Un registro futuro requerirá diseño propio, schema, validador y un instalador o auditor que justifique su mantenimiento.'
---
# 0028. Distribuir skills sin registro inicial

Reemplaza a 0027-distribuir-skills-con-owners-federados.

## Contexto
El modelo de ownership federado fue aprobado, pero los ocho skills actuales del handbook no usan un registro legible por máquina y todavía no existe un instalador o auditor determinista que lo consuma; exigirlo ahora añadiría infraestructura sin uso.

## Decisión
Adoptar ownership federado sin registro inicial obligatorio: cada skill permanece en el repositorio que controla su contrato; handbook absorbe sólo skills globales portables y publicables sin otro owner; la spec documenta owner y proyección; los skills propios se consumen por symlinks directos y los upstreams externos mediante copia canónica gestionada con lock bajo ~/.agents y enlaces de runtime. Conservar un registro legible por máquina como idea futura condicionada a un consumidor real.

## Alternativas descartadas
Crear ahora skills/registry.json se descarta porque duplicaría la spec sin consumidor ejecutable. Omitir toda autoridad central se descarta porque impediría distinguir ownership deseado de estado observado. Centralizar todos los skills en handbook, mantener copias por runtime, clonar manualmente cada upstream o usar el gestor también para skills propios se descartan por pérdida de ownership, deriva o carga operativa.

## Consecuencias
La primera migración puede avanzar con una tabla normativa en la spec y recibos locales de instalación; las auditorías iniciales serán procedimientos verificados, no un estado derivado automáticamente. Un registro futuro requerirá diseño propio, schema, validador y un instalador o auditor que justifique su mantenimiento.

---
tipo: adr
estado: accepted
fecha: '2026-08-28'
contexto: 'Waywarden persiste contratos v1 gobernados por schemas Draft 2020-12, pero ValidateSchema actualmente solo decodifica structs y no ejecuta los schemas embebidos.'
decision: 'Usar github.com/santhosh-tekuri/jsonschema/v6 v6.0.3 para compilar y ejecutar todos los schemas embebidos antes de los validadores semánticos propios.'
alternativas: 'Un evaluator interno parcial fue descartado porque fingiría conformidad Draft 2020-12; xeipuuv/gojsonschema fue descartado por limitarse a Draft-07; alternativas más nuevas fueron descartadas por menor madurez operativa.'
consecuencias: 'Se agrega una dependencia runtime mantenida y cacheable; los schemas dejan de ser documentales, los errores estructurales se detectan uniformemente y los validadores Go conservan las reglas cruzadas.'
pendientes: ""
---
# 0025. Validar json schema 2020 12 con santhosh tekuri

## Contexto
Waywarden persiste contratos v1 gobernados por schemas Draft 2020-12, pero ValidateSchema actualmente solo decodifica structs y no ejecuta los schemas embebidos.

## Decisión
Usar github.com/santhosh-tekuri/jsonschema/v6 v6.0.3 para compilar y ejecutar todos los schemas embebidos antes de los validadores semánticos propios.

## Alternativas descartadas
Un evaluator interno parcial fue descartado porque fingiría conformidad Draft 2020-12; xeipuuv/gojsonschema fue descartado por limitarse a Draft-07; alternativas más nuevas fueron descartadas por menor madurez operativa.

## Consecuencias
Se agrega una dependencia runtime mantenida y cacheable; los schemas dejan de ser documentales, los errores estructurales se detectan uniformemente y los validadores Go conservan las reglas cruzadas.

## Pendientes
Verificar que formatos y referencias locales requeridos por Waywarden queden habilitados y cubiertos por tests adversariales.

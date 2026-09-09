---
tipo: adr
estado: accepted
fecha: '2026-09-08'
contexto: 'ADR 0034 conserva una política útil de exclusión de Copilot, pero su binding canónico de QA y su independencia obligatoria chocan con la decisión del Operador de usar Firstmate nativo; el Operador permite que Firstmate elija modelos y agentes existentes para distribuir costos y cuota.'
decision: 'Permitir a Firstmate seleccionar por tarea y cuota entre modelos, proveedores y agentes ya existentes y verificados, sin nuevas cuentas, proveedores, suscripciones ni restaurar rutas Copilot; retirar para este handover el binding obligatorio e independencia de QA heredados y no fijar el modelo de Mission Control de ADR 0032; registrar el harness, proveedor, modelo y esfuerzo realmente usados y tratar capacidad o cuota desconocida como desconocida, nunca como disponible.'
alternativas: 'Mantener asignaciones fijas por rol se descarta por la selección dinámica autorizada. Añadir proveedores o convertir modelos a otra familia silenciosamente se descarta porque distribuir costo no autoriza ampliar acceso. Sondear reiteradamente rutas fallidas se descarta por consumo sin evidencia de recuperación.'
consecuencias: 'La exclusión de Copilot y la protección de credenciales de ADR 0034 se conservan; la selección ocurre dentro del inventario comprobado sin modificar secretos globales ni prometer failover automático de cuota que Firstmate no haya demostrado; se preservan gates de seguridad y aceptación propios de Homeserver sin imponer agentes QA o Reviewer separados; el Operador acepta este cambio en la conversación del 2026-09-08.'
---
# 0037. Seleccionar modelos existentes con firstmate

Reemplaza a 0034-reemplazar-rutas-copilot-de-factory-por-openai-codex.

## Contexto
ADR 0034 conserva una política útil de exclusión de Copilot, pero su binding canónico de QA y su independencia obligatoria chocan con la decisión del Operador de usar Firstmate nativo; el Operador permite que Firstmate elija modelos y agentes existentes para distribuir costos y cuota.

## Decisión
Permitir a Firstmate seleccionar por tarea y cuota entre modelos, proveedores y agentes ya existentes y verificados, sin nuevas cuentas, proveedores, suscripciones ni restaurar rutas Copilot; retirar para este handover el binding obligatorio e independencia de QA heredados y no fijar el modelo de Mission Control de ADR 0032; registrar el harness, proveedor, modelo y esfuerzo realmente usados y tratar capacidad o cuota desconocida como desconocida, nunca como disponible.

## Alternativas descartadas
Mantener asignaciones fijas por rol se descarta por la selección dinámica autorizada. Añadir proveedores o convertir modelos a otra familia silenciosamente se descarta porque distribuir costo no autoriza ampliar acceso. Sondear reiteradamente rutas fallidas se descarta por consumo sin evidencia de recuperación.

## Consecuencias
La exclusión de Copilot y la protección de credenciales de ADR 0034 se conservan; la selección ocurre dentro del inventario comprobado sin modificar secretos globales ni prometer failover automático de cuota que Firstmate no haya demostrado; se preservan gates de seguridad y aceptación propios de Homeserver sin imponer agentes QA o Reviewer separados; el Operador acepta este cambio en la conversación del 2026-09-08.

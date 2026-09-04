---
tipo: adr
estado: accepted
fecha: '2026-08-27'
contexto: 'Sweep consolida tres workflows globales y depende de tres agentes hoy gestionados por chezmoi con contratos específicos de Claude; separar sus propietarios produciría instalaciones parciales y deriva.'
decision: 'Este repositorio será la fuente canónica de sweep y de sus tres agentes dentro de skills/sweep/agents, con adaptadores separados para Claude y Pi; se distribuirán mediante symlinks a las rutas globales de cada runtime después de retirar explícitamente el ownership de chezmoi.'
alternativas: 'Crear agents/ en la raíz: descartado porque rompe el contrato autocontenido de cada skill. Mantener agentes en chezmoi: descartado porque divide ownership y portabilidad. Reutilizar los archivos Claude directamente en Pi: descartado por incompatibilidad de herramientas, modelos y entrega de resultados.'
consecuencias: 'La migración exigirá inventario, backups, aprobación ligada a digest, chezmoi forget antes de reemplazar rutas, adaptadores por runtime, verificación de discovery y restore drill; OpenCode descubrirá el skill pero no recibirá agentes hasta un diseño específico.'
pendientes: ""
---
# 0018. Distribuir sweep con adaptadores de agente

## Contexto
Sweep consolida tres workflows globales y depende de tres agentes hoy gestionados por chezmoi con contratos específicos de Claude; separar sus propietarios produciría instalaciones parciales y deriva.

## Decisión
Este repositorio será la fuente canónica de sweep y de sus tres agentes dentro de skills/sweep/agents, con adaptadores separados para Claude y Pi; se distribuirán mediante symlinks a las rutas globales de cada runtime después de retirar explícitamente el ownership de chezmoi.

## Alternativas descartadas
Crear agents/ en la raíz: descartado porque rompe el contrato autocontenido de cada skill. Mantener agentes en chezmoi: descartado porque divide ownership y portabilidad. Reutilizar los archivos Claude directamente en Pi: descartado por incompatibilidad de herramientas, modelos y entrega de resultados.

## Consecuencias
La migración exigirá inventario, backups, aprobación ligada a digest, chezmoi forget antes de reemplazar rutas, adaptadores por runtime, verificación de discovery y restore drill; OpenCode descubrirá el skill pero no recibirá agentes hasta un diseño específico.

## Pendientes
Evaluar soporte de agentes OpenCode en una decisión posterior.

---
tipo: adr
estado: accepted
fecha: '2026-08-26'
contexto: 'La lógica ADR (detección, bootstrap, esquema, formato, validación) vivía en el output style mentor-telemetria, visible solo para Claude Code; decision-calibrator y otros skills la habrían duplicado.'
decision: 'Un skill adr, alojado en skills/adr y enlazado desde cada harness, es el único dueño de la política y del esquema ADR; la mecánica va en adr.sh sobre rootline (propose/accept/supersede/list, idempotente por slug, --dry-run). Output style y decision-calibrator solo invocan el skill. No existe almacén alternativo: sin directorio ADR habilitado y con rechazo del usuario, no se registra.'
alternativas: 'Mantener todo en el output style: no portable a Pi/OpenCode. Subcomando adr en rootline: acopla una herramienta genérica de esquemas a un tipo de documento. Fallback a engram: descartado explícitamente por el usuario para evitar registros fuera del repositorio.'
consecuencias: 'El esquema añade alternativas, pendientes y superseded_by como campos opcionales; el script exige alternativas en registros nuevos. El output style pierde su asset adr.stem. Los consumidores dependen de rootline instalado.'
pendientes: ""
---
# 0015. Centralizar logica adr en skill sobre rootline

## Contexto
La lógica ADR (detección, bootstrap, esquema, formato, validación) vivía en el output style mentor-telemetria, visible solo para Claude Code; decision-calibrator y otros skills la habrían duplicado.

## Decisión
Un skill adr, alojado en skills/adr y enlazado desde cada harness, es el único dueño de la política y del esquema ADR; la mecánica va en adr.sh sobre rootline (propose/accept/supersede/list, idempotente por slug, --dry-run). Output style y decision-calibrator solo invocan el skill. No existe almacén alternativo: sin directorio ADR habilitado y con rechazo del usuario, no se registra.

## Alternativas descartadas
Mantener todo en el output style: no portable a Pi/OpenCode. Subcomando adr en rootline: acopla una herramienta genérica de esquemas a un tipo de documento. Fallback a engram: descartado explícitamente por el usuario para evitar registros fuera del repositorio.

## Consecuencias
El esquema añade alternativas, pendientes y superseded_by como campos opcionales; el script exige alternativas en registros nuevos. El output style pierde su asset adr.stem. Los consumidores dependen de rootline instalado.

## Pendientes
Validar el skill en Pi y OpenCode; decidir si se corrige fecha sin comillas en 0007 y 0008.

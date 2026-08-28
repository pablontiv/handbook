---
tipo: adr
estado: accepted
fecha: '2026-08-28'
contexto: 'La especificación Waywarden aprobada concreta los contratos de distribución segura que ADR 0019 dejó genéricos y corrige su rango de Go y su atribución de release a Crossbeam.'
decision: 'Adoptar docs/superpowers/specs/2026-08-28-waywarden-skill-distribution-design.md como autoridad normativa de Waywarden v1: Go exacto 1.26.0, Cobra 1.10.2, Picokit 1.0.0 selectivo, despliegues físicos con bindings de runtime, planes canónicos digest-bound, estado transaccional, uninstall por identidad, restore separado, verificación Pi/OpenCode/Claude, Crossbeam sólo como baseline CI y release propio con GoReleaser 2.18.0 para seis binarios.'
alternativas: 'Mantener ADR 0019 sin precisión se descarta porque permitiría implementaciones incompatibles; editar ADR 0019 in place se descarta porque el registro aceptado es append-only; volver a TypeScript, Rust o copiar skills se descarta por las razones ya registradas y por romper la autonomía aprobada.'
consecuencias: 'ADR 0019 queda superseded; ADR 0016 conserva únicamente evidencia histórica de ownership y separación uninstall/restore; ADR 0017 sigue gobernando OpenCode; toda implementación requiere un plan derivado de la especificación aprobada y validación multiplataforma.'
---
# 0020. Cerrar contrato waywarden v1

Reemplaza a 0019-gobernar-distribucion-con-cli-go.

## Contexto
La especificación Waywarden aprobada concreta los contratos de distribución segura que ADR 0019 dejó genéricos y corrige su rango de Go y su atribución de release a Crossbeam.

## Decisión
Adoptar docs/superpowers/specs/2026-08-28-waywarden-skill-distribution-design.md como autoridad normativa de Waywarden v1: Go exacto 1.26.0, Cobra 1.10.2, Picokit 1.0.0 selectivo, despliegues físicos con bindings de runtime, planes canónicos digest-bound, estado transaccional, uninstall por identidad, restore separado, verificación Pi/OpenCode/Claude, Crossbeam sólo como baseline CI y release propio con GoReleaser 2.18.0 para seis binarios.

## Alternativas descartadas
Mantener ADR 0019 sin precisión se descarta porque permitiría implementaciones incompatibles; editar ADR 0019 in place se descarta porque el registro aceptado es append-only; volver a TypeScript, Rust o copiar skills se descarta por las razones ya registradas y por romper la autonomía aprobada.

## Consecuencias
ADR 0019 queda superseded; ADR 0016 conserva únicamente evidencia histórica de ownership y separación uninstall/restore; ADR 0017 sigue gobernando OpenCode; toda implementación requiere un plan derivado de la especificación aprobada y validación multiplataforma.

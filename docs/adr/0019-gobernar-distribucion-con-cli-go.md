---
tipo: adr
estado: superseded
fecha: '2026-08-28'
contexto: 'ADR 0016 estableció ownership, symlinks directos y un futuro instalador TypeScript; el diseño aprobado de #10 requiere binarios autónomos, una frontera CLI JSON y una north star Go compatible con Picokit, Cobra y Crossbeam ya usados en los repositorios relacionados.'
decision: 'Conservar la clasificación de ownership, la distribución mediante symlinks y la separación uninstall/restore de ADR 0016, pero implementar la CLI de distribución en Go 1.26 o posterior con Cobra, reutilización selectiva de Picokit, adaptadores de filesystem específicos por plataforma, contratos JSON versionados y releases multiplataforma mediante Crossbeam y GoReleaser; futuras migraciones de helpers a Go serán issues independientes.'
alternativas: 'TypeScript sobre Node, Bun o Deno se descarta porque exige un runtime instalado o embebido; Rust se descarta por costo cognitivo desproporcionado; flag.FlagSet sin framework se descarta porque Cobra ya es la convención probada; un binario monolítico que absorba las skills se descarta porque rompería su autonomía.'
consecuencias: 'El repositorio incorpora toolchain Go y artefactos binarios para Linux, macOS y Windows en amd64 y arm64; Picokit aporta utilidades pero no autoridad transaccional; ADR 0017 sigue gobernando la verificación OpenCode; el nombre final de la CLI no altera estos contratos.'
superseded_by: 0020-cerrar-contrato-waywarden-v1
---
# 0019. Gobernar distribucion con cli go

Reemplaza a 0016-gobernar-propiedad-y-distribucion-de-skills-globales.

## Contexto
ADR 0016 estableció ownership, symlinks directos y un futuro instalador TypeScript; el diseño aprobado de #10 requiere binarios autónomos, una frontera CLI JSON y una north star Go compatible con Picokit, Cobra y Crossbeam ya usados en los repositorios relacionados.

## Decisión
Conservar la clasificación de ownership, la distribución mediante symlinks y la separación uninstall/restore de ADR 0016, pero implementar la CLI de distribución en Go 1.26 o posterior con Cobra, reutilización selectiva de Picokit, adaptadores de filesystem específicos por plataforma, contratos JSON versionados y releases multiplataforma mediante Crossbeam y GoReleaser; futuras migraciones de helpers a Go serán issues independientes.

## Alternativas descartadas
TypeScript sobre Node, Bun o Deno se descarta porque exige un runtime instalado o embebido; Rust se descarta por costo cognitivo desproporcionado; flag.FlagSet sin framework se descarta porque Cobra ya es la convención probada; un binario monolítico que absorba las skills se descarta porque rompería su autonomía.

## Consecuencias
El repositorio incorpora toolchain Go y artefactos binarios para Linux, macOS y Windows en amd64 y arm64; Picokit aporta utilidades pero no autoridad transaccional; ADR 0017 sigue gobernando la verificación OpenCode; el nombre final de la CLI no altera estos contratos.

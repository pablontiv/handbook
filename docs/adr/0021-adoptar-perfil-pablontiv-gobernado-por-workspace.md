---
tipo: adr
estado: accepted
fecha: '2026-09-03'
contexto: 'La identidad del repositorio como handbook portable requiere un perfil personal reusable basado en engineering-handbook v1.4, una instancia dogfood y una única autoridad de configuración y conocimiento bajo .workspace; la decisión previa fijó docs/adr como almacén canónico.'
decision: 'Adoptar un perfil pablontiv de madurez progresiva: PROFILE.md especializa las dieciséis secciones de engineering-handbook v1.4; bootstrap.md guía la adopción; .workspace/config.yaml contiene en prosa las capas workspace, groups y repositories; .workspace/docs concentra ADRs, specs y planes gobernados por Rootline; Backscroll es fuente obligatoria de memoria; Pi es el único runtime inicial; todas las herramientas oficiales se enrutan por condición y no admiten sustitución.'
alternativas: 'Mantener docs como autoridad se descarta porque contradice el control plane central. Empezar con executors y schemas deterministas se descarta por formalización prematura. Cargar PROFILE.md como configuración operativa se descarta porque el perfil es referencia y la instancia vive en .workspace.'
consecuencias: 'Los registros históricos se trasladan preservando contenido; ADR, Superpowers, README, AGENTS, CI y pruebas deben resolver .workspace; los controles comienzan en prosa y migran gradualmente a bindings deterministas; Rootline y Backscroll pasan de integración opcional a dependencias obligatorias del perfil.'
---
# 0021. Adoptar perfil pablontiv gobernado por workspace

Reemplaza a 0002-adopt-versioned-adr-and-pull-request-governance.

## Contexto
La identidad del repositorio como handbook portable requiere un perfil personal reusable basado en engineering-handbook v1.4, una instancia dogfood y una única autoridad de configuración y conocimiento bajo .workspace; la decisión previa fijó docs/adr como almacén canónico.

## Decisión
Adoptar un perfil pablontiv de madurez progresiva: PROFILE.md especializa las dieciséis secciones de engineering-handbook v1.4; bootstrap.md guía la adopción; .workspace/config.yaml contiene en prosa las capas workspace, groups y repositories; .workspace/docs concentra ADRs, specs y planes gobernados por Rootline; Backscroll es fuente obligatoria de memoria; Pi es el único runtime inicial; todas las herramientas oficiales se enrutan por condición y no admiten sustitución.

## Alternativas descartadas
Mantener docs como autoridad se descarta porque contradice el control plane central. Empezar con executors y schemas deterministas se descarta por formalización prematura. Cargar PROFILE.md como configuración operativa se descarta porque el perfil es referencia y la instancia vive en .workspace.

## Consecuencias
Los registros históricos se trasladan preservando contenido; ADR, Superpowers, README, AGENTS, CI y pruebas deben resolver .workspace; los controles comienzan en prosa y migran gradualmente a bindings deterministas; Rootline y Backscroll pasan de integración opcional a dependencias obligatorias del perfil.

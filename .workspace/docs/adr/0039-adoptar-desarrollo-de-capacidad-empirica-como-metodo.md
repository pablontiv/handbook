---
tipo: adr
estado: accepted
fecha: '2026-09-15'
contexto: 'La práctica PoC-first observada en Homeserver, Backscroll y Firstmate y el PoC A/B ejecutado en Handbook demostraron valor de un flujo empírico opt-in; el skill evidence-driven-development no se usa y no mostró uplift propio, y el Operador exige cero compatibilidad.'
decision: 'Crear la familia top-level methods con empirical-capability-development como único owner activo del método; cada repositorio opta mediante su workspace config y reglas locales; retirar por completo el skill evidence-driven-development, su routing, documentación y CI, sin alias, shim, fallback ni adaptador; publicar el cambio como perfil pablontiv v2 y tratar runtimes como integraciones no autoritativas.'
alternativas: 'Extender o conservar el skill se descarta por resultados operativos insuficientes y autoridad duplicada; mantener compatibilidad se descarta por decisión explícita del Operador y costo permanente; documentarlo solo en el perfil se descarta porque limitaría una metodología portable; imponerlo en AGENTS se descarta porque dejaría de ser opt-in.'
consecuencias: 'El Handbook gana una familia portable con ownership explícito y tests propios; la adopción es breaking y eleva el perfil a v2; Git preserva la historia del skill retirado; la limpieza de proyecciones globales ocurre solo después del merge mediante un plan destructivo separado, respaldado, verificado y aprobado por digest.'
pendientes: ""
---
# 0039. Adoptar desarrollo de capacidad empirica como metodo

## Contexto
La práctica PoC-first observada en Homeserver, Backscroll y Firstmate y el PoC A/B ejecutado en Handbook demostraron valor de un flujo empírico opt-in; el skill evidence-driven-development no se usa y no mostró uplift propio, y el Operador exige cero compatibilidad.

## Decisión
Crear la familia top-level methods con empirical-capability-development como único owner activo del método; cada repositorio opta mediante su workspace config y reglas locales; retirar por completo el skill evidence-driven-development, su routing, documentación y CI, sin alias, shim, fallback ni adaptador; publicar el cambio como perfil pablontiv v2 y tratar runtimes como integraciones no autoritativas.

## Alternativas descartadas
Extender o conservar el skill se descarta por resultados operativos insuficientes y autoridad duplicada; mantener compatibilidad se descarta por decisión explícita del Operador y costo permanente; documentarlo solo en el perfil se descarta porque limitaría una metodología portable; imponerlo en AGENTS se descarta porque dejaría de ser opt-in.

## Consecuencias
El Handbook gana una familia portable con ownership explícito y tests propios; la adopción es breaking y eleva el perfil a v2; Git preserva la historia del skill retirado; la limpieza de proyecciones globales ocurre solo después del merge mediante un plan destructivo separado, respaldado, verificado y aprobado por digest.

## Pendientes
ADR 0038 permanece reservada por el PR 55 y deberá ajustarse antes de cualquier entrega posterior; validar escenarios adicionales de falso target disposable, presión multi-turn y ejecución real de herramientas antes de aceptar el método.

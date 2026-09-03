---
tipo: adr
estado: superseded
fecha: '2026-08-26'
contexto: 'Los skills globales están repartidos entre copias sueltas, symlinks, repositorios de producto y gestores externos; se verificó deriva entre fuentes y runtimes, incluida una copia obsoleta de model-optimizer.'
decision: 'Este repositorio será la fuente canónica sólo de skills independientes, globales, portables y publicables; los skills acoplados permanecen con su producto, los locales con su repositorio y los de terceros con su gestor. Inicialmente se instalarán manualmente mediante symlinks directos desde skills/<name> a ~/.agents/skills para Pi y OpenCode y a ~/.claude/skills para Claude, sin duplicados runtime-específicos. Un instalador futuro se implementará en TypeScript con inventory, plan, apply, verify, uninstall y restore; uninstall retirará sólo symlinks gestionados y restore recuperará backups por separado.'
alternativas: 'Centralizar todos los skills: descartado porque vendoriza terceros y desacopla contratos de producto. Mantener sólo enlaces sin resolver propiedad: descartado porque conserva fuentes implícitas y deriva. Sincronizar por copia: descartado porque reproduce el fallo observado. Implementar ahora o usar Python/shell: descartado para limitar alcance inicial y respetar la dirección TypeScript multiplataforma.'
consecuencias: 'Las migraciones serán graduales, una skill por PR y con TDD cuando cambie comportamiento; las sustituciones manuales exigirán inventario, backup verificado y aprobación ligada al estado observado. El futuro instalador añadirá una dependencia de toolchain TypeScript, pero permitirá una operación portable, auditable y reversible sin confundir uninstall con restore.'
pendientes: ""
superseded_by: 0022-ampliar-repositorio-a-handbook-de-trabajo
---
# 0016. Gobernar propiedad y distribucion de skills globales

## Contexto

Los skills globales están repartidos entre copias sueltas, symlinks, repositorios de producto y gestores externos; se verificó deriva entre fuentes y runtimes, incluida una copia obsoleta de model-optimizer.

## Decisión

Este repositorio será la fuente canónica sólo de skills independientes, globales, portables y publicables; los skills acoplados permanecen con su producto, los locales con su repositorio y los de terceros con su gestor. Inicialmente se instalarán manualmente mediante symlinks directos desde skills/<name> a ~/.agents/skills para Pi y OpenCode y a ~/.claude/skills para Claude, sin duplicados runtime-específicos. Un instalador futuro se implementará en TypeScript con inventory, plan, apply, verify, uninstall y restore; uninstall retirará sólo symlinks gestionados y restore recuperará backups por separado.

## Alternativas descartadas

Centralizar todos los skills: descartado porque vendoriza terceros y desacopla contratos de producto. Mantener sólo enlaces sin resolver propiedad: descartado porque conserva fuentes implícitas y deriva. Sincronizar por copia: descartado porque reproduce el fallo observado. Implementar ahora o usar Python/shell: descartado para limitar alcance inicial y respetar la dirección TypeScript multiplataforma.

## Consecuencias

Las migraciones serán graduales, una skill por PR y con TDD cuando cambie comportamiento; las sustituciones manuales exigirán inventario, backup verificado y aprobación ligada al estado observado. El futuro instalador añadirá una dependencia de toolchain TypeScript, pero permitirá una operación portable, auditable y reversible sin confundir uninstall con restore.

## Pendientes

Definir durante el diseño del instalador el framework CLI, el formato versionado de planes y manifests, y la ubicación del paquete TypeScript.

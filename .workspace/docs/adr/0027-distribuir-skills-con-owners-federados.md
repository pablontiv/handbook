---
tipo: adr
estado: superseded
fecha: '2026-09-04'
contexto: 'Los runtimes globales contienen skills duplicados, huérfanos y gestionados externamente; centralizarlos todos en handbook rompería ownership de producto y procedencia upstream.'
decision: 'Adoptar ownership federado: cada skill permanece en el repositorio que controla su contrato; handbook absorbe sólo skills globales portables y publicables sin otro owner; un manifiesto central declara owner y proyección; los skills propios se consumen por symlinks directos y los upstreams externos mediante copia canónica gestionada con lock bajo ~/.agents y enlaces de runtime.'
alternativas: 'Centralizar todos los skills en handbook se descarta porque crea forks y desacopla contratos de producto. Mantener copias por runtime se descarta porque permite deriva. Clonar cada upstream y enlazarlo directamente se descarta porque impone mantenimiento manual innecesario frente a un gestor con procedencia y lock. Usar el gestor también para skills propios se descarta porque intercala copias entre el owner Git y el runtime.'
consecuencias: 'Cada skill tendrá un único owner explícito aunque pueda tener varias proyecciones; Pi y OpenCode compartirán ~/.agents/skills y Claude recibirá enlaces equivalentes; las migraciones requerirán fuente canónica, backup, aprobación ligada a digest, verificación de discovery y rollback; las copias externas gestionadas no podrán editarse localmente.'
pendientes: ""
superseded_by: 0028-distribuir-skills-sin-registro-inicial
---
# 0027. Distribuir skills con owners federados

## Contexto
Los runtimes globales contienen skills duplicados, huérfanos y gestionados externamente; centralizarlos todos en handbook rompería ownership de producto y procedencia upstream.

## Decisión
Adoptar ownership federado: cada skill permanece en el repositorio que controla su contrato; handbook absorbe sólo skills globales portables y publicables sin otro owner; un manifiesto central declara owner y proyección; los skills propios se consumen por symlinks directos y los upstreams externos mediante copia canónica gestionada con lock bajo ~/.agents y enlaces de runtime.

## Alternativas descartadas
Centralizar todos los skills en handbook se descarta porque crea forks y desacopla contratos de producto. Mantener copias por runtime se descarta porque permite deriva. Clonar cada upstream y enlazarlo directamente se descarta porque impone mantenimiento manual innecesario frente a un gestor con procedencia y lock. Usar el gestor también para skills propios se descarta porque intercala copias entre el owner Git y el runtime.

## Consecuencias
Cada skill tendrá un único owner explícito aunque pueda tener varias proyecciones; Pi y OpenCode compartirán ~/.agents/skills y Claude recibirá enlaces equivalentes; las migraciones requerirán fuente canónica, backup, aprobación ligada a digest, verificación de discovery y rollback; las copias externas gestionadas no podrán editarse localmente.

## Pendientes
Definir y aprobar el esquema del manifiesto, los lotes de migración y los contratos de verificación antes de modificar rutas runtime.

---
tipo: adr
estado: accepted
fecha: "2026-08-28"
contexto: "Task 5 introduce planes de distribución que deben derivarse de artefactos de inventario canónicos, con digest de aprobación vinculante y sin leer estado ambiental durante la planificación."
decision: "La construcción del plan debe ser una función pura sobre el inventario canónico y las banderas explícitas; solo el adaptador de comando puede leer el archivo de inventario y publicar el artefacto mediante el publisher read-only."
alternativas: "Leer manifests, ledgers, roots de runtime o entorno dentro del planner fue descartado porque mezclaría descubrimiento con decisión aprobable. Generar IDs de operación o almacenamiento en el plan fue descartado porque pertenece a tareas posteriores de aplicación y verificación."
consecuencias: "Los planes son reproducibles byte a byte, embeben el inventario completo, enlazan inventory_digest a los bytes canónicos de entrada y enlazan approval_digest al payload canónico. Los blockers clasificados pueden devolver error y artefacto de plan simultáneamente para que la CLI publique evidencia aprobable o bloqueada sin mutar estado."
pendientes: "Las tareas de aplicación y verificación deben consumir estos planes sin introducir IDs, locks o efectos de estado en la fase de planificación."
---

## Contexto

Task 5 requiere que `cmd/waywarden plan` consuma un artefacto de inventario producido previamente y emita un plan canónico. El plan debe ser aprobable mediante digest, por lo que su contenido no puede depender de relojes, aleatoriedad, variables de entorno, manifests, ledgers ni lecturas de roots en tiempo de planificación.

Además, algunos errores clasificados, como backups faltantes o capacidades no soportadas ya observadas como blockers, deben conservar una respuesta de plan para que la CLI pueda publicar un artefacto bloqueado. Esto exige separar el cálculo determinístico del plan de la publicación del resultado.

## Decisión

`BuildPlan` debe operar solamente sobre `InventoryArtifact` y `Options` explícitas de intención/selector. La decodificación exige JSON canónico estricto y schema de inventario. El payload del plan embebe el inventario completo, calcula `inventory_digest` desde los bytes canónicos exactos de entrada cuando el inventario no cambió, y calcula `approval_digest` como SHA-256 del payload canónico.

La lectura de `--inventory`, la escritura a stdout y la publicación no-replace a `--out` quedan fuera de `BuildPlan`, en el servicio/adaptador de comando. Esa frontera puede devolver un `ArtifactResult` junto con un error clasificado cuando el plan es bloqueado pero publicable.

## Alternativas descartadas

- Leer manifests, ledgers, roots de runtime o entorno desde el planner: descartado porque haría que el plan dependiera de estado ambiental y no solo del artefacto de inventario aprobado.
- Generar `operation_id`, `installation_id`, `backup_set_id`, recibos, verificaciones o timestamps durante la planificación: descartado porque esos identificadores pertenecen a fases posteriores de mutación/verificación.
- Fallar sin artefacto ante blockers seguros: descartado porque impediría publicar evidencia determinística de por qué el plan está bloqueado.

## Consecuencias

Los planes son determinísticos y auditables. La CLI puede publicar planes exitosos o bloqueados sin adquirir locks ni mutar estado de distribución. Las tareas posteriores deben tratar el plan como entrada aprobable y no reabrir la planificación para incorporar estado ambiental adicional.

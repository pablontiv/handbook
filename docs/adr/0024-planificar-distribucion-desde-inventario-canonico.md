---
tipo: adr
estado: accepted
fecha: "2026-08-28"
contexto: "Task 5 introduce planes de distribución que deben derivarse de artefactos de inventario canónicos, con digest de aprobación vinculante, sin leer estado ambiental durante la planificación pura y con publicación de archivo confinada a raíces demostradas."
decision: "La construcción del plan debe ser una función pura sobre un InventoryArtifact opaco decodificado desde bytes canónicos exactos y banderas explícitas; solo el servicio/adaptador de comando puede leer entorno para publicación a archivo, derivar raíces prohibidas completas desde la unión deduplicada de vistas de inventario canónico y publicar mediante el publisher read-only."
alternativas: "Leer manifests, ledgers, roots de runtime o entorno dentro del planner fue descartado porque mezclaría descubrimiento con decisión aprobable. Re-serializar un inventario mutable del llamador fue descartado porque permitiría cambiar silenciosamente la entrada aprobada. Inferir raíces fuente padre no observadas fue descartado porque excedería la evidencia exacta del inventario."
consecuencias: "Los planes son reproducibles byte a byte, embeben el inventario completo decodificado, enlazan inventory_digest a los bytes canónicos exactos aceptados y enlazan approval_digest al payload canónico. La publicación a archivo falla cerrada si la evidencia total de raíces fuente o runtime queda vacía, falta, es relativa o no comprobable, y rechaza destinos bajo cualquier raíz fuente, runtime, estado o lock probada."
pendientes: "Las tareas de aplicación y verificación deben consumir estos planes sin introducir IDs, locks o efectos de estado en la fase de planificación."
---

## Contexto

Task 5 requiere que `cmd/waywarden plan` consuma un artefacto de inventario producido previamente y emita un plan canónico. El plan debe ser aprobable mediante digest, por lo que su contenido no puede depender de relojes, aleatoriedad, variables de entorno, manifests, ledgers ni lecturas de roots en tiempo de planificación pura.

Además, algunos errores clasificados, como backups faltantes o capacidades no soportadas ya observadas como blockers, deben conservar una respuesta de plan para que la CLI pueda publicar un artefacto bloqueado. Esto exige separar el cálculo determinístico del plan de la publicación del resultado.

La publicación a archivo agrega una frontera distinta: aunque el plan sea puro, el destino de salida no puede escribirse dentro de directorios gobernados por Waywarden ni dentro de raíces que contienen fuentes, runtimes, estado o coordinación de locks. Esa validación pertenece al servicio/adaptador con efectos, no a `BuildPlan`.

## Decisión

`BuildPlan` debe operar solamente sobre `InventoryArtifact` y `Options` explícitas de intención/selector. La decodificación exige JSON canónico estricto y schema de inventario. `InventoryArtifact` es opaco para llamadores: conserva una copia interna del inventario decodificado y los bytes crudos canónicos aceptados. Si se expone el inventario, se entrega una copia, de modo que el llamador no pueda mutar la entrada y provocar una reserialización silenciosa como si fuera otro artefacto aprobado.

El payload del plan embebe el inventario completo decodificado desde el artefacto opaco. `payload.inventory_digest` se calcula siempre desde los bytes crudos canónicos exactos aceptados por `DecodeInventoryArtifact`; no se recalcula desde una estructura mutable del llamador. `approval_digest` se calcula como SHA-256 del payload canónico.

La lectura de `--inventory`, la escritura a stdout y la publicación no-replace a `--out` quedan fuera de `BuildPlan`, en el servicio/adaptador de comando. Para `--out -`, el servicio no lee entorno para derivar raíces de publicación. Para salida a archivo, el servicio lee el entorno mediante el adaptador, selecciona la raíz de estado desde `--state-root` absoluto o desde el default de plataforma, obtiene la raíz privada de locks con `OwnerPrivateLockRoot`, toma raíces fuente desde la unión deduplicada de `inventory.sources[].source_identity` e `inventory.deployments[].source_identity`, y toma raíces runtime desde la unión deduplicada de `inventory.runtime_bindings[].root` y cada `inventory.deployments[].runtime_bindings[].root`. Las vistas duplicadas del inventario externo no se consideran necesariamente consistentes. Si la evidencia total de raíces fuente o runtime queda vacía, falta, es relativa o no comprobable, la publicación falla cerrada con `runtime_contract_missing` antes de llamar al publisher no-replace; un destino bajo una raíz prohibida falla como precondición segura.

## Alternativas descartadas

- Leer manifests, ledgers, roots de runtime o entorno desde el planner: descartado porque haría que el plan dependiera de estado ambiental y no solo del artefacto de inventario aprobado.
- Generar `operation_id`, `installation_id`, `backup_set_id`, recibos, verificaciones o timestamps durante la planificación: descartado porque esos identificadores pertenecen a fases posteriores de mutación/verificación.
- Fallar sin artefacto ante blockers seguros: descartado porque impediría publicar evidencia determinística de por qué el plan está bloqueado.
- Clasificar blockers de capacidad por `severity == "error"`: descartado porque severidad no identifica contratos runtime faltantes; la clasificación se hace por el código tipado `runtime_contract_missing`.
- Derivar raíces fuente mediante padres comunes de `source_identity`: descartado porque introduciría raíces no probadas por el inventario exacto.

## Consecuencias

Los planes son determinísticos y auditables. La CLI puede publicar planes exitosos o bloqueados sin adquirir locks ni mutar estado de distribución. Las tareas posteriores deben tratar el plan como entrada aprobable y no reabrir la planificación para incorporar estado ambiental adicional.

La publicación a archivo queda protegida por raíces prohibidas completas sin contaminar `BuildPlan` con efectos ambientales. La protección usa todas las raíces probadas por cualquiera de las vistas canónicas disponibles y falla cerrada cuando una clase completa de evidencia fuente o runtime no existe o no es absoluta. Esto conserva la frontera pura para aprobación y concentra la seguridad de salida en el adaptador que ya posee las garantías de publicación absoluta, no-follow y no-replace.

# Especificación de Forma de Trabajo

**Versión:** 1.4

**Estado:** propuesta para revisión humana

**Alcance:** del trabajo asignado a su entrega, verificación posterior y captura de conocimiento

**Audiencia:** personas y agentes que trabajan sobre uno o más repositorios agrupados en un workspace

---

## 1. Propósito

Este documento define un método de trabajo reproducible para workspaces heterogéneos. El método separa dos responsabilidades:

1. **El Handbook define el contrato genérico:** fases, invariantes, precedencia, gates y evidencia mínima.
2. **El workspace define la ejecución concreta:** repositorios administrados, comandos, fuentes, estrategia Git, pre-checks, acceptance checks, delivery gates y post-checks.

El Handbook no prescribe herramientas, proveedores, comandos ni topologías concretas. Esas decisiones pertenecen a la configuración central del workspace.

Las palabras **DEBE**, **NO DEBE**, **DEBERÍA** y **PUEDE** expresan requisitos normativos.

## 2. Principios de diseño

### 2.1 Configuración central, ejecución distribuida

Toda la configuración de control vive bajo `.workspace/config/`. Los repositorios hijos contienen código, scripts y capacidades ejecutables, pero no son la autoridad para descubrir el método de trabajo aplicable.

Un control central puede ejecutar un comando dentro de un repositorio. Eso no convierte al archivo que implementa el comando en configuración: el control sigue definido centralmente y el repositorio solo expone una interfaz ejecutable.

### 2.2 Controles genéricos, bindings concretos

El contrato distingue:

- **control genérico:** qué condición debe verificarse y en qué fase;
- **binding concreto:** qué comando, consulta o gate satisface ese control para un repositorio;
- **evidencia:** qué resultado demuestra que el control pasó, falló o no pudo verificarse.

El Handbook puede mencionar clases de controles —por ejemplo, pre-check, acceptance, delivery o post-check—, pero NO DEBE convertir una herramienta o proveedor particular en requisito universal.

### 2.3 Fallo cerrado

La falta de configuración, acceso, evidencia o resolución inequívoca no equivale a éxito. Cuando una condición obligatoria no puede verificarse, el estado es `unknown` y el trabajo se detiene antes de la siguiente mutación o entrega afectada.

### 2.4 Trazabilidad sin navegación implícita

Una persona o agente DEBE poder obtener desde `.workspace/config/`:

- qué repositorios administra el workspace;
- qué configuración efectiva aplica a cada uno;
- qué controles se ejecutan antes y después;
- qué reglas fueron heredadas y cuáles sobrescritas;
- contra qué revisión del repositorio se verificaron los bindings.

La resolución de la configuración efectiva y de los controles que deben ejecutarse NO DEBE depender de seguir enlaces hacia archivos de steering o configuración en repositorios hijos: el control plane central debe ser suficiente para determinar qué aplica.

La configuración central DEBERÍA mantener referencias explícitas a artefactos de los repositorios hijos cuando sirvan para evitar duplicación o relacionar conceptos, ideas, decisiones, implementación y evidencia. Estas referencias no transfieren autoridad al artefacto enlazado ni autorizan inferir controles ausentes. Sus destinos y, cuando corresponda, sus anchors y ciclos DEBEN validarse mediante un control declarado; Rootline es el binding recomendado para esa validación. Si una referencia requerida no puede resolverse inequívocamente, su estado es `unknown` y se aplica fallo cerrado.

## 3. Modelo de workspace

### 3.1 Estructura

```text
<workspace>/
├── .workspace/
│   ├── config/                    # control plane central y versionado
│   │   ├── workspace.yaml         # defaults y política global
│   │   ├── groups/                # configuración compartida por grupo
│   │   │   └── <group>.yaml
│   │   ├── repos/                 # identidad y overrides por repositorio
│   │   │   └── <repo-id>.yaml
│   │   └── effective/             # vistas resueltas; generadas, no autoritativas
│   │       └── <repo-id>.yaml
│   ├── docs/                      # conocimiento durable del workspace
│   └── worktrees/                 # aislamiento administrado por el workspace
└── <repositorios administrados>/
```

`workspace.yaml` es la autoridad del catálogo canónico de clases de artefacto y de los aliases explícitamente permitidos.

`.workspace/config/` DEBE tener historial versionado. El medio de respaldo o remoto es configurable, pero la procedencia y los cambios de la configuración DEBEN ser auditables.

### 3.2 Identidad canónica de repositorio

Cada repositorio administrado DEBE tener un `repo_id` estable y una ruta física canónica. Aliases, symlinks y worktrees derivados no crean nuevas identidades.

Un repositorio que no tenga entrada efectiva en el control plane puede explorarse en modo de solo lectura, pero NO DEBE recibir mutaciones ni entregas hasta quedar clasificado.

### 3.3 Grupos

Un grupo representa repositorios que comparten controles o defaults. No implica equipo, propiedad ni estructura organizacional.

Un repositorio PUEDE pertenecer a un grupo de configuración. Las excepciones se expresan como overrides centrales por `repo_id`, no como copias de política dentro del repositorio hijo.

## 4. Resolución de configuración

### 4.1 Precedencia

La configuración efectiva se resuelve en este orden:

```text
workspace defaults → group → repository
```

La capa más específica prevalece únicamente en los campos que declara.

### 4.2 Semántica de merge

- Los escalares de una capa más específica reemplazan a los anteriores.
- Los mapas se combinan recursivamente.
- Las listas se reemplazan completas; no se concatenan implícitamente.
- Una lista vacía (`[]`) significa “declaradamente sin controles de esta clase”.
- Un valor ausente significa “heredar”.
- Un valor `unknown` significa “no resuelto” y activa fallo cerrado cuando afecta una fase obligatoria.
- Las reglas libres NO PUEDEN debilitar un invariante del Handbook.

Las clases de artefacto DEBEN resolverse contra el catálogo autoritativo definido en `workspace.yaml`. La autorización usa coincidencia exacta entre identificadores canónicos; aliases, equivalencias o patrones solo se permiten cuando están declarados explícitamente en esa configuración y NO DEBEN inferirse.

### 4.3 Configuración efectiva

Antes de iniciar trabajo mutante, el sistema DEBE producir o mostrar una vista efectiva que incluya:

- valores finales;
- origen de cada valor (`workspace`, `group` o `repository`);
- revisión de la configuración;
- revisión observada del repositorio;
- warnings y campos `unknown`.

`effective/` es una vista derivada. Editarla directamente no modifica la autoridad.

### 4.4 Drift

Un binding concreto queda stale cuando el repositorio cambia de forma que invalida el comando, ruta, branch, proveedor o evidencia esperada.

Antes de ejecutar un control, el sistema DEBE comprobar como mínimo:

1. que el repositorio resuelto conserva su identidad canónica;
2. que el `cwd` existe;
3. que el comando o interfaz declarada puede resolverse;
4. que las precondiciones del control siguen siendo verdaderas;
5. que cualquier revisión fijada o límite de vigencia sigue siendo aplicable.

Si no puede establecerse, el control queda `unknown`; no se sustituye por otro control inferido.

## 5. Contrato de los controles

Todo control concreto usa este modelo lógico:

```yaml
id: stable-control-id
phase: pre | acceptance | review | delivery | post | monitoring | cleanup
when: explicit-condition
required: true
mode: read-only | local-mutation | external-mutation
executor:
  type: command | human-approval | observation
timeout_seconds: 300
success:
  evidence: verifiable-postcondition
on_failure: stop | defer | notify
```

El payload de `executor` depende de su tipo:

- `command`: declara `cwd`, `run` y códigos de salida aceptables;
- `human-approval`: declara alcance, identidad de la decisión y evidencia durable;
- `observation`: declara target, campos consultados y una operación read-only.

### 5.1 Requisitos

- `id` DEBE ser estable dentro de la configuración efectiva del repositorio.
- `executor` DEBE contener exactamente un tipo y todos sus campos requeridos.
- Un executor `command` DEBE ser concreto y ejecutable desde el `cwd` declarado.
- `when` NO DEBE depender de interpretación implícita.
- `success` DEBE describir el resultado verificable, no solo que el executor inició.
- `on_failure` DEBE preservar el error mínimo y no convertir fallo en éxito.
- Un control que maneje secretos NO DEBE imprimirlos ni persistirlos como evidencia.
- Un control de `external-mutation` requiere autorización humana explícita para el alcance de esa ejecución, salvo que exista una autorización permanente igualmente explícita y acotada.

### 5.2 Estados

Los estados canónicos son:

- `pending`: todavía no ejecutado;
- `passed`: postcondición verificada;
- `failed`: ejecución o postcondición fallida;
- `skipped`: exclusión permitida por una condición explícita;
- `unknown`: no se pudo ejecutar o verificar;
- `not_applicable`: el control no aplica según configuración efectiva.

## 6. Ejes configurables

Cada repositorio recibe valores efectivos para los ejes siguientes. Pueden proceder de defaults, grupo u override de repositorio.

| Eje | Propósito |
| --- | --- |
| `context_sources` | Ticket, diseño, adjuntos, memoria y recursos que deben cargarse. |
| `base_branch` | Branch o revisión desde la que parte el trabajo. |
| `sync_strategy` | Cómo se establece frescura antes de modificar. |
| `isolation_strategy` | Worktree, branch, entorno efímero u otro aislamiento verificable. |
| `development_workflow` | Flujo de diseño, aprobación, planificación e implementación. |
| `commit_policy` | Forma y restricciones de commits. |
| `delivery_mode` | PR, direct push, trunk, artefacto local u otro mecanismo. |
| `delivery_gate` | Aprobación y evidencia requeridas antes de entregar. |
| `pre_checks` | Controles concretos previos a acceptance y entrega. |
| `acceptance_checks` | Verificación de los criterios del spec aprobado. |
| `review_checks` | Revisión humana, automática o independiente. |
| `post_checks` | Postcondiciones concretas después de integrar, publicar o desplegar. |
| `monitoring` | Señales y periodo de observación posteriores. |
| `external_effects` | Precondiciones, autorización y postcondiciones para sistemas externos. |
| `credential_policy` | Mecanismo autorizado para usar y proteger credenciales. |
| `knowledge_policy` | Clases de artefactos, destinos permitidos y aprobación requerida para escribirlos. |
| `cleanup_policy` | Qué se ofrece, conserva o elimina y quién puede autorizarlo. |
| `custom_rules` | Reglas adicionales que no contradicen invariantes. |

Las opciones conocidas funcionan como catálogo, no como lista cerrada. Los valores concretos y sus comandos pertenecen al control plane, no al Handbook.

## 7. Valores por defecto

Los defaults priorizan seguridad frente a conveniencia:

- `base_branch`: detectar mediante lectura del repositorio; si es ambiguo, `unknown`.
- `sync_strategy`: `unknown`; debe declararse antes de trabajo mutante.
- `isolation_strategy`: aislamiento dedicado para trabajo mutante ticketed; equivalentes requieren declaración explícita.
- `development_workflow`: diseño proporcional al alcance y aprobación antes de implementar.
- `delivery_mode`: `unknown`; bloquea entrega hasta declararse.
- `pre_checks`: `[]`; la ausencia es visible y no se confunde con validación.
- `acceptance_checks`: obligatorios cuando existe un spec con criterios de aceptación.
- `review_checks`: al menos una revisión antes de entrega mutante.
- `post_checks`: `[]`; la ausencia es visible y debe aceptarse conscientemente.
- `monitoring.enabled`: `false`.
- `external_effects.mode`: `read-only` hasta autorización explícita.
- `knowledge_policy`: aprobación humana por artefacto durable; `repo_writable_classes` vacío, es decir, ningún artefacto sujeto a esta política puede escribirse en un repositorio hijo hasta que su clase se enumere.
- `cleanup_policy`: ofrecer; no eliminar automáticamente por decisión del agente.

Los defaults no autorizan inferir comandos desde la presencia de archivos del repositorio.

## 8. Flujo de trabajo

### Fase 0 — Resolver autoridad y memoria

1. Identificar el `repo_id` canónico.
2. Resolver la configuración efectiva.
3. Mostrar campos heredados, overrides y `unknown`.
4. Consultar las fuentes de memoria declaradas.
5. Detenerse si una fuente obligatoria no está disponible.

### Fase 1 — Cargar contexto

Se cargan ticket, diseño, adjuntos y referencias declaradas en `context_sources`.

> Nada es obligatorio por tipo; todo recurso declarado como requerido es obligatorio de leer.

Si un recurso requerido no puede abrirse, el trabajo se detiene y se informa qué falta.

### Fase 2 — Preparar entorno

1. Ejecutar `sync_strategy`.
2. Verificar frescura según la evidencia declarada.
3. Crear o seleccionar `isolation_strategy`.
4. Confirmar que toda mutación posterior ocurrirá dentro del entorno autorizado.

La spec no presupone `pull`, un nombre de branch ni una tecnología de aislamiento.

### Fase 3 — Diseñar e implementar

1. Clasificar alcance y riesgo.
2. Explorar el contexto necesario.
3. Aclarar requisitos.
4. Proponer y aprobar el diseño requerido.
5. Escribir un spec con criterios de aceptación cuando la complejidad lo requiera.
6. Implementar solo después del gate aplicable.

El framework o procedimiento concreto se define en `development_workflow`.

### Fase 4 — Verificar

En orden:

1. ejecutar todos los `pre_checks` aplicables;
2. ejecutar los `acceptance_checks` derivados del spec aprobado;
3. ejecutar los `review_checks`;
4. registrar resultados y evidencia;
5. detener la entrega ante cualquier control requerido en `failed` o `unknown`.

La mera existencia de CI, tests o scripts no prueba acceptance. Debe existir trazabilidad entre criterio, control y resultado.

### Fase 5 — Entregar

1. Preparar el artefacto según `delivery_mode` y `commit_policy`.
2. Verificar las postcondiciones previas definidas en `delivery_gate`.
3. Presentar el resumen y obtener la aprobación exigida.
4. Ejecutar la entrega únicamente dentro del alcance autorizado.
5. Registrar evidencia de que el artefacto quedó efectivamente entregado.

La spec no presupone PR. Un review de merge no sustituye una aprobación previa cuando esta haya sido declarada.

### Fase 6 — Monitorear

Si `monitoring.enabled` es `true`, se observan las señales, duración y condiciones de salida declaradas. La observación es de solo lectura salvo autorización separada para remediar.

### Fase 7 — Verificar postcondiciones y cerrar

1. Ejecutar todos los `post_checks` aplicables.
2. Confirmar el estado final esperado de la entrega o sistema afectado.
3. Registrar `passed`, `failed`, `unknown` o `not_applicable` por control.
4. Aplicar `cleanup_policy`.
5. Ante un post-check fallido, detener reintentos mutantes y volver a autorización.

`done`, el cierre de un worker o el éxito del comando de entrega no sustituyen la verificación de postcondiciones.

### Fase 8 — Retro y conocimiento durable

1. Revisar la sesión y extraer decisiones, errores, fricciones y patrones.
2. Confirmar y registrar las clases canónicas previamente asignadas. Todo artefacto nuevo producido durante la retro DEBE clasificarse antes de su primera escritura durable.
3. Obtener la aprobación correspondiente.
4. Escribir en el destino central autorizado; un repositorio hijo solo si la clase está enumerada en `repo_writable_classes`.
5. Registrar procedencia sin copiar secretos ni contenido sensible innecesario.

Una autorización permanente para una clase —por ejemplo, un tipo de registro— no autoriza otras clases de documentos.

## 9. Invariantes

Estas reglas no son configurables. Los IDs conservan el tema de v1.1 cuando existe correspondencia y generalizan el mecanismo concreto:

1. **INV-01 — Destino de conocimiento:** todo artefacto durable de conocimiento o gobernanza del proceso DEBE escribirse en el destino central configurado. Un repositorio hijo solo PUEDE recibirlo si su clase está enumerada en `knowledge_policy.repo_writable_classes` de la configuración efectiva. Los archivos que implementan el cambio autorizado —por ejemplo, código, pruebas, configuración del producto y artefactos de build— se rigen por el alcance de la tarea y los controles de entrega, no por este invariante. Antes de su primera escritura durable, todo artefacto sujeto a esta política DEBE recibir una clase canónica. Si no puede determinarse inequívocamente si está sujeto a la política o qué clase le corresponde, el estado es `unknown` y la escritura se detiene.
2. **INV-02 — Control plane central:** la configuración y el conocimiento operativo del workspace DEBEN tener autoridad central e historial auditable; su transporte o remoto no se presupone.
3. **INV-03 — Contexto completo:** si un recurso requerido no puede abrirse, el trabajo DEBE detenerse y notificarse.
4. **INV-04 — Frescura declarada:** antes de mutar, DEBE ejecutarse y verificarse la estrategia de frescura efectiva; la spec no presupone `pull`.
5. **INV-05 — Aislamiento declarado:** toda mutación DEBE ocurrir en el entorno autorizado por la estrategia de aislamiento efectiva; la spec no presupone worktree.
6. **INV-06 — Diseño aprobado:** no se inicia implementación antes del gate de diseño aplicable.
7. **INV-07 — Acceptance trazable:** los criterios del spec aprobado DEBEN mapearse a checks y resultados verificables; los pre-checks y review checks obligatorios también DEBEN pasar antes de entregar.
8. **INV-08 — Entrega autorizada:** ninguna entrega o efecto externo mutante ocurre fuera del gate, modo y alcance declarados; la spec no presupone PR.
9. **INV-09 — Conocimiento aprobado:** todo artefacto durable sujeto a `knowledge_policy` DEBE seguir la política de aprobación de su clase; una autorización no se amplía por inferencia a otras clases.
10. **INV-10 — Cleanup gobernado:** una eliminación destructiva DEBE seguir la política y autorización efectivas; el agente no elimina automáticamente por decisión propia.
11. **INV-11 — Fallo cerrado:** un control obligatorio `failed` o `unknown` NO DEBE tratarse como éxito.
12. **INV-12 — Postcondición verificada:** una tarea no se considera entregada solo por señales de finalización; DEBEN verificarse las postcondiciones configuradas.
13. **INV-13 — Secretos protegidos:** configuración, comandos, logs y evidencia NO DEBEN exponer ni persistir credenciales fuera del mecanismo autorizado.

## 10. Configuración mínima por repositorio

Cada repositorio DEBE tener una entrada central, aunque herede todos sus controles:

```yaml
schema_version: workspace-control/v1

repo:
  id: group/repository
  path: /absolute/canonical/path
  group: group
  managed: true
  verified_revision: unknown

context_sources: []

workflow:
  base_branch: unknown
  sync_strategy: unknown
  isolation_strategy: dedicated
  development_workflow: design-before-implementation
  delivery_mode: unknown

pre_checks: []
acceptance_checks: []
review_checks: []  # bloquea entrega mutante hasta declarar una revisión
post_checks: []

monitoring:
  enabled: false

external_effects:
  mode: read-only

knowledge_policy:
  default: per-artifact-human-approval
  repo_writable_classes: []

cleanup_policy:
  default: offer-never-auto-delete

custom_rules: []
```

Los valores `unknown` impiden las fases afectadas. El onboarding consiste en sustituirlos por bindings observados y aprobados, no en adivinarlos.

## 11. Ejemplo no normativo de binding

```yaml
repo:
  id: example/service
  path: /workspace/example/service
  group: example
  verified_revision: abc123

workflow:
  base_branch: primary
  sync_strategy: fast-forward
  isolation_strategy: dedicated-worktree
  delivery_mode: review-request

pre_checks:
  - id: project-check
    phase: pre
    cwd: .
    run: ./scripts/check
    when: always
    required: true
    mode: local-mutation
    timeout_seconds: 600
    success:
      exit_codes: [0]
      evidence: exit code and summarized check results
    on_failure: stop

acceptance_checks:
  - id: spec-acceptance
    phase: acceptance
    cwd: .
    run: ./scripts/acceptance
    when: approved-spec-present
    required: true
    mode: local-mutation
    timeout_seconds: 900
    success:
      exit_codes: [0]
      evidence: criterion identifiers and results
    on_failure: stop

post_checks:
  - id: delivered-state
    phase: post
    cwd: .
    run: ./scripts/verify-delivery
    when: delivery-completed
    required: true
    mode: read-only
    timeout_seconds: 300
    success:
      exit_codes: [0]
      evidence: delivered revision and observed state
    on_failure: notify
```

Los nombres y comandos son ilustrativos. La configuración real debe contener los controles observados y aprobados para cada repositorio.

## 12. Precedencia frente a steering y automatización

La configuración central es la autoridad del workspace, pero no puede prometer que anula controles externos que técnicamente siguen activos.

Al incorporar un repositorio se inspeccionan:

1. configuración global de las herramientas;
2. steering heredado;
3. steering y políticas del repositorio;
4. hooks y plugins;
5. CI y políticas del proveedor;
6. práctica observable.

Todo control activo que contradiga la configuración central debe quedar como conflicto explícito. No se fusiona silenciosamente ni se declara resuelto hasta cambiar una de las autoridades efectivas.

## 13. Seguridad y sistemas externos

### 13.1 Credenciales

La spec solo establece el principio de protección. El mecanismo concreto —transporte, helper, token efímero, cifrado o scanner— se declara en `credential_policy` y en los controles afectados.

La evidencia registra nombres de controles y resultados sanitizados; nunca valores secretos.

### 13.2 Efectos externos

Cuando una tarea pueda mutar un sistema externo, la configuración efectiva DEBE declarar:

- observaciones read-only previas;
- contrato y variabilidad que deben verificarse;
- autorización de mutación;
- checks posteriores;
- condición de rollback, defer o nueva autorización.

La spec no prescribe GitOps, APIs, proveedores, comandos ni plataformas. Esos son bindings concretos del repositorio.

## 14. Adopción

La adopción de un repositorio sigue este orden:

1. registrar identidad física canónica;
2. cuando la raíz del workspace coincida con un repositorio Git y se use `.workspace/worktrees/`, asegurar idempotentemente la entrada `/.workspace/worktrees/` en el archivo local de exclusiones resuelto por Git (`.git/info/exclude`), sin sobrescribir entradas existentes ni trasladar esta exclusión al `.gitignore` versionado;
3. asignar grupo, si aplica;
4. observar en modo read-only sus interfaces y controles reales;
5. crear la entrada central;
6. resolver todos los `unknown` necesarios para la primera tarea;
7. revisar y aprobar la configuración efectiva;
8. ejecutar una tarea representativa sin efectos externos;
9. habilitar gradualmente delivery y efectos externos.

No es necesario copiar política a cada repositorio. Sí es necesario que cada repositorio tenga una configuración efectiva verificable.

## 15. Criterios de aceptación de esta especificación

Esta versión es aceptable cuando una implementación del control plane puede demostrar que:

1. inventaría cada repositorio físico una sola vez;
2. resuelve `workspace → group → repository` determinísticamente;
3. muestra el origen de cada valor efectivo;
4. no necesita abrir configuración en repositorios hijos para saber qué controles ejecutar;
5. ejecuta controles concretos en el `cwd` correcto;
6. conserva `unknown` y falla cerrado;
7. enlaza criterios de aceptación con checks y resultados;
8. distingue finalización de proceso de entrega verificada;
9. protege secretos en configuración y evidencia;
10. detecta bindings stale antes de tratarlos como válidos;
11. no aplica herramientas o proveedores concretos como reglas universales;
12. mantiene historial versionado de la configuración central.

## 16. Fuera de alcance

Esta especificación no define:

- el formato interno de scripts o pipelines de los repositorios;
- una herramienta concreta para resolver o ejecutar la configuración;
- un proveedor de tickets, Git, CI, secretos, despliegue o monitoreo;
- los comandos reales de ningún repositorio;
- migraciones automáticas de repositorios existentes;
- autorización para mutar remotos o sistemas vivos.

Esas decisiones pertenecen a la configuración, a su implementación futura o a tareas de adopción explícitamente aprobadas.

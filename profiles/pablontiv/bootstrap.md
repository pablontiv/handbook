# Wizard de adopción del perfil Pablontiv Handbook

Este documento guía a Pi para preparar una instancia prose-first de `pablontiv/handbook`. No es un CLI, no ejecuta un merge automático y no activa un workspace por sí mismo. La salida propuesta es `.workspace/config.yaml`; toda incertidumbre material permanece `unknown` y bloquea la mutación o entrega afectada.

## Reglas del wizard

- Trabajar sobre un repositorio consumidor identificado, no sobre una ruta inferida.
- Separar observación, propuesta, aprobación, escritura y verificación.
- No copiar el `AGENTS.md` del handbook. Inspeccionar y preservar el steering local de cada consumidor.
- No presentar prosa como control ejecutado ni como evidencia automática.
- No sustituir Rootline, Backscroll ni un artefacto oficial aplicable.
- No mutar sistemas externos durante bootstrap.

## Etapas numeradas

### 1. Identificar identidad y autoridad

1. Resolver por lectura la raíz física canónica del workspace y la raíz Git del repositorio consumidor.
2. Proponer un `repo.id` estable, la ruta canónica, el grupo si aplica y la revisión observada.
3. Detectar aliases, symlinks o worktrees. No tratarlos como nuevas identidades.
4. Si la identidad no puede resolverse inequívocamente, conservar `unknown` y detener cualquier preparación mutante.
5. Leer `PROFILE.md` y verificar que declara `pablontiv/handbook`, Engineering Handbook 1.4 y el digest `f5455e3eced13690358b02823053a1e00a6c7c06de5f17d9716805bf0a0cff26`.
6. Verificar la procedencia contra `references/engineering-handbook-v1.4.md`. Una discrepancia bloquea la adopción.

### 2. Realizar inspección de solo lectura

1. Inspeccionar herramientas instaladas y sus versiones observables.
2. Inspeccionar configuración global del runtime Pi, steering heredado y steering del repositorio consumidor.
3. Inspeccionar hooks, plugins, automatizaciones, CI, políticas del proveedor y práctica observable.
4. Identificar la branch base, estrategia de frescura, aislamiento disponible, workflow de desarrollo, política de commits, modo y gate de entrega.
5. Inventariar pre-checks, criterios de acceptance, mecanismos de review, post-checks, monitoring, efectos externos, credenciales, conocimiento y cleanup.
6. Tratar specs, documentación y nombres de scripts como claims hasta comprobar la interfaz real. No ejecutar operaciones mutantes para descubrir comportamiento.
7. Registrar conflictos entre `.workspace/config.yaml` propuesta y autoridades técnicamente activas. No prometer que la configuración central las anula.

### 3. Consultar memoria episódica

1. Verificar disponibilidad y estado de Backscroll mediante su preflight oficial.
2. Buscar primero con alcance del proyecto canónico y salida acotada legible por máquina.
3. Si no hay resultado, ampliar exactamente una vez a todos los proyectos.
4. Para recordar comandos, rutas o errores de ejecución, usar búsqueda de contenido de herramienta.
5. Para agentes, usar `--robot`, `--fields minimal` y un `--max-tokens` explícito.
6. Contrastar la memoria con el repositorio y los registros durables; Backscroll no reemplaza source, ADRs ni validación Rootline.
7. Cuando una historia requerida no esté disponible o sea inutilizable, conservar `unknown` y explicar qué fase bloquea.

### 4. Resolver capas y unknowns materiales

1. Completar los 18 ejes del perfil sin eliminar `context_sources`, el bloque `workflow`, los cuatro grupos de checks ni las políticas restantes.
2. Resolver en orden lógico `workspace → group → repository`.
3. Aplicar la semántica del perfil: escalares reemplazan, mapas se combinan recursivamente y listas se reemplazan completas.
4. Distinguir valor ausente, lista vacía y `unknown`.
5. Mostrar el origen de cada valor: `workspace`, `group` o `repository`.
6. Preguntar únicamente por hechos materiales que no puedan observarse de forma segura.
7. No adivinar comandos, branches, políticas, rutas, proveedores ni evidencia.

### 5. Renderizar la configuración candidata

1. Partir de `config.template.yaml` y preparar en memoria una configuración candidata para `.workspace/config.yaml`.
2. Mantener `workspace`, `groups` y `repositories` aunque alguna capa quede vacía.
3. Incluir identidad estable, locator relocatable o ruta explícitamente no resuelta, revisión observada y `AGENTS.md` como steering local cuando exista.
4. Expresar controles en prosa, listas de prosa y `unknown`; no inventar executors, schemas ni evidencia pasada.
5. Presentar un resumen por eje con valor efectivo, origen, conflicto, evidencia y blocker.
6. Mostrar el diff completo de bytes propuestos. La propuesta todavía no está activa y no autoriza ningún efecto externo.

### 6. Solicitar aprobación humana explícita

1. Enumerar archivos exactos que se crearían o modificarían.
2. Enumerar todos los `unknown`, conflictos y fases bloqueadas.
3. Explicar que aprobar configuración no autoriza delivery, despliegues, cambios remotos ni otras mutaciones externas.
4. Solicitar aprobación del contenido exacto mostrado antes de la primera escritura.
5. Si la persona rechaza o modifica la propuesta, volver a la etapa correspondiente y renderizar una propuesta nueva.
6. No ampliar una aprobación por inferencia ni reutilizarla para bytes diferentes.

### 7. Ejecutar la escritura durable aprobada

1. Escribir únicamente los bytes aprobados en `.workspace/config.yaml`.
2. No crear `.workspace/worktrees/` por anticipado. Crearla solo cuando la estrategia efectiva aprobada la requiera.
3. Si se crea `.workspace/worktrees/`, pedir a Git la ruta real del archivo local de exclusiones y añadir `/.workspace/worktrees/` idempotentemente.
4. Conservar todas las entradas existentes del exclude local; no seguir symlinks ambiguos y no trasladar esa exclusión al `.gitignore` versionado.
5. No copiar el `AGENTS.md` de este repositorio. Conservar el steering propio del consumidor y registrar conflictos activos.
6. Para cualquier Markdown gobernado que la adopción autorice, exigir Rootline y validar el archivo inmediatamente después de escribirlo.
7. Si Rootline no está disponible o falla, marcar `unknown`; no declarar exitosa la escritura gobernada ni usar un sustituto.

### 8. Realizar verificación posterior

1. Releer `.workspace/config.yaml` desde disco y comparar sus bytes con la versión aprobada.
2. Verificar que las capas `workspace`, `groups` y `repositories` permanecen presentes.
3. Volver a calcular la vista efectiva y mostrar valor y origen por eje sin convertirla en autoridad.
4. Verificar que cada conflicto y `unknown` continúa visible y que bloquea la fase obligatoria correspondiente.
5. Confirmar que Rootline validó todo Markdown gobernado escrito.
6. Si se creó `.workspace/worktrees/`, verificar por Git que la entrada local exacta existe una sola vez y que el `.gitignore` versionado no fue alterado por el wizard.
7. Reportar estados `passed`, `failed`, `unknown` o `not_applicable` con evidencia observable. No usar el cierre del proceso como prueba.
8. Declarar qué trabajo puede comenzar en modo local y qué delivery o efecto externo sigue bloqueado.

### 9. Activar gradualmente

1. Ejecutar primero una tarea representativa sin efectos externos.
2. Derivar acceptance de criterios aprobados y conservar trazabilidad.
3. Habilitar delivery únicamente cuando `delivery_mode`, `delivery_gate`, review y post-checks estén resueltos y aprobados.
4. Antes de cualquier sistema externo, observar el contrato real en modo de solo lectura, derivar pruebas desde esa evidencia y pedir una autorización separada.
5. Ante un intento live fallido, no reintentar hasta verificar la causa, reproducirla mediante una prueba fallida, corregir, revisar y recibir nueva autorización.

## Resultado esperado

El wizard termina con una configuración aprobada y verificada, una lista explícita de blockers y la evidencia de las validaciones efectuadas. No termina con un executor instalado, un schema generado, un merge engine, compatibilidad con otro runtime ni autorización implícita para entregar o mutar sistemas vivos.

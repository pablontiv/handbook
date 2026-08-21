---
tipo: adr
estado: accepted
fecha: "2026-08-21"
contexto: "La evaluación local de roles debía preservar runtime, modelo, effort y prompt reales sin exponer extensiones, configuración, bash, rutas, secretos ni red del host al candidato."
decision: "Introducir un evaluador interno con request validado, fixture policy inmutable, Pi cargando solo una extensión confinada, OpenCode con configuración XDG aislada y ejecución de comandos de manifest por sandbox de procesos fail-closed."
consecuencias: "Las evaluaciones inseguras o no verificables retornan INCONCLUSIVE/ABSTAIN en lugar de certificar capacidad; la auditoría retiene solo hechos acotados y requiere backends de sandbox soportados para fixtures con ejecución de código."
---

# Evaluación runtime-exacta con herramientas confinadas

## Contexto

El optimizador necesita comparar modelos para el rol real de un agente, no para un harness genérico. Esa comparación debe conservar identidad exacta de runtime, provider/model y effort/variant, además del cuerpo del agente y sus herramientas requeridas. Sin confinamiento, una evaluación podría leer configuración o credenciales del usuario, cargar extensiones ambientales, ejecutar `bash` sin restricciones, usar red o confiar en reportes no verificables del propio modelo.

La evaluación también debe producir evidencia reutilizable sin almacenar prompts completos, respuestas del modelo, argumentos crudos de herramientas ni secretos. Cuando el entorno local no puede ofrecer aislamiento suficiente, penalizar al modelo sería incorrecto; el resultado debe ser inconcluso o abstenerse.

## Decisión

Agregar un módulo interno de evaluación que valida `RoleEvalRequest` contra `RouteKey`, `ModelRecord`, `AgentContract`, `RoleRequirements`, `PreparedWorkspace` y `FixturePolicy` antes de cualquier lanzamiento. La validación comprueba identidad de modelo y effort, autoridad de herramientas, token y marcador de workspace, digest del fixture, rutas confinadas, comandos con IDs estables y capability attestations frescas para herramientas custom esenciales.

Pi se ejecuta con extensiones, herramientas builtin, sesión, contexto, skills y templates desactivados, y carga únicamente `evals/pi-confined-tools.ts`. La extensión lee una política acotada generada por el helper, resuelve rutas reales bajo el workspace y acepta solo comandos exactos del manifest. Esos comandos se envuelven con el backend de sandbox seleccionado.

OpenCode usa un `XDG_CONFIG_HOME` temporal dentro del workspace, sin fusionar `OPENCODE_CONFIG_CONTENT` ambiental. El agente de evaluación tiene defaults deny-all, `external_directory: deny`, permisos de lectura/escritura limitados al fixture y `bash: deny`. Antes del lanzamiento se exige que `opencode debug config --pure` coincida con el prompt, modelo, variant y permisos generados. Después, el evaluador confiable ejecuta los comandos de manifest por el sandbox seleccionado.

La selección de sandbox reconoce `sandbox-exec`, `bwrap` y Docker solo si existen y pasan un self-test. Si un fixture requiere ejecución de código y no hay backend, el resultado es `INCONCLUSIVE` con `eval_sandbox_unavailable`. Los eventos JSONL se reducen a `ToolAudit` y `CommandAudit` acotados; los cambios se verifican independientemente con `git diff --name-only` ejecutado por el runner confiable.

## Alternativas descartadas

- Confiar en `cwd` o rutas relativas como aislamiento: no bloquea credenciales, rutas externas ni red.
- Cargar extensiones o configuración ambiente y negar selectivamente: aumenta la superficie de bypass y contradice el requisito de runtime confinado.
- Permitir `bash` del candidato en OpenCode: mezclaría generación y ejecución confiable, impidiendo auditar comandos exactos.
- Persistir transcripts, argumentos de herramientas o texto final para depuración: amplía exposición de secretos y código sin ser necesario para la selección.
- Convertir infraestructura inconclusa en fallo de modelo: confunde capacidad del modelo con capacidad local de aislamiento.

## Consecuencias

La evidencia local queda vinculada a fixture, manifest digest, runtime exacto, tools expuestas y comandos ejecutados. El sistema falla cerrado ante mismatch de request, sandbox ausente, custom tools no probadas, streams truncados o auditoría insuficiente. Esto reduce el riesgo de certificar rutas inseguras, a cambio de abstenerse con más frecuencia en entornos sin sandbox compatible.

El flujo requiere mantener fixtures versionados, políticas de permisos y adaptadores de sandbox. Nuevos runtimes o herramientas custom deberán integrarse mediante capability probes seguros y sin cargar configuración ambiente del usuario.

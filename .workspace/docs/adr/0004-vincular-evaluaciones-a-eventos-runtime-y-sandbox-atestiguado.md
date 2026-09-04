---
tipo: adr
estado: accepted
fecha: "2026-08-21"
contexto: "La primera revisión de seguridad rechazó aceptar auditoría sintética, backends de sandbox como strings libres y entornos heredados para evaluaciones de modelos. Esos supuestos podían permitir que un candidato falsificara evidencia o heredara autoridad del host."
decision: "Vincular la evaluación a eventos emitidos por el runtime y a una SandboxAttestation inmutable. Pi debe ejecutarse en modo JSON y correlacionar tool_execution_start/tool_execution_end por toolCallId. OpenCode debe parsear eventos runtime-shaped como tool_use y permission.asked. Los procesos candidatos y comandos confiables deben recibir environment replacement explícito, y los fixtures con ejecución de código requieren una atestación de sandbox fresca ligada a backend, workspace, token, digest de perfil y self-tests."
consecuencias: "La auditoría plana o no correlacionada queda inconclusa; los backends desconocidos no caen a ejecución cruda en host; la ausencia, stale o mismatch de atestación bloquea fixtures con código. Aumenta la verbosidad de validación y de pruebas, pero reduce la posibilidad de certificar una ruta mediante evidencia falsificada o autoridad ambiental."
---

# Vincular evaluaciones a eventos runtime y sandbox atestiguado

## Contexto

La evaluación de roles ejecuta modelos no confiables con herramientas confinadas. La arquitectura previa ya separaba Pi y OpenCode de la configuración ambiental, pero la revisión identificó tres riesgos concretos: aceptar JSON plano con forma de auditoría, representar el sandbox como un string mutable y lanzar procesos con overlays sobre `os.environ`.

Esos riesgos son de límite de seguridad. Un modelo podría emitir texto con campos `argv` o `exit_code` sin que el runtime haya ejecutado una herramienta; un backend desconocido podría degradar a ejecución directa; y un overlay de entorno puede conservar secretos del proceso padre.

## Decisión

La evidencia de Pi se acepta solo desde eventos JSON mode emitidos por el runtime. El parser requiere correlación entre `tool_execution_start` y `tool_execution_end` por `toolCallId`, y extrae hechos acotados desde los detalles de resultado de la herramienta confinada. La evidencia plana con forma de auditoría no satisface comandos requeridos.

La evidencia de OpenCode se interpreta según los eventos instalados del runtime: `tool_use` para partes de herramienta y `permission.asked` / `permission.v2.asked` para solicitudes de permiso. Una solicitud de permiso en modo no interactivo produce infraestructura inconclusa, no aprobación implícita.

`PreparedWorkspace` porta `SandboxAttestation` en lugar de un backend libre. La atestación registra backend, raíz canónica del workspace, token, digest canónico del perfil, hora de observación y self-tests requeridos. La validación rechaza backends desconocidos, timestamps futuros o vencidos, mismatch de raíz/token/digest y self-tests incompletos.

`CommandRunner` soporta `env_replacement`, usado en los límites de candidato, debug/config y comandos de manifest. Los entornos generados preservan solo canales de autenticación explícitos y variables mínimas como `PATH`; no heredan secretos por defecto.

## Alternativas descartadas

- Conservar `sandbox_backend: str | None` y confiar en validación local del adaptador: demasiado fácil de reutilizar como valor no atestiguado.
- Aceptar auditoría JSON plana junto con eventos runtime: mezcla evidencia confiable y candidato-forjable.
- Mantener `env_overlay` para procesos candidatos y filtrar secretos por nombre: no prueba ausencia de secretos no reconocidos.
- Aprobar automáticamente permisos OpenCode en modo no interactivo: convertiría un bloqueo de seguridad en autorización implícita.

## Consecuencias

Los resultados inseguros pasan a `INCONCLUSIVE` o `HANG` según corresponda. Los tests deben construir eventos con forma de runtime y atestaciones válidas. La selección puede abstenerse con más frecuencia cuando el host no puede probar sandbox, pero no certifica ejecución sin evidencia verificable.

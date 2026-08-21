---
tipo: adr
estado: accepted
fecha: "2026-08-20"
contexto: "Model Optimizer debía reevaluar rutas al incorporar modelos o agentes sin barrer la matriz completa, atribuir benchmarks de familia como evidencia exacta ni mutar configuración antes de aprobación humana."
decision: "Adoptar un único flujo lean con identidad completa de ruta, deltas semánticos, shortlist acotada, evaluaciones locales confinadas y versionadas, evidencia adaptativa por fixture y apply separado con backup, recarga, verificación y rollback verificado."
consecuencias: "La selección reduce churn y exposición del host, pero requiere contratos internos más ricos, fixtures reproducibles, backends de sandbox fail-closed y una segunda recarga para confirmar cualquier rollback."
---

# Optimizar routing con evidencia confinada

## Contexto

El skill existente inventariaba modelos y verificaba disponibilidad, pero no podía justificar empíricamente que una asignación nueva mejorara al incumbent para el rol real. Los benchmarks públicos aportan un prior útil, aunque pueden medir otro provider, esfuerzo, harness o checkpoint. Los aliases opacos tampoco permiten atribuir resultados exactos. Además, evaluar toda la matriz modelo por agente elevaría costo y latencia sin mejorar proporcionalmente la decisión.

La mutación de mappings afecta configuración global o de proyecto. Por ello, disponibilidad, evaluación y aplicación deben permanecer separadas, y una restauración de bytes no basta para declarar rollback exitoso si el runtime no vuelve a cargar y ejecutar la ruta restaurada.

## Decisión

Implementar un único flujo `discover → derive needs → shortlist → evaluate → propose → approve → apply/reload/verify`. La identidad de evidencia incluye runtime y versión, provider/model exacto y effort/variant. Los cambios se detectan mediante fingerprints semánticos independientes de timestamps y orden.

La shortlist admite como máximo cuatro rutas e incluye al incumbent sano. Los benchmarks públicos se registran con correspondencia `EXACT`, `MODEL_EQUIVALENT`, `FAMILY_PROXY`, `ABSENT`, `UNKNOWN` o `SOURCE_UNAVAILABLE`; solo la evaluación local runtime-exacta puede cerrar evidencia ambigua.

Las evaluaciones usan fixtures desechables, permisos y comandos acotados, configuración aislada y sandbox de procesos sin red. Pi carga únicamente la extensión confinada del evaluador; OpenCode deniega bash al candidato y el evaluador confiable ejecuta las pruebas. Si no existe un backend seguro o falta una capability attestation esencial, la decisión es `ABSTAIN`.

Un challenger sustituye a un incumbent sano únicamente con ventaja material comprobable en dos fixtures compatibles o dos observaciones operativas comparables sin regresión de fiabilidad/intervención. La propuesta visible permanece concisa; el target exacto de configuración vive solo en el payload interno aprobado. Apply requiere backup, edición mínima, validación, recarga y verificación de la ruta. Ante fallo, restaura de forma atómica, vuelve a recargar y verifica la ruta restaurada.

## Alternativas descartadas

- Elegir solo por benchmarks públicos: no prueba el runtime, provider, effort, prompt, tools ni fixture exactos.
- Evaluar la matriz completa modelo por agente: aumenta costo y latencia y contradice el embudo lean.
- Confiar en cwd o allowlists textuales como aislamiento: no impide acceso a credenciales, red o rutas del host.
- Exponer manifests y targets internos al usuario: añade plumbing sin mejorar la aprobación.
- Aplicar automáticamente la mejor puntuación: omite incertidumbre, anti-churn y aprobación humana.
- Considerar rollback la restauración de bytes: no demuestra que el runtime restaurado funcione.

## Consecuencias

El optimizador puede justificar `CHANGE`, `NO_CHANGE`, `NEEDS_MORE_EVIDENCE` o `ABSTAIN` con evidencia auditable y acotada. La caché evita repetir evaluaciones durante siete días sin almacenar prompts, respuestas, código o secretos. La arquitectura añade tipos internos para identidad, permisos, fixture policy, auditoría y estado, pero mantiene un único flujo visible.

La ejecución local depende de backends de locking y sandbox soportados; su ausencia desactiva persistencia o evaluación de forma fail-closed. Los fixtures y graders deben mantenerse versionados y semánticos. Cualquier ampliación a nuevos runtimes, herramientas esenciales o mecanismos de apply deberá conservar estas fronteras.

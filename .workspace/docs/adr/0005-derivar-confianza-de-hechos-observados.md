---
tipo: adr
estado: accepted
fecha: "2026-08-21"
contexto: "La segunda revisión de seguridad rechazó transiciones de confianza derivadas de etiquetas sintéticas, colecciones mutadas parcialmente, configuraciones ambientales no acotadas y evidencia de estado vacía. La evaluación de roles necesitaba distinguir hechos observados por el runtime o el sistema operativo de valores reportados o inferidos."
decision: "Derivar PASS, ausencia de cambios, disponibilidad de sandbox y atestaciones de capacidad exclusivamente desde hechos observados y acotados. La selección de sandbox ejecuta probes exactos de escritura permitida, lectura externa denegada, ausencia de secretos y listener de red denegado antes de construir una SandboxAttestation. Los digests de fixture, sandbox y capability probe se recomputan desde contenido canónico y contexto de ruta/workspace. La colección de cambios usa un resultado tipado sobre git status porcelain v1 -z; fallas, timeouts, truncación o evidencia inválida son INCONCLUSIVE. OpenCode usa autenticación por proveedor y limpieza incondicional de raíces temporales. Pi registra únicamente herramientas solicitadas compatibles con el runtime instalado."
consecuencias: "La producción excluye backends que no puedan probar todos los probes y abstiene evaluaciones esenciales inseguras. La auditoría sobredimensionada o con campos inválidos no se recorta para simular evidencia; pasa a inconclusa. El código es más estricto y puede requerir configuración explícita de autenticación por proveedor, pero evita certificar evaluaciones a partir de ausencia de datos o de declaraciones sintéticas."
---

# Derivar confianza de hechos observados

## Contexto

La evaluación runtime-exacta busca comparar modelos sin conceder autoridad ambiental ni aceptar reportes del candidato como prueba. La segunda revisión identificó que aún quedaban transiciones de confianza no observadas: self-tests marcados como `PASS`, colecciones de auditoría recortadas, cambios vacíos ante fallas de `git status`, autenticación OpenCode no diferenciada por proveedor y stubs de herramientas Pi anunciadas pero no funcionales.

Estos casos comparten una falla: tratan la falta de evidencia como evidencia positiva o degradan datos inválidos a valores seguros por defecto.

## Decisión

La disponibilidad de sandbox se construye solo después de ejecutar probes con el perfil exacto: escritura/lectura dentro del workspace, lectura de sentinel externo denegada, ausencia de secretos bajo entorno reemplazado y listener de red denegado. La atestación incorpora identidad del ejecutable, raíz canónica, token, perfil y digests de salidas observadas.

Los digests de fixture y capability probe se recalculan desde contenido canónico y se vinculan al workspace, token, ruta, herramienta y digest de sandbox. Las fechas de prueba son relativas al reloj de ejecución.

La colección de cambios se representa como `ChangedPathsResult`. Solo `git status --porcelain=v1 -z --untracked-files=all` exitoso produce paths; fallas, timeouts, truncación, paths inválidos u oversized producen `INCONCLUSIVE`.

La auditoría tiene límites estrictos de identificadores, strings, enteros y cardinalidad. El registro 129 no se persiste y la evaluación queda inconclusa si excede el límite. Los estados conservan semántica: fallo de comando requerido es `FAIL`, timeout es `HANG`, infraestructura/config/permisos/cuota/auditoría inválida es `INCONCLUSIVE`, y solo evidencia requerida exitosa es `PASS`.

OpenCode genera config/data roots aislados por evaluación, preserva solo canales de autenticación del proveedor de la ruta y limpia las raíces en éxito, error y excepciones. Pi redirige raíces de sesión/datos a paths descartables y registra implementaciones funcionales para `read`, `write`, `edit`, `bash`, `ls`, `grep` y `find` cuando son solicitadas.

## Alternativas descartadas

- Mantener etiquetas `PASS` generadas por el helper sin observar los probes: no prueba aislamiento real.
- Interpretar una falla de `git status` como “sin cambios”: confunde ausencia de evidencia con estado vacío.
- Recortar auditoría oversized y continuar: permite que un atacante o bug oculte eventos relevantes después del límite.
- Preservar variables OpenCode genéricas para todos los proveedores: aumenta superficie de credenciales y configuración ambiental.
- Registrar `grep` y `find` como stubs que lanzan error: anuncia capacidades que el runtime no puede ejecutar.

## Consecuencias

La evaluación es más conservadora. Hosts con Docker que permiten listener local o `sandbox-exec` que no puede ejecutar el perfil quedan sin backend disponible hasta probar todos los requisitos. Algunas rutas necesitarán credenciales explícitas por proveedor. A cambio, cada transición de confianza tiene una fuente verificable y los resultados inseguros no se transforman en PASS por defecto.

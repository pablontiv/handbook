---
tipo: adr
estado: accepted
fecha: "2026-08-21"
contexto: La evaluación local de modelos necesita fixtures piloto reutilizables para comparar candidatos por arquetipo. Esos fixtures ejecutan o inspeccionan código en workspaces desechables, por lo que no pueden aceptar rutas arbitrarias, comandos ambientales ni diagnósticos sin evidencia objetiva. Además, las pruebas de infraestructura previas identificaron que la confianza en sentinels predecibles, identidad de ejecutables basada solo en stat e inventarios con asignación previa podía erosionar el confinamiento.
decision: Los fixtures piloto confiables se cargan únicamente desde el árbol versionado `evals/` o desde un directorio temporal propiedad del evaluador con token marcador impredecible. Los manifiestos se acotan por tamaño, validan IDs estables, grader conocido, comandos exactos permitidos y proyecto sin escapes por symlink. La preparación copia el proyecto a un workspace desechable y los graders evalúan criterios semánticos objetivos. La selección exige evidencia compatible de dos fixtures o dos observaciones operativas comparables. La infraestructura de soporte usa sentinels exclusivos en directorios temporales propios, identidad de ejecutable con ruta canónica, stat y hash, e inventario incremental acotado antes de leer contenido.
consecuencias: La comparación local gana fixtures piloto reproducibles sin ampliar la superficie de confianza hacia proyectos de usuario o configuración real. Las ejecuciones con sandbox no disponible siguen absteniéndose en lugar de degradar seguridad. El costo es mayor validación alrededor de manifiestos, preparación y graders, además de pruebas vivas que dependen de la disponibilidad de los runtimes instalados y se omiten solo cuando el ejecutable no existe.
---

# Confiar solo en fixtures piloto bundled y marcados

## Contexto

El flujo de optimización necesita evidencia local exacta para decidir si un candidato supera al incumbente. Los fixtures piloto son deliberadamente pequeños, pero siguen siendo entradas de confianza: definen archivos, comandos permitidos y criterios de éxito. Si se aceptaran rutas arbitrarias o comandos ambientales, el evaluador podría ejecutar o inspeccionar contenido fuera del workspace desechable.

## Decisión

Se incorporan cuatro fixtures piloto versionados bajo `evals/` y un mecanismo separado para fixtures representativos temporales generados por el evaluador. Los fixtures representativos requieren estar bajo el temp root del evaluador y contener un marcador con el token esperado. Los graders verifican éxito objetivo, comandos requeridos, cambios autorizados y diagnósticos semánticos con evidencia de líneas flexible.

La infraestructura previa se endurece como prerrequisito: los probes usan sentinels exclusivos creados en directorios temporales propios, la identidad del ejecutable incluye ruta canónica, stat y hash, y el inventario de bytes recorre directorios incrementalmente con límites antes de leer contenido.

## Alternativas descartadas

- Aceptar fixtures desde rutas de usuario: descartado porque mezclaría datos no confiables con comandos confiables.
- Validar diagnósticos por formato exacto: descartado porque penaliza diferencias no semánticas y no mejora seguridad.
- Mantener sentinels predecibles o inventarios con `sorted(scandir)`: descartado porque permite colisiones/propiedad ambigua y asignación previa no acotada.

## Consecuencias

El sistema obtiene pilotos reproducibles para los arquetipos mecánico y debugger, con selección estable basada en dos fixtures o dos observaciones operativas. Las rutas no confiables y la falta de sandbox siguen produciendo abstención o inconclusión segura. La complejidad aumenta moderadamente en validación y pruebas, pero queda localizada en el evaluador y el inventario.

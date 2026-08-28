---
tipo: adr
estado: accepted
fecha: '2026-08-28'
contexto: 'La planificación de despliegues Waywarden usa la identidad lexical del slot gobernado para deduplicar despliegues físicos y derivar deployment_id. En Windows, dos rutas con bytes exactos distintos pueden comparar igual bajo reglas insensibles a mayúsculas/minúsculas, mientras que el sistema también permite sensibilidad por directorio. Fusionar o tratar esas rutas como slots independientes puede ocultar duplicados, blockers y ownership incorrecto.'
decision: 'Mantener la identidad lexical exacta del slot gobernado como autoridad y entrada de hash, y derivar una clave comparativa separada sólo para detectar colisiones de caso en Windows. Si dos candidatos tienen la misma clave comparativa pero identidades exactas distintas, Waywarden emite un blocker tipado de ambigüedad y elimina los despliegues de ese grupo ambiguo. La comparación Windows inicial es ASCII conservadora; Unicode no soportado bloquea en lugar de normalizar.'
alternativas: 'Convertir globalmente los slots a minúsculas se descarta porque cambiaría la autoridad de identidad y rompería directorios Windows sensibles a caso; usar Unicode casefolding o normalización se descarta porque no modela de forma segura la identidad real del sistema de archivos; permitir ambos despliegues se descarta porque conserva una ambigüedad operacional peligrosa hasta contar con identidad handle-bound.'
consecuencias: 'Waywarden puede producir falsos positivos seguros en Windows hasta incorporar identidad handle-bound. En plataformas no Windows las claves exactas permanecen sin cambios. Los códigos de blocker quedan definidos por contracts como autoridad compartida y el planner sólo los consume.'
---
# 0021. Bloquear ambigüedad de caso en slots Windows

## Contexto

La planificación de despliegues Waywarden usa la identidad lexical del slot gobernado para deduplicar despliegues físicos y derivar `deployment_id`. En Windows, dos rutas con bytes exactos distintos pueden comparar igual bajo reglas insensibles a mayúsculas/minúsculas, mientras que el sistema también permite sensibilidad por directorio. Fusionar o tratar esas rutas como slots independientes puede ocultar duplicados, blockers y ownership incorrecto.

## Decisión

Mantener la identidad lexical exacta del slot gobernado como autoridad y entrada de hash, y derivar una clave comparativa separada sólo para detectar colisiones de caso en Windows. Si dos candidatos tienen la misma clave comparativa pero identidades exactas distintas, Waywarden emite un blocker tipado de ambigüedad y elimina los despliegues de ese grupo ambiguo. La comparación Windows inicial es ASCII conservadora; Unicode no soportado bloquea en lugar de normalizar.

## Alternativas descartadas

Convertir globalmente los slots a minúsculas se descarta porque cambiaría la autoridad de identidad y rompería directorios Windows sensibles a caso; usar Unicode casefolding o normalización se descarta porque no modela de forma segura la identidad real del sistema de archivos; permitir ambos despliegues se descarta porque conserva una ambigüedad operacional peligrosa hasta contar con identidad handle-bound.

## Consecuencias

Waywarden puede producir falsos positivos seguros en Windows hasta incorporar identidad handle-bound. En plataformas no Windows las claves exactas permanecen sin cambios. Los códigos de blocker quedan definidos por `contracts` como autoridad compartida y el planner sólo los consume.

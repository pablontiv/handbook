---
tipo: adr
estado: accepted
fecha: "2026-08-21"
contexto: "El contrato de aprobación, aplicación, recarga y rollback debía ser verificable de extremo a extremo sin agregar un helper de mutación ni un subcomando de aplicación a la superficie de producción."
decision: "Validar la secuencia mediante una simulación solo para pruebas en tests/support.py y documentación normativa, manteniendo los comandos de helper como evidencia read-only."
consecuencias: "Las pruebas cubren alcance exacto, backup, edición mínima, validación, recarga/reinicio y rollback verificado sin ampliar la superficie operativa; cualquier implementación real futura deberá respetar ese contrato antes de mutar configuración."
---

## Contexto

El optimizador debe detenerse antes de cualquier cambio de configuración hasta contar con aprobación explícita. Después de la aprobación, el contrato exige usar el destino descubierto, crear backup, editar solo campos permitidos, validar sintaxis, recargar o reiniciar, verificar la ruta de agente afectada y, ante fallo, restaurar de forma atómica y verificar nuevamente la ruta restaurada.

Implementar esa ruta como helper o CLI de producción en esta tarea habría ampliado la superficie de mutación y contradicho el límite de que los comandos existentes sigan siendo mecanismos de evidencia read-only.

## Decisión

Se mantiene la mutación fuera de producción. El contrato se documenta en la referencia normativa y se prueba con una simulación exclusiva de tests en `tests/support.py`. La simulación opera solo sobre árboles temporales, exige digest del origen, copia bytes exactos al backup, edita spans mínimos en JSON o frontmatter Markdown, valida la fuente, registra recarga/reinicio y verificación de ruta, y usa `os.replace` para restaurar en rollback antes de validar y verificar la ruta restaurada.

## Alternativas descartadas

- Agregar un subcomando `apply` al helper: descartado porque convertiría el helper de evidencia en una superficie de mutación.
- Crear una utilidad de mutación de producción sin CLI: descartado porque igualmente introduciría código operativo no requerido por la tarea.
- Probar solo documentación sin simulación ejecutable: descartado porque no demostraría igualdad de bytes, edición mínima, orden de recarga/verificación ni rollback atómico.

## Consecuencias

- La suite ahora puede fallar de forma determinista si el contrato documentado pierde alcance exacto, backup de bytes, edición mínima, segunda recarga o verificación de ruta restaurada.
- La simulación no debe importarse desde código de producción.
- Una implementación real futura deberá tratar estos tests como contrato de comportamiento, no como autorización para exponer una mutación antes de aprobación.

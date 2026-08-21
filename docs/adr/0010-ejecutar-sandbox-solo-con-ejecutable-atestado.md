---
tipo: adr
estado: accepted
fecha: "2026-08-21"
contexto: "Las evaluaciones confinadas ya registraban SandboxAttestation con identidad de ejecutable, perfil y probes, pero la construcción final de argv seguía usando literales resolubles por PATH."
decision: "Construir cada lanzamiento de sandbox desde el ejecutable canónico almacenado en la atestación y revalidar la identidad antes de ejecutar comandos de manifiesto."
consecuencias: "La atestación deja de ser solo evidencia documental y pasa a controlar el límite de ejecución; los tests sintéticos deben usar identidades con hash y argv canónico."
---

## Contexto

Las evaluaciones de rol dependen de un backend de sandbox atestado. La revisión detectó que, aunque la atestación incluía identidad de ejecutable, los probes y comandos de manifiesto podían construirse con literales como `bwrap` o `sandbox-exec`. Eso dejaba una brecha entre el ejecutable verificado y el ejecutable efectivamente lanzado si el PATH cambiaba o el binario era reemplazado.

## Decisión

El sandbox se lanza usando el path canónico derivado de la `SandboxAttestation`. La validación recalcula la identidad actual del ejecutable y rechaza reemplazos antes de ejecutar comandos de manifiesto. Los probes iniciales también registran `argv[0]` con el path canónico observado.

## Alternativas descartadas

- Mantener literales de PATH y confiar en la revalidación separada: descartado porque no garantiza que el lanzamiento consuma el mismo artefacto verificado.
- Resolver PATH en cada lanzamiento sin usar la atestación: descartado porque permite drift entre probe y evaluación.
- Permitir identidades antiguas sin hash en tests: descartado porque debilita el contrato que la revisión pidió cerrar.

## Consecuencias

- Los tests deben construir fixtures de atestación con identidad `sha256` y argv canónico.
- La ejecución falla cerrada si el ejecutable desaparece o cambia después del probe.
- El acoplamiento entre atestación y lanzamiento aumenta, pero reduce una clase crítica de sustitución de ejecutable.

---
tipo: adr
estado: accepted
fecha: '2026-09-04'
contexto: 'Mentor Telemetría imponía varios formatos completos y telemetría visible en cada respuesta, lo que aumentaba la longitud incluso cuando una respuesta directa era suficiente; Pi además necesita consumir el cuerpo sin frontmatter.'
decision: 'Reducir el output style a un cuerpo de hasta 350 palabras, elegir una sola forma primaria por respuesta, mantener gates transversales de seguridad y aprendizaje, y publicar para Pi un append-system.md idéntico al cuerpo canónico sin frontmatter.'
alternativas: 'Mantener el contrato detallado conserva ceremonia uniforme pero penaliza todas las respuestas; separar estilos conciso y forense exige selección manual; añadir un gestor de distribución, tests y skills especializados introduce complejidad desproporcionada para dos artefactos Markdown.'
consecuencias: 'Las respuestas rutinarias serán más breves y la telemetría sólo aparecerá cuando aporte aprendizaje verificable; la seguridad queda expresada dentro del contrato; append-system.md es un artefacto derivado que debe comprobarse contra el cuerpo canónico antes de publicar; la distribución por symlinks sigue gobernada por ADR 0014.'
---

# 0024. Hacer concisa Mentor Telemetría

## Contexto

Mentor Telemetría imponía varios formatos completos y telemetría visible en cada respuesta, lo que aumentaba la longitud incluso cuando una respuesta directa era suficiente. Pi además necesita consumir el cuerpo sin frontmatter.

## Decisión

Reducir el output style a un cuerpo de hasta 350 palabras, elegir una sola forma primaria por respuesta, mantener gates transversales de seguridad y aprendizaje, y publicar para Pi un `append-system.md` idéntico al cuerpo canónico sin frontmatter.

Esta decisión complementa la distribución por symlinks de ADR 0014 y la delegación de ADRs a su skill especializado de ADR 0015; no añade gestores, tests ni nuevos skills.

## Alternativas descartadas

**Mantener el contrato detallado.** Conserva ceremonia uniforme, pero penaliza todas las respuestas aunque no necesiten explicación extensa.

**Separar estilos conciso y forense.** Permite elegir densidad, pero exige selección manual y crea dos contratos que pueden divergir.

**Añadir un gestor de distribución, tests y skills especializados.** Automatiza más casos, pero introduce complejidad desproporcionada para dos artefactos Markdown.

## Consecuencias

Las respuestas rutinarias serán más breves y la telemetría sólo aparecerá cuando aporte aprendizaje verificable. La seguridad queda expresada dentro del contrato. `append-system.md` es un artefacto derivado que debe comprobarse contra el cuerpo canónico antes de publicar. La distribución por symlinks sigue gobernada por ADR 0014.

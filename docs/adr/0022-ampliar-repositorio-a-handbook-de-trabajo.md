---
tipo: adr
estado: accepted
fecha: '2026-09-02'
contexto: 'La identidad vigente limita el repositorio a skills independientes, pero el árbol ya publica output styles, reglas, helpers, memoria y registros de diseño; el propietario aprobó reposicionarlo como un handbook y renombrar el repositorio público.'
decision: 'Establecer el repositorio completo como un handbook portable con el hero “Un handbook para convertir el trabajo de desarrollo improvisado en un método reproducible, verificable y adaptable.” y el soporte “Reúne reglas, skills, herramientas y memoria para orientar el trabajo de personas y agentes.”; renombrar GitHub a pablontiv/handbook después del merge y autorización live; conservar temporalmente el path local; mantener skills autocontenidas y admitir únicamente artefactos globales, portables, publicables y con ownership explícito.'
alternativas: 'Mantener la identidad exclusiva de skills se descarta porque ya contradice el contenido publicado. Aplicar solo un rebranding se descarta porque no establecería una taxonomía verificable. Implementar ahora el método .workspace completo se descarta porque mezcla identidad con un subsistema aún no diseñado ni probado.'
consecuencias: 'README y AGENTS pasan a describir y navegar el handbook; skills y output styles conservan fronteras explícitas; el método .workspace queda fuera de esta entrega; el rename remoto ocurre tras merge con un gate separado; la rama Waywarden deberá resolver al rebasarse su numeración ADR divergente y sus referencias a ADR 0016.'
---
# 0022. Ampliar repositorio a handbook de trabajo

Reemplaza a 0016-gobernar-propiedad-y-distribucion-de-skills-globales.

## Contexto
La identidad vigente limita el repositorio a skills independientes, pero el árbol ya publica output styles, reglas, helpers, memoria y registros de diseño; el propietario aprobó reposicionarlo como un handbook y renombrar el repositorio público.

## Decisión
Establecer el repositorio completo como un handbook portable con el hero “Un handbook para convertir el trabajo de desarrollo improvisado en un método reproducible, verificable y adaptable.” y el soporte “Reúne reglas, skills, herramientas y memoria para orientar el trabajo de personas y agentes.”; renombrar GitHub a pablontiv/handbook después del merge y autorización live; conservar temporalmente el path local; mantener skills autocontenidas y admitir únicamente artefactos globales, portables, publicables y con ownership explícito.

## Alternativas descartadas
Mantener la identidad exclusiva de skills se descarta porque ya contradice el contenido publicado. Aplicar solo un rebranding se descarta porque no establecería una taxonomía verificable. Implementar ahora el método .workspace completo se descarta porque mezcla identidad con un subsistema aún no diseñado ni probado.

## Consecuencias
README y AGENTS pasan a describir y navegar el handbook; skills y output styles conservan fronteras explícitas; el método .workspace queda fuera de esta entrega; el rename remoto ocurre tras merge con un gate separado; la rama Waywarden deberá resolver al rebasarse su numeración ADR divergente y sus referencias a ADR 0016.

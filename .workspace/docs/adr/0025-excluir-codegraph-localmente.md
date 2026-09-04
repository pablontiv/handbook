---
tipo: adr
estado: accepted
fecha: '2026-09-04'
contexto: 'Codegraph conserva estado local bajo .codegraph; su propio .gitignore oculta la base de datos pero deja visible el archivo .codegraph/.gitignore, generando ruido recurrente y bloqueando checkouts limpios.'
decision: 'En todo repositorio Git donde opere Mentor Telemetría, añadir idempotentemente /.codegraph/ al archivo local de exclusiones resuelto por Git, preservando sus entradas y sin trasladar la regla al .gitignore versionado; publicar la instrucción en el estilo canónico y en su render Pi exacto.'
alternativas: 'Versionar la exclusión se descarta porque el estado pertenece a una herramienta local, no al contrato portable del repositorio. Confiar solo en .codegraph/.gitignore se descarta porque ese archivo continúa apareciendo como no rastreado. Recordarlo manualmente en cada sesión se descarta porque ya produjo drift observable.'
consecuencias: 'La presencia de Codegraph no ensucia git status ni modifica política compartida; la operación debe ser repetible y conservar exclusiones locales existentes; el estilo canónico y append-system.md mantienen paridad exacta y el límite de 350 palabras establecido por ADR 0024.'
---
# 0025. Excluir Codegraph localmente

## Contexto

Codegraph conserva estado local bajo `.codegraph/`. Su propio `.gitignore` oculta la base de datos, pero deja visible `.codegraph/.gitignore`, lo que genera ruido recurrente y puede impedir un checkout limpio.

## Decisión

En todo repositorio Git donde opere Mentor Telemetría, añadir idempotentemente `/.codegraph/` al archivo local de exclusiones resuelto por Git. La operación preserva las entradas existentes y no traslada la regla al `.gitignore` versionado.

Publicar esta instrucción tanto en el estilo canónico como en su render Pi exacto.

## Alternativas descartadas

**Versionar la exclusión.** Se descarta porque el estado pertenece a una herramienta local, no al contrato portable del repositorio.

**Confiar solo en `.codegraph/.gitignore`.** Se descarta porque ese archivo continúa apareciendo como no rastreado.

**Recordarlo manualmente en cada sesión.** Se descarta porque ya produjo drift observable.

## Consecuencias

La presencia de Codegraph deja de ensuciar `git status` sin modificar política compartida. La operación debe ser repetible y conservar exclusiones locales existentes. El estilo canónico y `append-system.md` mantienen paridad exacta y el límite de 350 palabras establecido por ADR 0024.

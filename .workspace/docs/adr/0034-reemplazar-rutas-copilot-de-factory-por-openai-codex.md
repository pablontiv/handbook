---
tipo: adr
estado: superseded
fecha: '2026-09-08'
contexto: 'El Operador estableció como política vigente para todas las Factories, hasta que la cambie, que el acceso por GitHub Copilot se reemplace por la ruta openai-codex soportada con el mismo harness y modelo exacto; el binding canónico de QA usaba Pi con github-copilot/gpt-5.6-terra y los bindings de los roles de Factory vivían solo en el issue 38 y en memoria de sesión, sin registro gobernado en Handbook, mientras ADR 0032 ya registraba el de Mission Control.'
decision: 'Fijar el binding canónico de QA en Pi con openai-codex/gpt-5.6-terra y thinking medium, conservando rol, independencia y restricciones, y adoptar la regla de que toda ruta github-copilot de un rol de Factory se reemplaza por la ruta openai-codex idéntica y soportada del mismo modelo, verificando soporte y autenticación sin exponer credenciales y registrando el proveedor y modelo observados antes del primer dispatch; los modelos Copilot sin ruta openai-codex idéntica no se sustituyen y se reportan como discrepancia, nunca se mapean a otra familia; este ADR no adopta la tabla piloto del issue 38 y no cambia los bindings de Orchestrator, Researcher, Developer ni Reviewer.'
alternativas: 'Tratar el reemplazo como fallback automático de cuota o como reacción al incidente de errores 429 del 2026-09-08 registrado en ADR 0033 se descarta porque el Operador lo definió como política explícita y permanente, y la exclusión de cambios de proveedor, modelo o cuenta de ADR 0033 aplica a la respuesta automática ante cuota de Mission Control, no a esta política. Mapear modelos Claude o Gemini de Copilot a otra familia se descarta por prohibición explícita. Editar credenciales o configuración global del usuario desde una Factory se descarta por exceder su propiedad. Crear un registro de bindings paralelo al issue 38 se descarta porque el issue sigue siendo el backlog autoritativo y este ADR es la autoridad normativa del binding de QA.'
consecuencias: 'Las Factories futuras aplican el binding canónico de QA con openai-codex y verifican la ruta observada antes de despachar; el cambio de proveedor de QA no altera el gate de admisión de bindings, que sigue siendo el issue 38 aún no autorizado; Mission Control conserva su binding de ADR 0032 con ruta de proveedor sin fijar; tras una ruta fallida no se sondea ni reintenta; este ADR no autoriza el issue 38 ni iteraciones posteriores; el Operador autorizó en conversación este registro, por lo que se acepta.'
pendientes: ""
superseded_by: 0037-seleccionar-modelos-existentes-con-firstmate
---
# 0034. Reemplazar rutas copilot de factory por openai codex

## Contexto
El Operador estableció como política vigente para todas las Factories, hasta que la cambie, que el acceso por GitHub Copilot se reemplace por la ruta openai-codex soportada con el mismo harness y modelo exacto; el binding canónico de QA usaba Pi con github-copilot/gpt-5.6-terra y los bindings de los roles de Factory vivían solo en el issue 38 y en memoria de sesión, sin registro gobernado en Handbook, mientras ADR 0032 ya registraba el de Mission Control.

## Decisión
Fijar el binding canónico de QA en Pi con openai-codex/gpt-5.6-terra y thinking medium, conservando rol, independencia y restricciones, y adoptar la regla de que toda ruta github-copilot de un rol de Factory se reemplaza por la ruta openai-codex idéntica y soportada del mismo modelo, verificando soporte y autenticación sin exponer credenciales y registrando el proveedor y modelo observados antes del primer dispatch; los modelos Copilot sin ruta openai-codex idéntica no se sustituyen y se reportan como discrepancia, nunca se mapean a otra familia; este ADR no adopta la tabla piloto del issue 38 y no cambia los bindings de Orchestrator, Researcher, Developer ni Reviewer.

## Alternativas descartadas
Tratar el reemplazo como fallback automático de cuota o como reacción al incidente de errores 429 del 2026-09-08 registrado en ADR 0033 se descarta porque el Operador lo definió como política explícita y permanente, y la exclusión de cambios de proveedor, modelo o cuenta de ADR 0033 aplica a la respuesta automática ante cuota de Mission Control, no a esta política. Mapear modelos Claude o Gemini de Copilot a otra familia se descarta por prohibición explícita. Editar credenciales o configuración global del usuario desde una Factory se descarta por exceder su propiedad. Crear un registro de bindings paralelo al issue 38 se descarta porque el issue sigue siendo el backlog autoritativo y este ADR es la autoridad normativa del binding de QA.

## Consecuencias
Las Factories futuras aplican el binding canónico de QA con openai-codex y verifican la ruta observada antes de despachar; el cambio de proveedor de QA no altera el gate de admisión de bindings, que sigue siendo el issue 38 aún no autorizado; Mission Control conserva su binding de ADR 0032 con ruta de proveedor sin fijar; tras una ruta fallida no se sondea ni reintenta; este ADR no autoriza el issue 38 ni iteraciones posteriores; el Operador autorizó en conversación este registro, por lo que se acepta.

## Pendientes
Los modelos Copilot sin ruta openai-codex idéntica y la investigación de alternativas no soportadas quedan pendientes de decisión del Operador.

---
tipo: adr
estado: accepted
fecha: '2026-09-02'
contexto: 'Context-save pertenece a Praxis, sus copias distribuidas están obsoletas y el enlace Gemini está roto; el usuario decidió consolidarlo junto con sweep en el repositorio dedicado de skills.'
decision: 'Este repositorio adopta context-save como skill global portable con procedencia y licencia de Praxis preservadas, lo distribuye mediante enlaces directos y entrega su migración junto con sweep en un único pull request.'
alternativas: 'Mantener context-save en Praxis: descartado porque perpetúa copias distribuidas y un enlace activo roto. Copiarlo sin procedencia ni licencia: descartado porque ocultaría el origen y sus condiciones de redistribución. Entregar cada skill en un PR separado: descartado por decisión explícita del propietario para esta migración.'
consecuencias: 'El repositorio pasa a mantener dos skills adicionales; context-save deberá adaptar contratos específicos de Claude y conservar PolyForm Noncommercial 1.0.0, mientras sweep conserva adaptadores separados para Claude y Pi.'
---
# 0019. Adoptar context save globalmente

## Contexto
Context-save pertenece a Praxis, sus copias distribuidas están obsoletas y el enlace Gemini está roto; el usuario decidió consolidarlo junto con sweep en el repositorio dedicado de skills.

## Decisión
Este repositorio adopta context-save como skill global portable con procedencia y licencia de Praxis preservadas, lo distribuye mediante enlaces directos y entrega su migración junto con sweep en un único pull request.

## Alternativas descartadas
Mantener context-save en Praxis: descartado porque perpetúa copias distribuidas y un enlace activo roto. Copiarlo sin procedencia ni licencia: descartado porque ocultaría el origen y sus condiciones de redistribución. Entregar cada skill en un PR separado: descartado por decisión explícita del propietario para esta migración.

## Consecuencias
El repositorio pasa a mantener dos skills adicionales; context-save deberá adaptar contratos específicos de Claude y conservar PolyForm Noncommercial 1.0.0, mientras sweep conserva adaptadores separados para Claude y Pi.

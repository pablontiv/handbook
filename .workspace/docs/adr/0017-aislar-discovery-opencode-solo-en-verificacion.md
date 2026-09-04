---
tipo: adr
estado: accepted
fecha: '2026-08-26'
contexto: 'OpenCode 1.18.19 descubre nombres idénticos desde ~/.agents/skills y ~/.claude/skills con concurrencia no acotada, por lo que la ruta ganadora cambia entre ejecuciones aunque ambos enlaces apunten al mismo origen canónico.'
decision: 'La verificación gobernada ejecutará OPENCODE_DISABLE_CLAUDE_CODE_SKILLS=1 inline y usará captura respaldada por archivo; el repositorio no persistirá ni administrará configuración de OpenCode.'
alternativas: 'Persistir la variable en ~/.zshenv se descarta porque la configuración del runtime no pertenece a este repositorio; aceptar cualquiera de las dos raíces se descarta para mantener el gate controlado sobre ~/.agents; retirar enlaces Claude se descarta porque rompería su discovery requerido.'
consecuencias: 'Los enlaces de ambas raíces permanecen; el gate OpenCode será determinístico sólo dentro del comando verificador; el uso habitual de OpenCode queda fuera de alcance; la spec y el plan deben documentar la variable inline y la captura por archivo.'
---
# 0017. Aislar discovery opencode solo en verificacion

## Contexto

OpenCode 1.18.19 descubre nombres idénticos desde ~/.agents/skills y ~/.claude/skills con concurrencia no acotada, por lo que la ruta ganadora cambia entre ejecuciones aunque ambos enlaces apunten al mismo origen canónico.

## Decisión

La verificación gobernada ejecutará OPENCODE_DISABLE_CLAUDE_CODE_SKILLS=1 inline y usará captura respaldada por archivo; el repositorio no persistirá ni administrará configuración de OpenCode.

## Alternativas descartadas

Persistir la variable en ~/.zshenv se descarta porque la configuración del runtime no pertenece a este repositorio; aceptar cualquiera de las dos raíces se descarta para mantener el gate controlado sobre ~/.agents; retirar enlaces Claude se descarta porque rompería su discovery requerido.

## Consecuencias

Los enlaces de ambas raíces permanecen; el gate OpenCode será determinístico sólo dentro del comando verificador; el uso habitual de OpenCode queda fuera de alcance; la spec y el plan deben documentar la variable inline y la captura por archivo.

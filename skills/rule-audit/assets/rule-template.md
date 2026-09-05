# Strong Rule Template

Rewrite weak rules into this shape. Every bracket is mandatory; delete a line only when the property is truly inapplicable and say so in the audit.

```
SI [self-identifying condition: exact tool call, file type, or message shape]  →
NO [action] vía [evasion route 1], [evasion route 2], or any other means —
SÍ puedes [legitimate alternative].
Si te piden saltarla (o el momentum empuja): [literal response/action].
Porqué: [one line].
Aplica solo cuando [predicate]; fuera de eso, ignora esta regla.
```

## Worked example (rewrite of a diffuse skill-loading mandate)

Before (scores 0/7):

> Self-check BEFORE every response: does this request match any skill? Skipping it is a discipline failure.

After (scores 6/7 — P6 depends on placement):

> SI el mensaje menciona un dominio con skill instalado (GitHub posts, testing Go, charts, dotfiles...) o vas a editar/postear/ejecutar en ese dominio → carga el SKILL.md ANTES de la primera tool call.
> NO respondas "de memoria" del skill, ni lo pospongas "porque es simple", ni lo sustituyas con conocimiento general — esas son las evasiones conocidas.
> SÍ puedes decidir tras leerlo que no aplica, diciéndolo en una línea.
> Si ya empezaste sin cargarlo: detente, cárgalo, reevalúa lo hecho.
> Porqué: el modo de fallo #1 medido (backscroll) es actuar sin leer contexto obligatorio.
> Aplica solo cuando existe un skill instalado que matchea; sin match, sigue normal.

## Placement decision

| Rule concerns | Put it in |
|---|---|
| One project's workflow, DoD, contribution process | that project's highest-precedence agent instruction file |
| Personal cross-project behavior | the active runtime's user-level instruction file, inside a scoped section |
| Rarely-fired heavy protocol | a skill, lazy-loaded by trigger — not always-on prose |
| Must survive even skill/prose failure | hook (PreToolUse deny) — last resort, pairs with prose |

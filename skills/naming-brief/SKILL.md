---
name: naming-brief
description: "Trigger: name a project, naming brief, nombrar proyecto, project name, name this, name generator prompt. Generate a copy-paste naming brief an LLM uses to propose project names."
license: Apache-2.0
metadata:
  author: "pablontiv"
  version: "1.0"
---

## Activation Contract

Load when the user wants a prompt/brief to name a new project, tool, package, or service —
not the name itself. Triggers: "name this project", "naming brief", "nombrar proyecto",
"genera un prompt para nombrar", "naming prompt".

## Hard Rules

- Produce a BRIEF that an LLM consumes to generate names. Do NOT invent the final name unless
  the user explicitly asks you to also run the brief.
- Fill EVERY placeholder in `assets/naming-brief-template.md` from gathered context. Never emit
  an unfilled `{{PLACEHOLDER}}`.
- If a required input is unknown, ask ONE consolidated question before emitting; do not guess
  lineage, siblings, or constraints.
- Emit the brief inside one fenced code block so it is copy-paste ready.
- Candidate NAMES default to English; instruct other-language or non-English roots only when the
  user explicitly requests it. Root-language hints never override this default on their own.
- Brief default language is English; switch only if the user requests another language.

## Decision Gates

| Situation | Action |
|-----------|--------|
| Project purpose, lineage, siblings all known | Fill template, emit brief |
| Any of purpose / lineage / constraints missing | Ask one batched question, then emit |
| User says "and run it" / "also propose names" | Emit brief, then produce the 12-15 candidates |
| Greenfield, no predecessors | Set LINEAGE to "none — greenfield" |

## Execution Steps

1. Gather: what the project does, lineage/predecessors to echo or avoid, sibling/ecosystem
   names, domain vocabulary + root languages, evocations, hard avoids, tone, length override.
2. Read `assets/naming-brief-template.md`.
3. Replace each `{{...}}` with concrete context; keep section order and the DELIVERABLE block.
4. Emit the filled brief in a single fenced code block.
5. Offer to run the brief (generate candidates) as a follow-up.

## Output Contract

Return one fenced code block containing the fully-filled naming brief (no remaining
placeholders), then one line offering to generate the candidates.

## References

- `assets/naming-brief-template.md` — the brief template with placeholders to fill.

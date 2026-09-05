---
name: adr
metadata:
  author: pablontiv
description: Use when a significant decision has just been made or overturned in a repo - an architecture or tool chosen, an approach rejected with rationale, a convention established, an irreversible trade-off accepted, a decision checkpoint requested by another skill, or a user correction that invalidates a prior decision. Also when the user says "adr", "registra la decisión", "qué decidimos", "por qué se decidió".
---

# ADR

Single owner of ADR policy and schema. Other skills and the output style invoke this skill; they never reimplement it. Mechanics live in `adr.sh` (this directory) over `rootline`; run `adr.sh` with no args for usage. Rootline remains the sole ADR data interface.

## Repository routing

`.workspace/docs/adr` is mandatory when `.workspace/config.yaml` exists. Legacy `docs/adr` and `.adr` detection applies only outside adopted workspaces. Missing workspace governance fails closed; an adopted workspace never falls back to a legacy store.

## Threshold

Record a decision only if it is irreversible, cross-cutting, or carries ongoing operating cost. Reversible local choices get no ADR.

## Quick reference

The `docs/adr` and `.adr` paths below describe legacy/non-adopted operation until a repository creates `.workspace/config.yaml`. In an adopted workspace, versioned commands resolve `.workspace/docs/adr` exclusively.

| Situation | Command |
|---|---|
| Is ADR enabled here? | `adr.sh detect` → prints `.workspace/docs/adr` when adopted, otherwise a legacy dir; fails if none is governed |
| Enable (once per repo) | `adr.sh init versioned` (`.workspace/docs/adr` when adopted; legacy `docs/adr` otherwise) or, only outside adopted workspaces, `adr.sh init local` (`.adr`, self-ignored) |
| Preview without writing | `adr.sh --dry-run propose ...` (the only way to experiment) |
| New decision | `adr.sh propose <slug> <contexto> <decision> <alternativas> <consecuencias> [pendientes]` |
| User approved it in this conversation | `adr.sh accept <NNNN>` right after propose |
| Not yet approved (checkpoint) | leave `proposed`; accept when the user approves |
| Correction invalidates ADR | `adr.sh supersede <NNNN> <slug> <contexto> <decision> <alternativas> <consecuencias>` |
| Recover state after compaction/handover | `adr.sh list`; read accepted ADRs before re-deriving anything |

Field values are one-line summaries written in neutral professional Spanish, regardless of the conversation language. `alternativas` states each rejected option and why — it is the list of what NOT to re-propose. `pendientes` holds unknowns that could still change the decision; leave it out when none.

## Not enabled

In an adopted workspace, `detect` fails closed when `.workspace/docs/adr/.stem` is missing; repair or initialize the workspace-governed store and never offer a legacy fallback.

Outside adopted workspaces, `detect` fails → ask once per repo per session: "¿Desea inicializar ADRs en este repositorio? ¿En modo versionado (docs/adr) o local (.adr)?". Declined → reply "ADR no registrado (no habilitado)" and stop. There is no other store: not engram, not a scratch file, not the chat.

## Enforcement (optional, per repo)

`rootline hooks install` validates ADRs on pre-commit. `rootline query --count --where "estado == 'proposed'" <dir>` gates a merge on unresolved proposals.

## When adr.sh fails

Exit code ≠ 0 → rerun the same command with `bash -x adr.sh ...` and read the last lines. Fix the environment (usually `rootline` missing or the dir lacks `.stem`), then rerun the real command once. Never retry with placeholder values against the real directory; `--dry-run` exists for that. Never write the record by hand.

## Rationalizations seen in testing

| Excuse | Reality |
|---|---|
| "The decision is already final, so accepted directly" | Correct only if the user approved it in this conversation. Otherwise it is a checkpoint: `proposed`. |
| "propose failed, I'll write the .md myself" | A hand-written record skips numbering and validation and is the bug the script prevents. Diagnose with `bash -x`. |
| "I'll try with test values to see if it works" | That pollutes the ADR history. Use `--dry-run`. |
| "The content was in English already" | Values are Spanish by contract; translate before calling. |

## Common mistakes

- Writing the file by hand: numbering, quoting (`fecha`, values with `:`), and validation are the script's job.
- Editing a superseded ADR's body: history is append-only; `supersede` creates the successor and links both.
- Recording routine choices: see Threshold.

---
source: pablontiv/praxis
name: context-save
metadata:
  author: pablontiv
description: |
  Guardar y restaurar estado de sesión estructurado entre sesiones usando
  rootline como capa de datos. Crea snapshots markdown con YAML frontmatter
  capturando trabajo activo, decisiones, estado git, y próximos pasos. Usar
  este skill siempre que el usuario diga "guardar contexto", "save context",
  "save session", "guardar progreso", "retomar", "pick up where I left off",
  "resume", "ya terminé por hoy", "list sessions", o cualquier variación de
  preservar/recuperar estado de trabajo — incluso si no dice "context-save"
  explícitamente, e incluso si solo dice "ya acabé por hoy" o "save my
  progress." Para buscar en el historial de conversaciones pasadas, usar
  backscroll en su lugar.
user-invocable: true
argument-hint: "[save | restore | list]"
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
---

# context-save — Cross-Session Context Persistence

Save and restore session context as structured markdown documents with YAML frontmatter, queryable by rootline. Resolves context loss between sessions.

## Gate Check

Before anything else, verify rootline is available:

```bash
command -v rootline >/dev/null 2>&1 || { echo "ERROR: rootline not found. Install rootline first."; exit 1; }
```

If rootline is missing, stop and tell the user to install it.

## Modes

Parse the arguments supplied when invoking this skill to determine mode. Default is `save` when no argument is provided.

| Argument | Mode |
|----------|------|
| *(none)* | Save |
| `save` | Save |
| `restore` | Restore |
| `list` | List |

---

## Save Mode (no argument, or the `save` argument)

### Step 1: Ensure session-state directory and schema exist

```bash
mkdir -p .claude/session-state
```

If `.claude/session-state/.stem` does not exist, create it with this content:

```yaml
version: 2
schema:
    tipo:
        type: enum
        values: [session-state]
        required: true
    proyecto:
        type: string
        required: true
    branch:
        type: string
    fecha:
        type: string
        required: true
    resumen:
        type: string
        required: true
    estado:
        type: enum
        values: [saved, restored, archived]
        required: true
```

### Step 2: Gather session state

Collect the following information:

```bash
# Project name
basename "$(pwd)"

# Git branch
git branch --show-current 2>/dev/null || echo "no-git"

# Last commit (short hash + subject)
git log --oneline -1 2>/dev/null || echo "no commits"

# Files modified (from git status)
git status --porcelain 2>/dev/null
```

Additionally, capture rootline project state (if rootline-managed directories exist):

```bash
# Discover state: active lines, theories, backlog
rootline query lines/ --where 'tipo == "question"' --output table 2>/dev/null
rootline query theories/ --output table 2>/dev/null
rootline query backlog/ --count 2>/dev/null

# Roadmap state: pending items
if [ -f .claude/roadmap.local.md ]; then
  ROADMAP_ROOT=$(grep 'roadmap-root:' .claude/roadmap.local.md | awk '{print $2}')
  rootline stats "$ROADMAP_ROOT" --output json 2>/dev/null
fi

# Hypothesize state: active investigations
rootline query . --where 'metodo == "hypothesize"' --output table 2>/dev/null
```

Include any non-empty results in the session document under a `## Project State` section.

Also synthesize from the current conversation:
- **Active work**: What was being done in this session (summarize in 1-2 sentences)
- **Key decisions**: Any decisions made during the session (bulleted list)
- **Blockers or next steps**: What should happen next (bulleted list)

### Step 3: Generate filename

```bash
date +%Y-%m-%d-%H%M%S
```

The file will be `.claude/session-state/YYYY-MM-DD-HHMMSS.md`.

### Step 4: Write the session document

Write the file with YAML frontmatter and markdown body:

```markdown
---
tipo: session-state
proyecto: <project-name>
branch: <branch-name>
fecha: "<YYYY-MM-DD>"
resumen: "<One-line summary of what was done>"
estado: saved
---

# Session Context

## Active Work

<What was being done, 1-2 sentences>

## Key Decisions

- <Decision 1>
- <Decision 2>

## Modified Files

- `path/to/file1`
- `path/to/file2`

## Last Commit

<short-hash> <subject>

## Project State

<Active discover lines, theories, roadmap progress, hypothesize investigations — from rootline queries. Omit section if no rootline-managed directories exist.>

## Next Steps

- <What to do next>
- <Blockers if any>
```

### Step 5: Validate

```bash
rootline validate .claude/session-state/<filename>.md --output json
```

If validation fails, fix the frontmatter and retry.

### Step 6: Confirm

Report to the user:
```
Context saved: .claude/session-state/<filename>.md
Summary: <resumen>
```

---

## Restore Mode (the `restore` argument)

### Step 1: Query recent sessions for this project

```bash
PROJECT=$(basename "$(pwd)")
rootline query .claude/session-state/ --where "proyecto == \"$PROJECT\"" --output table
```

### Step 2: Handle results

- **No results found**: Tell the user there are no saved sessions for this project.
- **One result**: Read it directly and proceed to Step 3.
- **Multiple results**: Show the list as a table and ask the user which session to restore. Include fecha and resumen for each.

### Step 3: Read and present the session document

Read the selected file and present a structured summary:

```
RESTORED SESSION — <fecha>
══════════════════════════

Project:  <proyecto>
Branch:   <branch>
Summary:  <resumen>

## Active Work
<content>

## Key Decisions
<content>

## Next Steps
<content>

## Modified Files
<content>
```

### Step 3.5: Enrich with session history (optional)

backscroll: optional — If `command -v backscroll >/dev/null 2>&1`:
```bash
backscroll search "KEY_TOPIC_FROM_RESUMEN" --robot --max-tokens 2000
```
Show related session discussions alongside the saved state to provide broader context. If backscroll is unavailable or returns no results, continue silently.

### Step 4: Update estado

Update the frontmatter field `estado` from `saved` to `restored` in the session file.

### Step 5: Validate

```bash
rootline validate .claude/session-state/<filename>.md --output json
```

### Step 6: Suggest next actions

Based on the "Next Steps" section, suggest concrete actions the user can take to continue their work.

---

## List Mode (the `list` argument)

### Step 1: Query all sessions

```bash
rootline query .claude/session-state/ --output table
```

### Step 2: Present results

Display the table output directly. If no sessions exist, inform the user.

---

## Conventions

- Gate check: `command -v rootline` before any operation
- Always create `.stem` schema if it does not exist before writing session files
- Keep resumen under 80 characters
- Use ISO date format (YYYY-MM-DD) for fecha
- Filenames use timestamp format: YYYY-MM-DD-HHMMSS.md
- Validate every written file with rootline immediately after writing
- Do not overwrite existing session files; always create new ones
- The body is English; frontmatter field names are Spanish to match rootline conventions

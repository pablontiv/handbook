# Subagent contract and orchestrator duties

## Evidence contract (system prompt, all three agents)

1. Every verdict states the exact command and its **literal** output.
2. A claim of the form "X is absent" requires the command that establishes it.
3. State what the command does **not** prove.
4. Use runtime-specific delivery. Claude adapters use parent-visible `SendMessage` delivery to `main`; Pi adapters return their final response directly through `subagent_run`. Do not assume one runtime's plain final text semantics apply to another. *15 of 22 Claude reports were lost to missing `SendMessage` on 2026-08-26.*

## Orchestrator duties

1. Verify every claim that underwrites a deletion, before deleting.
2. Reject a conclusion that arrives without its command.
3. **Sweep the repos the agents touched when they finish.** *One left a stray `pr-182-check` branch that only surfaced on re-inventory.*

## Honest limitation

`tools:` restricts *which tools* an agent has, not *which Bash commands* it may run. An `Explore` agent has no Edit or Write and still ran `git merge` in the wiki repository on 2026-08-26. Bundled agents reduce this risk; they do not eliminate it. The only real barrier is a permission allowlist.

---

Prefer `sweep-scout` for bulk. All six false reports on 2026-08-26 were verdicts; none was a raw fact.

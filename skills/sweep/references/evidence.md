# Evidence traps — why every rule exists

Fourteen entries. Each carries the failure that produced it, because a rule without its scar gets ignored.

## Git traps

1. **`ahead > 0` proves nothing after a squash.** Squash rewrites the commit.

2. **`[gone]` upstream does not mean unpublished.** It is what a merged-and-deleted PR branch looks like.

3. **`git diff base..branch` (two dots) invents deletions.** It renders everything the BASE gained since divergence as if the branch deleted it. Use three dots for "what did this branch change". *2026-08-26: reported that four wiki branches destroyed `.agents/skills`; the three-dot diff over those paths is empty — master added those dirs on 08-24, the merge-base is 06-23. Same cause produced a false "−9087/+1917, deletes startuplock" where the real figure was +19342/−632.*

4. **Staged work is invisible to `git diff`.** Read column 1 of `status --porcelain`: `M ` and `A ` mean staged. Use `git diff --cached`. *2026-08-26: a worktree holding 529 staged insertions, including a new test file, was classified abandoned.*

5. **Grepping a NAME proves only the name is absent, never the capability.** Compare contract and behaviour, or file by file against base. *2026-08-26: `grep -c detectTypeMismatch` returned 0 and the work was called unlanded; master shipped it as `detectTypeRepresentationRepairs`.*

6. **Unrelated history defeats every merge-base test.** *2026-08-26: `feature/net10-migration` had no merge-base with main — main was re-rooted after it branched.*

## CI and platform traps

7. **The same check failing across the whole fleet is infrastructure, not the PR.** Read the log before calling it a finding. *2026-08-26: gitleaks failed on every dependabot PR with `HttpError 403 Resource not accessible by integration` — nothing was scanned. It passes on push, where the token is not restricted.*

8. **`startup_failure` is not a check.** It never appears in `statusCheckRollup`, so the PR looks like it has no checks. It means the workflow did not start.

9. **A reusable workflow cannot request more permissions than its caller grants.** *2026-08-26: adding `pull-requests: read` to a shared gitleaks workflow left 9 repositories with no CI at all. The detonator was not the commit — it was moving the floating major tag. After touching a reusable workflow, wait for a green run in one consumer BEFORE moving the alias.*

10. **`gh api repos/X/rules/branches/Y` only sees rulesets.** An empty result is not proof there is no protection; classic branch protection is invisible to it.

11. **macOS has no `timeout` and no `gtimeout`.** *2026-08-26: wrapping fetch and gh in it emptied 89 verdicts silently.*

12. **zsh.** `set -- $var` does not word-split; a `?` in a URL is eaten by the glob; `cmd || other` can swallow a rejected push and report success.

## Instruction discipline

These two are the only entries the backscroll corrections census marks as **chronic across sessions**, not incidents.

13. **Read the instruction before acting on it.** Before any destructive action, restate the received scope in one line and check it against what is about to run. *Recurring corrections: "no te pedí a ti que borraras, te dije que ya estaban borradas"; "te dije que lo copiaras global solamente, olvídate de dotfiles".*

14. **Do not contradict or re-ask without consulting history.** Query backscroll before returning a question to the user or asserting anything about a past decision. *2026-08-26: the same question was returned three times while its answer had been written by the user in their own issue on 08-20.*

## Cross-session rule

Another session may be mutating the same machine. Before "recovering" deleted refs, find who deleted them and under what instruction (`~/.claude/projects/<repo>/*.jsonl`). A report expires in minutes: re-verify state at the moment of acting, never inherit it. *2026-08-26: five client branches were restored, undoing a deliberate deletion the user had approved in another session.*

## Design-document rule

When a branch ships its own spec, that spec is the best completeness test — it states what its author promised. *2026-08-26: it exposed that `rescue/recovered-source-accounting` carried the design of its titular feature but not the feature.*

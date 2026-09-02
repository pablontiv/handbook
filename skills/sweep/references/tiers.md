# Tiers and protection rules

## Local tiers (worktrees and branches)

Evaluate in order and stop at the first match. Only `orphan`, `superseded` and `stale` are ever deleted.

| # | Tier | Condition |
|---|---|---|
| 1 | orphan | listed by `worktree prune --dry-run` |
| 2 | unknown | `gh` failed, or the repo has no remote |
| 3 | held | protected by a rule below |
| 4 | **superseded** | content verifiably already in base — file by file, never by name or by `ahead` |
| 5 | stale | all PRs MERGED, or (`ahead == 0` AND clean AND no PR) |
| 6 | risky | dirty, or untracked, or `ahead > 0` with no MERGED PR |
| 7 | active | any PR OPEN |

`superseded` precedes `stale` because its evidence is stronger. The report must distinguish them: "already landed" is not "PR merged". *It occurred three times on 2026-08-26 — backscroll PR #60 (260 conflicts to land nothing), ten dependabot PRs proposing an already-applied bump, and a branch calling a CLI surface that does not exist.*

## PR tiers

| Tier | Condition | Action |
|---|---|---|
| superseded | base already has the change | close with evidence, never merge |
| blocked-infra | the same check fails fleet-wide | read the log; not the PR's fault |
| blocked-policy | mergeable but policy refuses | needs `--admin` and explicit authorization |
| blocked-ci | a real, PR-specific failure | report the cause, do not retry |
| **breaking-bump** | dependabot crossing a MAJOR boundary | **never low-risk**, whatever the author |
| low-risk | dependabot non-major, or docs/tests only | auto-merge |
| needs-review | everything else | never mutate |

`breaking-bump` exists because picokit 0.4→1.0 broke smoke tests on three platforms while classified low-risk purely for being dependabot-authored.

## Protection rules (tier `held`)

1. The branch of a `risky` worktree is itself held.
2. A `backup/*` branch is held while the work it backs has an OPEN PR.
3. The local default branch is never a deletion candidate.
4. **A ref that exists only locally is irreversible.** If `git ls-remote` does not have it, deleting it has no undo. *An agent proposed deleting `feature/net10-migration` — 137 commits of client code with no remote copy — precisely because it was orphaned.*
5. **Client or work code is held when in doubt.** If the remote is not the user's, the default is `held`, not `stale`.
6. **What another session deleted deliberately is not lost.** Before restoring, find who deleted it and why.

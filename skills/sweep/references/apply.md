# Apply phase — deletion order and evidence gates

## Deletion order

1. `worktree remove` — remove the working directory
2. `worktree prune` — clean orphaned admin dirs
3. `branch -d` — delete the branch

A branch cannot be deleted while a worktree holds it.

## Squash-merged branches

`branch -d` refuses every squash-merged branch. That is trap 1 surfacing at delete time — the normal path, not a signal of risk. Expect this refusal as part of the standard flow.

## The `-D` evidence gate

Escalate from `-d` to `-D` only with independent evidence that the content landed. Two admissible forms only:

1. `gh pr list --head BRANCH --state all` reports MERGED
2. The content is verifiably in base, compared file by file

Record which one justified each `-D` use.

## `worktree remove --force` is forbidden by default

A refusal to remove a worktree without `--force` means state you had not accounted for — re-tier it as `risky`. One documented exception exists (verified 2026-08-26): a worktree containing gitlinks with no `.gitmodules` (agent repro dirs) refuses even with `--force`. The path there is `rm -rf` the directory, then `worktree prune`.

## Applying PR decisions

1. **Gate check before any mutation.** `gh pr view N --repo OWNER/REPO --json mergeable,reviewDecision,statusCheckRollup`. Any check not `SUCCESS`/`NEUTRAL`/`SKIPPED` — failed OR still pending — blocks. `reviewDecision == "CHANGES_REQUESTED"` blocks. `mergeable == "CONFLICTING"` blocks.

2. **Read the failure before trusting it.** If the same check fails on every PR in the repo or across the fleet, it is infrastructure, not the PR — cross-reference `references/evidence.md` trap 7. Also: `startup_failure` never appears in `statusCheckRollup`, so a PR whose workflow did not start looks like it has no checks at all (trap 8).

3. **Approve, then merge** — for a bot-authored PR, self-approval is permitted: `gh pr review N --repo OWNER/REPO --approve` then `gh pr merge N --repo OWNER/REPO --squash`. Approval first, because merge fails on a repo that requires review.

4. **On conflict**, post exactly one `@dependabot rebase` comment per PR — dependabot PRs only, and skip it if such a comment already exists (`gh pr view N --comments`). Then move to the next PR. Same rule if the merge error contains `not up to date with the base branch`.

5. **Closing a `superseded` PR** requires the evidence in the comment: which commit or PR on the base already carries the change. Never close on a hunch.

6. **`breaking-bump` is never auto-merged**, whoever authored it.

7. **One failing PR never aborts the sweep** — continue to the next.

## `--admin` authorization on `gh pr merge`

`--admin` on `gh pr merge` requires explicit user authorization in the current session, and only where the substantive gate is green. Never use it to force a red check through.

## Empty worktree parents

After removing the last worktree under a `<repo>-worktrees/` directory, the empty parent remains. Use `rmdir` to clean it — never `rm -rf` — so a non-empty directory fails loudly instead of being destroyed silently.

## Local default branch

The local default branch is never a deletion candidate. If it is behind and not checked out, fast-forward it with `git update-ref` instead:

```bash
git -C "$repo" update-ref refs/heads/main refs/remotes/origin/main
```

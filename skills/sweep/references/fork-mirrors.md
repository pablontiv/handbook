# Fork mirror detection

A fork accumulates remote branches that are exact copies of upstream refs. They carry zero unique work and are pure noise.

## Detection command

```bash
git for-each-ref --format='%(refname:lstrip=3) %(symref)' refs/remotes/fork \
  | awk '$2 == "" {print $1}' \
  | while read -r b; do
      f=$(git rev-parse -q --verify "fork/$b"); o=$(git rev-parse -q --verify "origin/$b")
      [ -n "$f" ] && [ "$f" = "$o" ] && echo "MIRROR $b"
    done
```

Equal SHA on both remotes = **mirror**, safe to delete from the fork. Unequal or missing upstream = the user's own work, classify via Phase 3.

## Precondition — verify upstream ref coverage BEFORE trusting any verdict

```bash
git config --get-all remote.origin.fetch                      # must be a wildcard refspec
o=$(git for-each-ref refs/remotes/origin | wc -l)
f=$(git for-each-ref refs/remotes/fork   | wc -l)
```

A narrow refspec such as `+refs/heads/main:refs/remotes/origin/main` fetches only one upstream branch, so `origin/<branch>` is missing for everything else and the SHA test can never match. The result is not "no mirrors" — it is **no data**, and it labels every fork branch as the user's own work, the exact inverse of the truth. `hermes-agent` hit this: origin 2 refs, fork 1306, verdict "1305 propias".

If the refspec is not a wildcard, or `o` is small relative to `f`, tier the whole remote **`unknown`**, report the refspec as the cause, and stop. Do not propose deletions. Widening the refspec and refetching is the user's call — it pulls the upstream's full ref set and is not a side effect a sweep should cause.

## Enumeration gotcha

Do NOT enumerate with `git branch -r --list 'fork/*'`: it shortens the symbolic ref `refs/remotes/fork/HEAD` to the bare string `fork`, which then survives a naive `grep -v '^HEAD'` and is classified as a phantom branch. Filter on an empty `%(symref)` instead. Guard the comparison with `[ -n "$f" ]` so two missing refs never compare equal.

## Reporting and deletion

Report mirrors as a single aggregate count, not a 145-line list.

Fork mirrors, batched (a `--delete` per branch is 145 round-trips):

```bash
sed 's|^|:refs/heads/|' mirrors.txt | xargs -n 25 git push fork
```

Two traps in that one line:

- Do NOT build the refspec list into a shell variable and pass it unquoted. Under **zsh** an unquoted `$refs` does not word-split, so the whole list arrives as a single refspec and git dies with `invalid refspec`. `xargs` sidesteps it.
- Do NOT test success with `if git push … | tail -2`: that reads the exit status of `tail`, which is always 0, and reports a clean sweep while nothing was deleted. Check the exit status of the push itself, then confirm against `git ls-remote --heads fork | wc -l`.

Always verify deletions against the remote, never against your own counter.

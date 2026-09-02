#!/bin/sh
# Per-repo facts as TSV. Collects ONLY facts — no tiers, no verdicts.
# Columns: kind repo path branch base ahead dirty staged untracked last pr remote
set -u
repo=${1:-}; [ -n "$repo" ] || { printf 'usage: facts.sh REPO\n' >&2; exit 2; }
git -C "$repo" rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0
main=$(git -C "$repo" rev-parse --show-toplevel)

git -C "$repo" fetch --all --quiet 2>/dev/null   # stale refs give wrong verdicts

base=$(git -C "$repo" symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null)
if [ -z "$base" ]; then
  for b in main master; do
    git -C "$repo" show-ref -q "refs/remotes/origin/$b" && base="origin/$b" && break
  done
fi
slug=$(cd "$repo" && gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null)

prstate() {
  [ -n "$slug" ] || { printf 'nogh'; return; }
  gh pr list -R "$slug" --head "$1" --state all --json number,state \
    -q '.[]|"#\(.number) \(.state)"' 2>/dev/null | tr '\n' ',';
}

# --- worktrees (excluding the main working tree)
git -C "$repo" worktree list --porcelain | awk '
  /^worktree /{p=$2}
  /^branch /{sub("refs/heads/","",$2); print p"\t"$2}
  /^detached$/{print p"\t(detached)"}' \
| while IFS="$(printf '\t')" read -r wt br; do
    [ "$wt" = "$main" ] && continue
    if [ -d "$wt" ]; then
      st=$(git -C "$wt" status --porcelain 2>/dev/null)
      # Column 1 = index. `M `/`A ` is STAGED and invisible to `git diff`.
      staged=$(printf '%s\n' "$st" | grep -c '^[MARCD]' || true)
      dirty=$(printf  '%s\n' "$st" | grep -c '^.[MD]'   || true)
      untr=$(printf   '%s\n' "$st" | grep -c '^??'      || true)
      last=$(git -C "$wt" log -1 --format=%cs 2>/dev/null)
      ahead="?"
      [ -n "$base" ] && [ "$br" != "(detached)" ] && \
        ahead=$(git -C "$repo" rev-list --count "$base..$br" 2>/dev/null)
      pr=""; [ "$br" != "(detached)" ] && pr=$(prstate "$br")
      remote=0
      [ "$br" != "(detached)" ] && \
        remote=$(git -C "$repo" ls-remote --heads origin "$br" 2>/dev/null | wc -l | tr -d ' ')
      printf 'WT\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$repo" "$wt" "$br" "$base" "$ahead" "$dirty" "$staged" "$untr" "$last" "$pr" "$remote"
    else
      printf 'WT\t%s\t%s\t%s\t%s\t?\t?\t?\t?\t\tmissing-dir\t0\n' "$repo" "$wt" "$br" "$base"
    fi
  done

# --- local branches not checked out in any worktree
checked=$(git -C "$repo" worktree list --porcelain | awk '/^branch /{sub("refs/heads/","",$2); print $2}')
git -C "$repo" for-each-ref --format='%(refname:short)' refs/heads \
| while IFS= read -r br; do
    printf '%s\n' "$checked" | grep -qx "$br" && continue
    ahead=""; [ -n "$base" ] && ahead=$(git -C "$repo" rev-list --count "$base..$br" 2>/dev/null)
    last=$(git -C "$repo" log -1 --format=%cs "$br" 2>/dev/null)
    remote=$(git -C "$repo" ls-remote --heads origin "$br" 2>/dev/null | wc -l | tr -d ' ')
    printf 'BR\t%s\t\t%s\t%s\t%s\t\t\t\t%s\t%s\t%s\n' \
      "$repo" "$br" "$base" "$ahead" "$last" "$(prstate "$br")" "$remote"
  done

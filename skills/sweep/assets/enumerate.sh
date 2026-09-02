#!/bin/sh
# Three independent enumerations, unioned. None alone is sufficient:
# admin dirs catch worktrees whose directory was deleted; .git FILES catch
# worktrees whose admin dir was pruned; the repo list catches the rest.
# $HOME must stay depth-bounded: an unbounded find did not finish in 11 min.
set -u
[ $# -ge 1 ] || { printf 'usage: enumerate.sh ROOT [ROOT...]\n' >&2; exit 2; }
for root in "$@"; do
  [ -d "$root" ] || continue
  case "$root" in
    "$HOME") depth="-maxdepth 4" ;;
    *)       depth="" ;;
  esac
  # shellcheck disable=SC2086
  find "$root" $depth -type d -name .git \
    -not -path '*/node_modules/*' -not -path '*/.venv/*' \
    -not -path '*/.cache/*' -not -path '*/plugins/*' 2>/dev/null \
    | sed 's|/\.git$||'
  # A .git FILE marks a submodule OR a worktree; only the pointer differs.
  # Without this filter a repo with vendored submodules reports them all.
  # shellcheck disable=SC2086
  find "$root" $depth -type f -name .git \
    -not -path '*/node_modules/*' -not -path '*/.cache/*' 2>/dev/null \
    | while IFS= read -r f; do
        grep -q 'gitdir:.*/\.git/worktrees/' "$f" 2>/dev/null && dirname "$f"
      done
done | sort -u

#!/bin/sh
# Fixture-based tests for the sweep assets. Creates throwaway repos under a
# temp dir, never touches anything outside it.
set -u
here=$(cd "$(dirname "$0")" && pwd)
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
pass=0; fail=0
ok()   { pass=$((pass+1)); printf '  ok    %s\n' "$1"; }
bad()  { fail=$((fail+1)); printf '  FAIL  %s\n     %s\n' "$1" "$2"; }
is()   { [ "$2" = "$3" ] && ok "$1" || bad "$1" "got '$2' want '$3'"; }

# --- fixture: a repo, a worktree with a staged file, a submodule-looking .git file
git init -q "$tmp/repo"; cd "$tmp/repo"
git config user.email t@t; git config user.name t
echo a > a.txt; git add a.txt; git commit -qm init
git branch -q feature
git worktree add -q "$tmp/repo/.worktrees/wt" feature
echo staged > "$tmp/repo/.worktrees/wt/s.txt"
git -C "$tmp/repo/.worktrees/wt" add s.txt
mkdir -p "$tmp/repo/vendor/sub"
printf 'gitdir: ../../.git/modules/vendor/sub\n' > "$tmp/repo/vendor/sub/.git"

# --- enumerate.sh finds the repo and does NOT report the submodule as a worktree
out=$("$here/enumerate.sh" "$tmp" 2>/dev/null)
case "$out" in *"$tmp/repo"*) ok "enumerate finds the repo" ;;
  *) bad "enumerate finds the repo" "$out" ;; esac
case "$out" in *vendor/sub*) bad "enumerate excludes submodules" "$out" ;;
  *) ok "enumerate excludes submodules" ;; esac

# --- facts.sh reports the STAGED file (invisible to git diff)
row=$("$here/facts.sh" "$tmp/repo" 2>/dev/null | awk -F'\t' '$1=="WT"{print; exit}')
is "facts marks the worktree" "$(printf '%s' "$row" | cut -f1)" "WT"
is "facts counts staged work"  "$(printf '%s' "$row" | cut -f8)" "1"

# --- preflight.sh fails loudly when gh is unusable, never silently
if PATH=/nonexistent "$here/preflight.sh" >/dev/null 2>&1
then bad "preflight fails without gh" "exited 0"
else ok "preflight fails without gh"; fi

printf '\n%s passed, %s failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]

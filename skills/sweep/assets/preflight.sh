#!/bin/sh
# Phase 0. Exits non-zero to STOP the sweep. A silently-degraded pipeline
# produces confidently wrong verdicts: on 2026-08-26 a missing `timeout`
# emptied 89 of them without a single error message.
set -u
repo=""; known=""
while [ $# -gt 0 ]; do
  case "$1" in
    --repo) repo=$2; shift 2 ;;
    --known-merged) known=$2; shift 2 ;;
    *) printf 'unknown argument: %s\n' "$1" >&2; exit 2 ;;
  esac
done
fail=0
note() { printf '%s\n' "$1" >&2; fail=1; }

command -v git >/dev/null || note "git not found"
command -v gh  >/dev/null || note "gh not found"
if command -v timeout >/dev/null; then printf 'timeout: available\n'
else printf 'timeout: ABSENT — never wrap fetch/gh in it\n'; fi

gh auth status >/dev/null 2>&1 || note "gh is not authenticated"

# Canary: a pipeline that returns nothing is indistinguishable from "no PR".
if [ -n "$repo" ] && [ -n "$known" ]; then
  slug=$(cd "$repo" && gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null)
  if [ -z "$slug" ]; then note "cannot resolve a GitHub slug for $repo"
  else
    st=$(gh pr list -R "$slug" --head "$known" --state all --json state -q '.[0].state' 2>/dev/null)
    [ "$st" = "MERGED" ] || note "canary failed: $known reports '${st:-empty}', expected MERGED"
  fi
fi

# Another session may be mutating the same machine (spec §2, cross-session rule).
if [ -d "$HOME/.claude/projects" ]; then
  n=$(find "$HOME/.claude/projects" -name '*.jsonl' -mmin -30 2>/dev/null | wc -l | tr -d ' ')
  [ "$n" -gt 1 ] && printf 'note: %s session transcripts touched in the last 30 min — another session may be active\n' "$n"
fi

[ "$fail" -eq 0 ] || { printf 'PREFLIGHT FAILED — do not trust any verdict\n' >&2; exit 1; }
printf 'PREFLIGHT OK\n'

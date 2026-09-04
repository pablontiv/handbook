#!/usr/bin/env bash
# ADR mechanics over rootline. Policy lives in SKILL.md.
# Usage: adr.sh detect | init <versioned|local> | list
#        adr.sh [--dry-run] propose <slug> <contexto> <decision> <alternativas> <consecuencias> [pendientes]
#        adr.sh accept <NNNN>
#        adr.sh [--dry-run] supersede <NNNN> <slug> <contexto> <decision> <alternativas> <consecuencias> [pendientes]
# Field values: one line each, neutral professional Spanish. --dry-run prints the record to stdout and writes nothing.
# propose is idempotent per slug: an existing <NNNN>-<slug>.md is returned, never duplicated.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

workspace_active() { [ -f .workspace/config.yaml ]; }

versioned_dir() {
  if workspace_active; then
    printf '%s\n' .workspace/docs/adr
  else
    printf '%s\n' docs/adr
  fi
}

detect() {
  if workspace_active; then
    [ -f .workspace/docs/adr/.stem ] || return 1
    printf '%s\n' .workspace/docs/adr
  elif [ -f docs/adr/.stem ]; then
    printf '%s\n' docs/adr
  elif [ -f .adr/.stem ]; then
    printf '%s\n' .adr
  else
    return 1
  fi
}

need_dir() {
  DIR=$(detect) || {
    echo "adr: no governed ADR store resolved for this workspace or repository" >&2
    exit 2
  }
}

cmd_init() {
  case "${1:-}" in
    versioned) DIR=$(versioned_dir) ;;
    local)
      if workspace_active; then
        echo "adr: local ADR store is not allowed in an adopted workspace" >&2
        exit 2
      fi
      DIR=.adr
      ;;
    *) echo "usage: adr.sh init versioned|local" >&2; exit 2 ;;
  esac
  mkdir -p "$DIR"; cp "$HERE/adr.stem" "$DIR/.stem"
  if [ "$DIR" = .adr ]; then printf '*\n' > .adr/.gitignore; fi
  echo "$DIR"
}

yq() { printf "'%s'" "${1//\'/\'\'}"; }   # single-quoted YAML scalar; safe for ':' and quotes

write_record() { # file num title ctx dec alt con [pend] [supersedes]
  local f=$1 num=$2 title=$3 ctx=$4 dec=$5 alt=$6 con=$7 pend=${8:-} sup=${9:-}
  {
    echo '---'
    echo 'tipo: adr'
    echo 'estado: proposed'
    echo "fecha: $(yq "$(date +%F)")"
    echo "contexto: $(yq "$ctx")"
    echo "decision: $(yq "$dec")"
    echo "alternativas: $(yq "$alt")"
    echo "consecuencias: $(yq "$con")"
    if [ -n "$pend" ]; then echo "pendientes: $(yq "$pend")"; fi
    echo '---'
    printf '# %s. %s\n\n' "$num" "$title"
    if [ -n "$sup" ]; then printf 'Reemplaza a %s.\n\n' "$sup"; fi
    printf '## Contexto\n%s\n\n## Decisión\n%s\n\n## Alternativas descartadas\n%s\n\n## Consecuencias\n%s\n' "$ctx" "$dec" "$alt" "$con"
    if [ -n "$pend" ]; then printf '\n## Pendientes\n%s\n' "$pend"; fi
  } > "$f"
}

cmd_propose() { # slug ctx dec alt con [pend] [supersedes]
  need_dir
  [ $# -ge 5 ] || { echo "usage: adr.sh propose <slug> <contexto> <decision> <alternativas> <consecuencias> [pendientes]" >&2; exit 2; }
  local slug=$1; shift
  [[ "$slug" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]] || { echo "adr: slug must be kebab-case: $slug" >&2; exit 2; }
  local existing; existing=$(ls "$DIR"/[0-9][0-9][0-9][0-9]-"$slug".md 2>/dev/null | head -1 || true)
  if [ -n "$existing" ]; then echo "adr: already exists, not duplicated: $existing" >&2; echo "$existing"; return 0; fi
  local n; n=$( (ls "$DIR"/[0-9][0-9][0-9][0-9]-*.md 2>/dev/null || true) | wc -l | tr -d ' ')
  local num; num=$(printf '%04d' $((n+1)))
  local f="$DIR/$num-$slug.md"
  local title; title=$(echo "$slug" | tr '-' ' ' | awk '{print toupper(substr($0,1,1)) substr($0,2)}')
  if [ "$DRY" = 1 ]; then write_record /dev/stdout "$num" "$title" "$@"; echo "(dry-run: would write $f)" >&2; return 0; fi
  write_record "$f" "$num" "$title" "$@"
  rootline validate "$f" -o table >&2
  echo "$f"
}

cmd_accept() {
  need_dir; local f; f=$(ls "$DIR"/"${1:?NNNN}"-*.md)
  if grep -q '^pendientes:' "$f"; then rootline set "$f" estado=accepted pendientes="" >&2; else rootline set "$f" estado=accepted >&2; fi
  echo "$f"
}

cmd_supersede() { # NNNN slug ctx dec alt con [pend]
  need_dir; local old; old=$(ls "$DIR"/"${1:?NNNN}"-*.md); shift
  local slug=$1 ctx=$2 dec=$3 alt=$4 con=$5 pend=${6:-}
  local new; new=$(cmd_propose "$slug" "$ctx" "$dec" "$alt" "$con" "$pend" "$(basename "$old" .md)")
  [ "$DRY" = 1 ] && { echo "(dry-run: would mark $old superseded)" >&2; return 0; }
  rootline set "$old" estado=superseded superseded_by="$(basename "$new" .md)" >&2
  echo "$new"
}

cmd_list() { need_dir; rootline query --select path,estado,decision -o table "$DIR"; }

DRY=0; [ "${1:-}" = --dry-run ] && { DRY=1; shift; }
case "${1:-}" in
  detect) detect ;; init) shift; cmd_init "$@" ;; propose) shift; cmd_propose "$@" ;;
  accept) shift; cmd_accept "$@" ;; supersede) shift; cmd_supersede "$@" ;; list) cmd_list ;;
  *) sed -n '2,4p' "$0" >&2; exit 2 ;;
esac

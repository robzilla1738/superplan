#!/usr/bin/env bash
# repo-state.sh — evaluate the COMPLETE working-tree state relative to a baseline commit.
#
# Why this exists
# ---------------
# Supergoal's final audit and per-phase cleanliness checks must see every change an
# autonomous run produced — whether it was committed or left sitting in the working
# tree. A plain `git diff <baseline>..HEAD` only compares two commits, so a run that
# never commits looks completely empty: deliverables read as "missing" and cleanliness
# greps read as "0 debug prints" no matter what was actually written. This helper is the
# single source of truth for the corrected comparison (see
# references/repo-state-comparison.md).
#
# The strategy (complete state vs baseline)
# -----------------------------------------
#   tracked changes (committed + staged + unstaged + deleted)
#       = git diff <baseline>            # single revision, NOT <baseline>..HEAD
#         -> diffs the WORKING TREE against the baseline commit, so it already
#            includes staged, unstaged, and any post-baseline commits.
#   untracked deliverables (new files never `git add`-ed)
#       = git ls-files --others --exclude-standard
#         -> untracked files are diff-invisible, so they are detected separately.
#   invalid / unavailable baseline ("no-git" sentinel, bogus sha, or non-repo)
#       -> `deliverable` degrades gracefully to a filesystem existence test and SAYS SO
#          in its output ("baseline unavailable").
#       -> `changed-files` / `added-lines` have no meaningful fallback: without a baseline
#          there is no such thing as "what changed". They REFUSE, loudly, on stderr, with
#          exit 3 — because printing an empty result would be read as "nothing changed"
#          by every caller that pipes this into `wc -l` / `grep -c`, which is the exact
#          silent-empty failure this helper was written to prevent.
#
# This script never mutates the repository or the index. All output is for the audit
# transcript. Paths containing spaces are handled (callers must quote the path argument).
#
# Usage:
#   repo-state.sh deliverable   <baseline> <path>
#       -> "present — <evidence>" (exit 0) | "missing" (exit 1)
#   repo-state.sh changed-files <baseline>
#       -> newline-delimited paths changed since baseline (tracked + untracked + deleted)
#          (unresolvable baseline -> empty stdout, diagnostic on stderr, exit 3)
#   repo-state.sh added-lines   <baseline>
#       -> every added/new line since baseline: tracked-diff '+' lines plus the full body
#          of each untracked file (every line is "new"). Feed to grep for cleanliness counts.
#          (unresolvable baseline -> empty stdout, diagnostic on stderr, exit 3)

set -uo pipefail

in_git_repo() { git rev-parse --is-inside-work-tree >/dev/null 2>&1; }

# baseline_ok <ref> — true only when <ref> resolves to a real commit in this repo.
baseline_ok() {
  local b="${1:-}"
  [ -n "$b" ] || return 1
  [ "$b" = "no-git" ] && return 1
  git rev-parse --verify --quiet "${b}^{commit}" >/dev/null 2>&1
}

# refuse_unevaluable <subcommand> <baseline> — the baseline could not be resolved, so
# there is nothing to compare the working tree against.
#
# WHY THIS IS NOT A `return 0`: the callers pipe this subcommand straight into `wc -l`
# or `grep -c` for cleanliness and change counts. An empty stdout there reads as
# "0 changed files" / "0 debug prints" — indistinguishable from a genuinely clean run,
# and the audit records "clean" for a check that never ran. That is the same
# silent-empty failure described at the top of this file, arriving through a different
# door. So: stdout stays EMPTY (nothing must be miscounted), the reason goes to STDERR
# (which survives `| wc -l`, unlike the exit status), and the exit code is a dedicated
# 3 — distinct from 1 ("missing") and 2 ("usage") so a caller can tell the three apart.
refuse_unevaluable() {
  local sub="$1" baseline="$2" reason
  if in_git_repo; then
    reason="baseline '${baseline}' does not resolve to a commit in this repository"
  else
    reason="not inside a git work tree"
  fi
  {
    printf 'repo-state.sh: %s UNEVALUABLE — %s.\n' "$sub" "$reason"
    printf '  Refusing to print an empty result: an empty answer here would be read as\n'
    printf '  "nothing changed", and that is not what happened — there was nothing to\n'
    printf '  compare against. Fix the baseline, or use "deliverable", which has a\n'
    printf '  documented filesystem fallback.\n'
  } >&2
  return 3
}

cmd_deliverable() {
  local baseline="$1" path="$2"

  if in_git_repo && baseline_ok "$baseline"; then
    # 1) tracked change vs baseline: committed, staged, unstaged, or deleted.
    local stat
    stat="$(git diff --stat "$baseline" -- "$path" 2>/dev/null || true)"
    if [ -n "$stat" ]; then
      printf 'present — changed vs baseline (%s)\n' \
        "$(printf '%s' "$stat" | tail -1 | sed 's/^[[:space:]]*//')"
      return 0
    fi
    # 2) brand-new untracked deliverable (diff-invisible).
    local untracked
    untracked="$(git ls-files --others --exclude-standard -- "$path" 2>/dev/null | head -1 || true)"
    if [ -n "$untracked" ]; then
      printf 'present — untracked new file (%s)\n' "$untracked"
      return 0
    fi
    # 3) backward-compat net: the path exists / is tracked but is unchanged this run.
    if [ -e "$path" ] || [ -n "$(git ls-files -- "$path" 2>/dev/null | head -1 || true)" ]; then
      printf 'present — exists, unchanged since baseline\n'
      return 0
    fi
    printf 'missing\n'
    return 1
  fi

  # Fallback: baseline missing/invalid or not a git repo — existence only.
  if [ -e "$path" ]; then
    printf 'present — exists on disk (baseline unavailable)\n'
    return 0
  fi
  if in_git_repo && [ -n "$(git ls-files -- "$path" 2>/dev/null | head -1 || true)" ]; then
    printf 'present — tracked (baseline unavailable)\n'
    return 0
  fi
  printf 'missing\n'
  return 1
}

cmd_changed_files() {
  local baseline="$1"
  if ! in_git_repo || ! baseline_ok "$baseline"; then
    refuse_unevaluable changed-files "$baseline"
    return $?
  fi
  {
    git diff --name-only "$baseline" 2>/dev/null || true   # modified/staged/deleted
    git ls-files --others --exclude-standard 2>/dev/null || true   # untracked
  } | LC_ALL=C sort -u | sed '/^$/d'
  return 0
}

cmd_added_lines() {
  local baseline="$1"
  if ! in_git_repo || ! baseline_ok "$baseline"; then
    refuse_unevaluable added-lines "$baseline"
    return $?
  fi
  # Added lines from tracked changes (strip the leading '+', skip the '+++' file header).
  git diff "$baseline" 2>/dev/null | grep '^+' | grep -v '^+++' | sed 's/^+//' || true
  # Full body of every untracked file — each line counts as newly added.
  # Skip binaries: added-lines feeds text greps, so binary bodies are only noise.
  git ls-files --others --exclude-standard -z 2>/dev/null | while IFS= read -r -d '' f; do
    [ -f "$f" ] && LC_ALL=C grep -Iq . "$f" 2>/dev/null && cat -- "$f"
  done
  return 0
}

sub="${1:-}"
shift 2>/dev/null || true
case "$sub" in
  deliverable)
    [ "$#" -ge 2 ] || { echo "usage: repo-state.sh deliverable <baseline> <path>" >&2; exit 2; }
    cmd_deliverable "$1" "$2"
    ;;
  changed-files)
    [ "$#" -ge 1 ] || { echo "usage: repo-state.sh changed-files <baseline>" >&2; exit 2; }
    cmd_changed_files "$1"
    ;;
  added-lines)
    [ "$#" -ge 1 ] || { echo "usage: repo-state.sh added-lines <baseline>" >&2; exit 2; }
    cmd_added_lines "$1"
    ;;
  ""|-h|--help|help)
    cat >&2 <<'EOF'
repo-state.sh — evaluate the complete working-tree state vs a baseline commit.

  repo-state.sh deliverable   <baseline> <path>   present|missing (+ evidence), exit 0|1
  repo-state.sh changed-files <baseline>          paths changed since baseline
  repo-state.sh added-lines   <baseline>          added/new lines since baseline

Exit codes: 0 ok / 1 deliverable missing / 2 usage / 3 baseline unevaluable
(changed-files, added-lines — stdout stays empty, reason on stderr).

<baseline> is a commit sha (or "no-git" / any invalid ref to force the filesystem
fallback — which only `deliverable` has). Compares the working tree — not just HEAD — so uncommitted, staged, and
untracked work is included. See references/repo-state-comparison.md.
EOF
    exit 2
    ;;
  *)
    echo "repo-state.sh: unknown subcommand '$sub' (try deliverable|changed-files|added-lines)" >&2
    exit 2
    ;;
esac

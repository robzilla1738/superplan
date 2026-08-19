# CLAUDE.md

Project-level instructions for Claude Code sessions opened in this repo. Read `AGENTS.md` first for the authoritative project doc; this file adds Claude-Code-specific tips on top.

## Quick orientation

This repo is the source of truth for the `supergoal` skill — a Claude Code plugin that turns vague build requests into deeply-planned, autonomously-executed `/goal` runs backed by a v1 run kernel (`run.json`, `events.jsonl`, evidence files, phase gates, final audit, and `report.html`).

Full project doc: see [AGENTS.md](AGENTS.md).

## Working in this repo from Claude Code

### File map you actually edit

- `skills/supergoal/SKILL.md` — the skill content. Edit here for behavioral changes.
- `skills/supergoal/references/*.md` — progressive-disclosure docs the agent reads when needed (`planning-depth.md`, `phase-design.md`, `goal-format.md`, `repo-state-comparison.md`).
- `skills/supergoal/scripts/claim-run.sh` — atomically claims a unique per-run dir (`.supergoal/<slug>-XXXXXX` via `mktemp -d`) so concurrent runs in one working tree can't clobber each other. Edit here to change the namespacing/slug logic; tested by `tests/claim-run.test.sh`.
- `skills/supergoal/scripts/sg.py` — v1 run kernel. Edit here to change manifest validation, event recording, phase gates, audit, resume, or report generation; tested by `tests/sg-run-kernel.test.sh`.
- `skills/supergoal/scripts/repo-state.sh` — the complete-working-tree-vs-baseline comparison helper. Edit here to change how audit deliverables detect committed/staged/unstaged/deleted/untracked work. Copied into the run's `.supergoal/<run-id>/` dir at Stage 7; tested by `tests/repo-state.test.sh`.
- `skills/supergoal/templates/PROTOCOL.md` — v1 execution loop + evidence vault + phase gates + failure recovery + final audit/report. Edit here when changing the per-`/goal`-session protocol. Paths use the `{{RUN_ROOT}}` placeholder, `sed`-substituted to the concrete run dir at Stage 7.
- `skills/supergoal/templates/STATE.md` — human-readable progress mirror. `run.json` is canonical.
- `skills/supergoal/templates/ROADMAP.md` — phase plan rendered from `run.json`.
- `tests/claim-run.test.sh` — fixture tests for `claim-run.sh`, incl. the concurrent-claim race (repo-only; run with `bash tests/claim-run.test.sh`).
- `tests/repo-state.test.sh` — fixture tests for `repo-state.sh` (repo-only; run with `bash tests/repo-state.test.sh`).
- `tests/sg-run-kernel.test.sh` — fixture tests for `sg.py` (repo-only; run with `bash tests/sg-run-kernel.test.sh`).
- `.claude-plugin/plugin.json` — bump `version` on every shipped change so the marketplace cache refreshes.
- `CHANGELOG.md` — add a top entry per release.
- `README.md` — public-facing only. Edit for docs / Mermaid diagram tweaks. No version bump needed.

### Before shipping a change

```bash
claude plugin validate .claude-plugin/plugin.json
claude plugin validate .claude-plugin/marketplace.json
bash skills/supergoal/scripts/validate-phase.sh skills/supergoal/templates/phase-goal.txt
bash tests/sg-run-kernel.test.sh
bash tests/repo-state.test.sh   # expects: 47 passed, 0 failed
bash tests/claim-run.test.sh    # expects: 23 passed, 0 failed
```

The first three should return `✔ Validation passed`; both test runs should end `All fixture scenarios passed.`

### Local install testing

After committing + pushing + bumping version:

```bash
claude plugin marketplace update supergoal
claude plugin update supergoal@supergoal
# then in a Claude Code session:
/reload-plugins
/supergoal <some test task>
```

If `claude plugin update` reports "already at latest" but you know you pushed changes, you forgot to bump `version` in `plugin.json`.

### Codex sync

Claude Code auto-updates via the marketplace. Codex doesn't have a marketplace — it's a manual file copy. After any shipped change:

```bash
rm -rf ~/.codex/skills/supergoal
cp -R /Users/robert/Code/supergoal/skills/supergoal ~/.codex/skills/supergoal
```

## Conventions that matter here

### Commit attribution

**Do not add `Co-Authored-By` trailers to any commit message.** All commits are authored solely by the repo owner (`robzilla1738 <robertcourson1738@gmail.com>`). This rule has been load-bearing during cleanup of prior co-author attribution; preserve it going forward.

### Naming

Everything in lowercase `supergoal`. The plugin name, marketplace name, skill frontmatter `name:`, slash command (`/supergoal`), artifact dir (`.supergoal/`), and transcript markers (`SUPERGOAL_*`) all match. If you find a stray `superplan` outside the CHANGELOG, it's a bug — the CHANGELOG keeps historical names intentionally.

### Version bumping

Source of truth is `.claude-plugin/plugin.json`'s `version`. Must match README's "Current: v..." line, the latest `CHANGELOG.md` entry, and the "Working state (as of vX.Y.Z — …)" line in `AGENTS.md`. Tag the same number: `git tag -a v1.0.x -m "..." && git push origin v1.0.x`.

### Slash command mechanics

`/goal` on both Claude Code and Codex is a **user-initiated** command. Agent text containing `/goal "..."` does **not** fire the command. Stage 7's design is an honest one-paste handoff — the planner prints a fenced code block with the `/goal` line, instructs the user to paste it, and stops. Never reframe this as automatic dispatch.

`/goal` itself is built-in on Claude Code (no plugin dependency) per the official docs.

### Transcript markers

**Inside the `/goal` session** (the autonomous run). The agent must print these named blocks; they're how the host evaluator + the user judge progress:

- `SUPERGOAL_RUN_KERNEL_READY`
- `SUPERGOAL_PHASE_START` / `SUPERGOAL_PHASE_VERIFY` / `PHASE_GATE_VERIFY` / `SCOPE_DRIFT` / `TRUST_DEBT` / `SUPERGOAL_PHASE_DONE`
- `MEMORY_SAVED`
- `AUDIT_START` / `AUDIT_VERIFY` / `AUDIT_GAPS` / `AUDIT_COMPLETE` / `AUDIT_HANDOFF`
- `RUN_REPORT_WRITTEN`
- `SUPERGOAL_RUN_COMPLETE`
- `FAILURE_PROBE` / `FAILURE_ESCALATE` / `FAILURE_HANDOFF`

**Inside the planner session** (Supergoal stages, before the `/goal` is dispatched). The user sees these but the `/goal` evaluator doesn't (it isn't active yet):

- `Self-critique:` — inside the Stage 6 plan-review summary (Stage 6a — 1–3 findings or `clean`)
- `PREFLIGHT_GREEN` / `PREFLIGHT_RED` — Stage 6.5 output after running the deduplicated mandatory commands once

These are how the `/goal` evaluator decides the run is done. Don't rename the `/goal`-session markers without thinking through the protocol + the end-state condition string.

The `/goal` end-state requires `AUDIT_COMPLETE`, `RUN_REPORT_WRITTEN`, and `SUPERGOAL_RUN_COMPLETE`, with one `SUPERGOAL_PHASE_DONE` per phase and no `FAILURE_HANDOFF` or `AUDIT_HANDOFF`.

## Common pitfalls (field-tested)

- **Forgot to bump `version` after a content change** → marketplace cache stays stale. Symptom: `claude plugin update` says "already at latest". Fix: bump and re-push.
- **Mass find/replace missed `.gitignore`** → it has no extension so most find filters skip it. Always check it separately after global renames.
- **GitHub Contributors sidebar shows stale data after a history rewrite** → it's a stats-endpoint caching lag, clears on its own (minutes to hours). The actual `/contributors` API is what to trust.
- **`/plugin marketplace add owner/repo` shorthand defaults to SSH** → fails for users without GitHub SSH keys. README leads with the HTTPS URL form for this reason.
- **Codex install is a one-way copy** → users have to re-clone on update. Mention in any breaking-change CHANGELOG.
- **The skill description is the trigger** → tweak it carefully. Lead with `/supergoal` and natural-language phrases users actually type. Keep it pushy.
- **Updating SKILL.md/PROTOCOL.md? Codex stays in sync only via manual `rm -rf … && cp -R …`.** After any shipped change, re-run the copy and verify with `diff -r skills/supergoal ~/.codex/skills/supergoal` → expect `(no output)`. AGENTS.md's "Working state" section documents the latest verified sync.
- **v1 deliverable checks compare the COMPLETE working tree vs `run.baseline_ref` via `repo-state.sh`** — not a `<Baseline ref>..HEAD` commit range. Tracked changes come from the single-revision `git diff <Baseline ref>` (committed + staged + unstaged + deleted); untracked files are detected separately. If a user runs `/supergoal` in a directory without git history, `repo-state.sh` degrades to a filesystem existence check. The one documented strategy lives in `references/repo-state-comparison.md`; the logic is implemented once in `repo-state.sh` and tested by `tests/repo-state.test.sh`.
- **Honesty test for Stage 6a self-critique**: if it produces `clean` on essentially every real plan, it's theater and gets dropped. AGENTS.md "Open work" tracks the heuristic — don't defend the feature for its own sake.
- **v1 namespaces every run under `.supergoal/<run-id>/`** (claimed atomically by `scripts/claim-run.sh` via `mktemp -d`). This stops two concurrent `/supergoal` runs from clobbering runtime artifacts. `PROTOCOL.md` + phase specs use a `{{RUN_ROOT}}` placeholder — Stage 7 `sed`-substitutes the concrete dir into the copied `PROTOCOL.md`, and the planner fills it into each phase spec. Namespacing protects artifacts only: two `/goal` executions in the same working tree still edit the same source files, so use separate `git worktree`s for parallel execution.

## When in doubt

Read `AGENTS.md`. It's the authoritative project doc. This file is a Claude-Code-flavored skim on top.

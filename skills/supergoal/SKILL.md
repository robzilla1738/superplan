---
name: supergoal
description: Plan and autonomously build a software task end-to-end with the Supergoal v1 run kernel. Triggered by `/supergoal`, "plan and ship X", "supercharged plan", "autonomous build", "plan it out and don't stop until it's done", "I don't want to babysit this", or any non-trivial feature/refactor/redesign the user wants driven to completion. Strongly prefer over a plain plan when the user signals "every aspect", "fully", "perfectly", "until done", or wants depth + autonomous follow-through. Recons the codebase, applies memory, writes a structured run.json contract, records events/evidence, enforces phase gates, gets one confirmation, then prepares a single ready-to-paste `/goal` command that drives execution to final audit and report generation. Works on Claude Code and Codex.
argument-hint: <describe what you want built, fixed, or shipped>
---

# Supergoal

You are running the Supergoal workflow. The user's task is:

$ARGUMENTS

Your job: **plan deeply, then auto-execute under a single `/goal`** until the task is verifiably complete across every phase.

## What "every aspect is perfect" means here

The user's bar is high. Translate it into measurable criteria, not vibes:

- **Functional** — the feature works for the golden path and the obvious edge cases
- **Engineering** — build, typecheck, lint, tests all pass; no new warnings
- **Polish** — UX/copy, error states, empty states, loading states are handled
- **Hardening** — security review, input validation, no obvious regressions
- **Verification** — every phase produces transcript evidence the evaluator can see

If a phase can't be measured, it isn't a phase. Rewrite it until it can.

## How this skill works (one-shot summary)

0. **Available context** — preload memory; detect available tools (Context7, WebSearch, MCPs, skills); resume any in-progress Supergoal state
1. **Intake** — restate, classify, ask enough questions to cover every material gap. Greenfield walks the full category checklist (platform, stack, design direction, integrations, scope, audience, perf, data model) in batches of up to 4 until everything material is filled in; brownfield asks 0–2 since recon answers most structural questions.
2. **Recon** — parallel codebase + environment scan
3. **Deep think** — research best practices with whatever tools exist (optional, not required); list top-3 risks + dependencies
4. **Decompose** — derive phase count from the task itself; no fixed cap
5. **Compile the run contract** — write `run.json` first, then render `ROADMAP.md`, `STATE.md`, and one phase spec per phase from that manifest
6. **Plan review** — validate the run kernel, show summary + concrete revision menu; wait for explicit go/no-go
7. **Hand off one ready-to-paste `/goal`** with a short end-state condition; the user pastes once, and the agent inside that fresh `/goal` session executes phases sequentially with event telemetry, evidence files, mechanical phase gates, retry + fix-spec recovery, memory writeback, final audit, and `report.html`

Two human gates only: **clarifying questions for true gaps (Stage 1)** and **plan review (Stage 6)**. Everything else runs autonomously, but v1 makes the run inspectable through `run.json`, `events.jsonl`, `evidence/`, phase gates, and a generated report.

### Why one `/goal`, not a chain

`/goal` in both Claude Code and Codex takes a **short end-state condition**, not a long task body. A fast evaluator checks the condition against the transcript after each turn and auto-continues until it holds. Supergoal v1 uses one `/goal` for the whole run; phase work lives in files the agent reads from disk; the condition is "all phases done, `AUDIT_COMPLETE`, `RUN_REPORT_WRITTEN`, then `SUPERGOAL_RUN_COMPLETE`." No char budget, no inter-session chain dispatch, no fragility.

## Locate the skill directory

```bash
SUPERGOAL_DIR=$(dirname "$(ls -1 \
  "$HOME/.claude/skills/supergoal/SKILL.md" \
  "$HOME/.codex/skills/supergoal/SKILL.md" \
  "$PWD/.claude/skills/supergoal/SKILL.md" \
  "$PWD/.codex/skills/supergoal/SKILL.md" \
  2>/dev/null | head -n1)")
export SUPERGOAL_DIR
# $SUPERGOAL_BASE holds ALL runs. Each run gets its own namespaced subdir under it
# (claimed in Stage 0) so two runs in the same working tree never clobber each other.
# The per-run dir — $SUPERGOAL_ROOT — is set in Stage 0, not here.
export SUPERGOAL_BASE="${SUPERGOAL_BASE:-.supergoal}"
mkdir -p "$SUPERGOAL_BASE"
echo "SUPERGOAL_DIR=$SUPERGOAL_DIR"
echo "SUPERGOAL_BASE=$SUPERGOAL_BASE"
```

All artifacts for a run live under `$SUPERGOAL_ROOT` — a per-run subdir of `$SUPERGOAL_BASE`, claimed in Stage 0. Skill assets (scripts, references, templates) live under `$SUPERGOAL_DIR`.

---

## Stage 0 — Available context (memory + tools)

Before doing anything else, sense what's available this session. This is what makes the run frictionless — if memory already knows the user's preferences, don't ask; if a tool isn't available, don't try to call it.

### Claim the run namespace (resume or fresh)

**Do this first** — before memory preload, recon, or anything that writes a file. Every run gets its **own** subdirectory under `$SUPERGOAL_BASE`, so two runs started in the same working tree can never overwrite each other's STATE/ROADMAP/phases (the v0.7 fix for concurrent-run clobbering).

```bash
# Look for an in-progress run to resume. Scan per-run dirs AND the legacy flat layout
# (.supergoal/STATE.md from pre-0.7 runs). A run is "active" unless its STATE.md Status
# is COMPLETE. (The unfilled template's "PLANNING → IN_PROGRESS → COMPLETE" arrow line
# is not a terminal COMPLETE, so it correctly reads as active.)
ACTIVE_RUNS=""
for s in "$SUPERGOAL_BASE"/*/STATE.md "$SUPERGOAL_BASE"/STATE.md; do
  [ -f "$s" ] || continue
  grep -Eqi 'status:\**[[:space:]]*complete[[:space:]]*$' "$s" && continue
  ACTIVE_RUNS="${ACTIVE_RUNS}$(dirname "$s")"$'\n'
done
for r in "$SUPERGOAL_BASE"/*/run.json; do
  [ -f "$r" ] || continue
  grep -Eqi '"status"[[:space:]]*:[[:space:]]*"COMPLETE"' "$r" && continue
  ACTIVE_RUNS="${ACTIVE_RUNS}$(dirname "$r")"$'\n'
done
printf 'Active runs in this tree:\n%s\n' "${ACTIVE_RUNS:-  (none)}"
```

Then decide:

- **Fresh run (default for a new task)** — claim a unique namespace:
  ```bash
  SUPERGOAL_ROOT="$(bash "$SUPERGOAL_DIR/scripts/claim-run.sh" "$ARGUMENTS")"
  export SUPERGOAL_ROOT
  echo "SUPERGOAL_ROOT=$SUPERGOAL_ROOT"   # e.g. .supergoal/add-dark-mode-Ab3Kx9
  ```
  `claim-run.sh` uses `mktemp -d` to create-and-claim the dir atomically, so two simultaneous starts always get distinct dirs — the race that caused the overwrite is gone.

- **Resume** — if an active run clearly matches this task (its STATE.md title ≈ `$ARGUMENTS`, or the user said "resume"/"continue"), set `SUPERGOAL_ROOT` to that run dir and follow the resume path (don't re-plan). If several active runs exist and intent is ambiguous, ask with **one** `AskUserQuestion` which to resume — or to start fresh.

**Coexistence notice (load-bearing — print it).** If `ACTIVE_RUNS` is non-empty and you're starting a fresh run, surface this before continuing:

> ⚠ Another Supergoal run is active in this working tree (`<list>`). Your planning artifacts are isolated under `<SUPERGOAL_ROOT>`, so they won't collide — **but two `/goal` executions in the same working tree will still edit the same source files and clobber each other's code.** Namespacing protects the plan, not the build. For true parallel execution, run each task in its own `git worktree`; or resume the existing run instead of starting a second.

That boundary is the honest one: namespacing removes the artifact overwrite that happens during planning; it does not make two autonomous builds in one tree safe.

### Memory preload

```bash
# Detect a memory directory. Common locations:
MEM_DIR=""
for cand in \
  "$HOME/.claude/projects/-Users-$(whoami)/memory" \
  "$HOME/.claude/memory" \
  "$PWD/.claude/memory" \
  "$SUPERGOAL_ROOT/memory"; do
  [[ -d "$cand" ]] && MEM_DIR="$cand" && break
done
echo "MEM_DIR=$MEM_DIR"

if [[ -n "$MEM_DIR" && -f "$MEM_DIR/MEMORY.md" ]]; then
  echo "--- MEMORY INDEX ---"
  cat "$MEM_DIR/MEMORY.md"
fi
```

Read the index. Then **selectively** read individual memory files that look relevant to the task (feedback memories about the stack/domain, user role memories, related project memories). Don't dump them all into context — pull what matters.

Capture applicable memory hits in `$SUPERGOAL_ROOT/applied-memories.md` (one line per memory: name, why-applicable, what-it-changes). Surface them in Stage 1 as "Applied from memory: …" so the user can see what's being inherited and correct anything stale.

### Tool discovery

Tools differ between sessions and hosts (Claude Code vs Codex, different MCP server sets). Detect, don't assume:

- **Context7** — available if `mcp__claude_ai_Context7__resolve-library-id` or similar is in the tool list. If absent, skip it; rely on training-cutoff knowledge + WebSearch if that's present.
- **WebSearch / WebFetch** — available if listed. If neither, skip web research.
- **Project skills** — check the available-skills list for domain-relevant skills (e.g. `mobile-ios-design`, `clerk-auth`, `expo-dev-client`) and note them in `$SUPERGOAL_ROOT/applied-skills.md` to invoke from inside phase goals if relevant.
- **Prior Supergoal state** — handled above in "Claim the run namespace": active runs are detected per-namespace and either resumed (reuse their `$SUPERGOAL_ROOT`) or explicitly coexisted-with.

Write detected tools to `$SUPERGOAL_ROOT/tools.md`. Stage 3 and the phase goals reference this file when deciding what to invoke.

### Resume detection

If you resolved to resume a run in "Claim the run namespace", run `python "$SUPERGOAL_DIR/scripts/sg.py" resume "$SUPERGOAL_ROOT"` if `run.json` exists. For old markdown-only runs, the same command prints `LEGACY_RUN_FALLBACK` from `STATE.md`. If the run is `IN_PROGRESS` / `READY_TO_DISPATCH` / `BLOCKED` with a phase pending, **do not re-plan**. Print a one-line "Resuming Supergoal from phase N (`$SUPERGOAL_ROOT`)" and jump straight to Stage 6 (plan review) with the existing artifacts, or directly to Stage 7 (dispatch) if the user confirms resume.

---

## Stage 1 — Intake & clarifying questions

Echo the task back in **one sentence**. Then classify it (tags can combine):

| Tag | Trigger |
|---|---|
| `greenfield` | Request implies a new project; cwd has no `.git/` or empty tree |
| `brownfield` | Change in an existing repo |
| `bugfix` | Mentions "bug", "broken", "fails", "regression" |
| `refactor` | Mentions "refactor", "clean up", "restructure" |
| `ui` | Mentions "design", "polish", "UI", "UX", "responsive", "redesign" |

**Calibrate the question count to the context.** Greenfield has no codebase to scan, so it needs enough verbal context to plan well — never artificially limit questions when material info is missing. Brownfield runs lean on recon, so questions are sparse.

### Greenfield — gather enough context to plan well

A new project has no signal beyond the user's prompt + memory. The planner's job in Stage 1 is to **enumerate every category that meaningfully shapes the plan, eliminate the ones already answered by memory or prompt, and ask about every remaining one**. Don't stop until every material gap is filled.

**Category checklist — work through this for every greenfield run:**

| Category | Why it shapes the plan |
|---|---|
| **Target platform / surface** | iOS, Android, web, desktop, CLI, multi — the biggest fork. Different stacks, different phases. |
| **Stack / framework preference** | Next.js vs SvelteKit, Expo vs bare RN, FastAPI vs Django, Swift vs SwiftUI vs UIKit, etc. Affects every phase. |
| **Design direction / aesthetic** | Minimal-mono, brutalist, glass morphism, Apple-native, dashboardy-corporate, retro, etc. Determines tokens, component shapes, Polish phase content. |
| **Integration anchors** | Auth provider, database, payments, hosting, analytics, file storage, email — anything that locks in a vendor up front. |
| **Scope cut-line** | MVP-this-week vs full feature; what's explicitly out of scope vs deferred to v2. |
| **Primary use case / audience** | Solo-dev tool, team SaaS, public consumer app, internal admin — drives auth flow, onboarding shape, error tolerance. |
| **Performance / scale constraints** | "Realtime sub-100ms" vs "background batch ok"; expected traffic; offline-first or online-only. Only ask if non-trivial. |
| **Data model anchors** | If the prompt implies data, ask the shape ("users + posts? users + projects + tasks?"). Only if not obvious. |

**Process:**

1. For each category, ask: *did the user's prompt mention it? Does memory have a relevant preference?*
2. If yes → use that, surface as "Applied from memory: …" or "From your prompt: …"
3. If no → that category becomes a question.
4. Ask all remaining questions in **batches of up to 4** (the `AskUserQuestion` tool ceiling) until every material gap is filled. Two batches is fine for greenfield; three is rare but allowed if a complex task genuinely warrants it.
5. Within each batch, lead with the highest-leverage choices (the ones that change the phase shape most).

**Anti-patterns:**

- **Don't ask one batch and then plan around silent assumptions for the rest.** If you're about to assume the design direction, the auth provider, AND the scope cut-line, that's 3 assumptions and one batch of follow-up is cheaper than getting it wrong.
- **Don't pad questions when memory/prompt already covers them.** Reading "I want a SwiftUI iOS app with Liquid Glass" → don't ask "what platform?", "what stack?", or "what aesthetic?". Just ask about integrations, scope, and use case.
- **Don't ask micro-details** that belong in plan review: naming, file paths, copy wording, color palette specifics, library minor versions, default test framework if the stack has one. Those go into ROADMAP.md as assumptions and surface in Stage 6's revision menu.

### Brownfield — 0–2 questions, one batch

The codebase plus recon scripts already answer most structural questions (stack, package manager, build/test/lint, conventions, what exists). Ask only for **true gaps** memory + prompt + recon leave open:

- Scope cut-line ("just this surface, or also touch the related ones?")
- Compatibility surface ("backwards compat with the old API path, or break it?")
- Primary fork when ambiguous ("which of these two existing patterns do you want me to extend?")

Most well-described brownfield tasks ask **zero questions**.

### In both modes

1. Lead with "Applied from memory: …" and "From your prompt: …" so the user sees what's being inherited or read off before answering.
2. Each `AskUserQuestion` batch caps at 4 (tool limit). Greenfield can use multiple sequential batches; brownfield is one batch max.
3. If you genuinely need zero questions, say "No clarifying questions — proceeding from prompt + memory + recon." and move straight to Stage 2.
4. Never ask about anything you can responsibly assume — those go into the Stage 6 plan review for one-click correction.

---

## Stage 2 — Recon (parallel)

Run recon scripts in parallel. They populate context files under `$SUPERGOAL_ROOT/`.

### Brownfield path

```bash
bash "$SUPERGOAL_DIR/scripts/detect-stack.sh"   > "$SUPERGOAL_ROOT/context.md"
bash "$SUPERGOAL_DIR/scripts/summarize-repo.sh" > "$SUPERGOAL_ROOT/repo-map.md"
```

### Greenfield path

```bash
bash "$SUPERGOAL_DIR/scripts/detect-env.sh" > "$SUPERGOAL_ROOT/context.md"
```

Read the outputs. Then print a **5-line summary** to the user: stack, package manager, build/test/lint commands, notable modules (if any), risky areas. This is what tells them you've actually understood their codebase before planning.

---

## Stage 3 — Deep think

This is the difference between a generic plan and a Supergoal. Spend real cycles here — but use only what's available.

**Required regardless of tools:**
- Identify the **top 3 risks**: what's most likely to go wrong, what's hardest to undo, what's easy to miss until shipped.
- Identify **non-obvious dependencies**: things that have to happen in a specific order or block other work.
- Apply memory hits from `$SUPERGOAL_ROOT/applied-memories.md` — bake them into goals, constraints, or risk mitigations.

**Optional, use if available** (check `$SUPERGOAL_ROOT/tools.md`):
- **Context7** — if available, query current docs for any third-party SDK touched. Don't plan against stale APIs. If unavailable, lean on training-cutoff knowledge and call it out as an assumption ("planned against my training-cutoff understanding of Expo SDK — verify in phase 1").
- **WebSearch** — if available, look up current consensus on patterns you're unsure about (auth flows, payment idempotency, accessibility standards). If unavailable, skip.
- **Project skills** — if relevant skills are listed in `$SUPERGOAL_ROOT/applied-skills.md` (e.g. `clerk-auth`, `mobile-ios-design`), note them in THINKING.md as "consult `<skill>` skill during phase N" so the executor invokes them at the right moment.

**Write `$SUPERGOAL_ROOT/THINKING.md`** with sections: Goals, Constraints, Risks, Dependencies, Open Questions (already-assumed), Memory hits applied, Tools/skills relied on, Best Practices Applied. Keep it tight — 1–2 pages. This is the substrate the roadmap derives from.

See `references/planning-depth.md` for the bar to clear here.

---

## Stage 4 — Decompose into phases

Break the work into **as many phases as the task actually needs** — no fixed count, no upper or lower cap. The right number falls out of the work itself: how many independently verifiable units exist between empty repo (or current state) and "done perfectly." A trivial change might need 2 phases; a typical feature 4–6; a full-stack greenfield app 8–12; a major migration 15+. Read `references/phase-design.md` for how to slice well — the short version:

- Each phase delivers something **verifiable on its own** (it builds, it passes its own tests, you could ship it as a partial increment)
- Phases have **explicit dependencies** (phase 3 depends on 1 and 2)
- The **last phase is always a "Polish & Harden" phase** covering edge cases, error states, security, accessibility, copy, perf — this is how "every aspect is perfect" gets enforced
- For UI work, include a dedicated **visual polish** phase with screenshot/visual evidence requirements
- For brownfield, include an early **safety net** phase if test coverage is thin (add characterization tests before changing behavior)

Each phase has:
- **Name** (5 words max, action-first: "Build auth foundation")
- **Why** (1 sentence)
- **Deliverables** (concrete files/features that will exist when done)
- **Acceptance criteria** (5–10 measurable items)
- **Allowed paths** (the edit scope the phase gate will enforce)
- **Criteria verification class** for each criterion: `mechanical`, `human`, or `trust-prior`
- **Mandatory command ids** (from the run-level command registry)
- **Evidence required** (files under `evidence/phase-N/`, not only transcript claims)
- **Dependencies** (which prior phases must be done)

---

## Stage 5 — Compile the run contract and render specs

Write the structured contract first. Markdown files are mirrors for humans and the executor, not the source of truth.

Artifacts, all under `$SUPERGOAL_ROOT/`:

1. **`run.json`** — canonical v1 manifest. Required top-level fields:
   - `schema_version: "1.0"`
   - `run`: id, title, task, status, current_phase, run_root, baseline_ref, host, created_at, last_update
   - `commands`: command registry with `id`, `class`, `command`, `required`
   - `phases`: ordered phase objects with `id`, `name`, `status`, `allowed_paths`, `depends_on`, `criteria`, `commands`, `deliverables`, `required_evidence`
2. **`events.jsonl`** — append-only event stream. Start it with a `run.plan` event.
3. **`ROADMAP.md`** — rendered from `run.json` (template at `$SUPERGOAL_DIR/templates/ROADMAP.md`).
4. **`STATE.md`** — human-readable mirror (template at `$SUPERGOAL_DIR/templates/STATE.md`).
5. **`phases/phase-N.md`** — one work-spec file per phase (template at `$SUPERGOAL_DIR/templates/phase-goal.txt`). Any length; these are read from disk by the executor, not passed to `/goal`.
6. **`evidence/phase-N/{commands,diffs,screenshots}/`** — create these directories up front so the executor knows where proof belongs.

Each phase object in `run.json` must include:

```json
{
  "id": 1,
  "name": "Build auth foundation",
  "status": "pending",
  "allowed_paths": ["src/auth/", "tests/auth/"],
  "depends_on": [],
  "criteria": [
    {"id": "p1-c1", "text": "Auth middleware rejects anonymous requests", "verification": "mechanical", "evidence": ["commands/test.log"]}
  ],
  "commands": ["test"],
  "deliverables": ["src/auth/middleware.ts", "tests/auth/middleware.test.ts"],
  "required_evidence": ["commands/test.log", "diffs/summary.txt"]
}
```

Use only these verification classes:

- `mechanical` — script, command, file inspection, grep, or deterministic check can verify it.
- `human` — subjective UI/content judgment that must be honestly labeled.
- `trust-prior` — audit cannot re-check it mechanically and must rely on phase evidence.

Validate each spec with `bash $SUPERGOAL_DIR/scripts/validate-phase.sh "$SUPERGOAL_ROOT/phases/phase-N.md"`. Then run:

```bash
python "$SUPERGOAL_DIR/scripts/sg.py" validate-run "$SUPERGOAL_ROOT"
```

Fix `PLAN_LINT_RED` output before Stage 6. No invalid v1 manifest may be dispatched.

---

## Stage 6 — Plan review & confirmation (hard gate)

Before any `/goal` is dispatched, show the user the full plan and **ask for explicit confirmation**. The chain runs unsupervised once it starts, so this is the last cheap moment to correct course. Skipping this step is a bug.

### Stage 6a — Self-critique pass (cheap, runs once)

Plan-time is the cheapest moment to catch the most expensive bugs (vague criteria, mis-sliced phases, weak dependencies). Before printing the summary, run **one** self-critique turn answering exactly three questions:

1. **Falsifiability:** Is every acceptance criterion across every phase a yes/no test, not a vibe? Flag any that say "works", "good", "ready", "correct" without a measurable predicate. Each criterion must have a valid `verification` class in `run.json`.
2. **Phase atomicity:** Is any phase secretly two coherent units packed into one (deliverables that don't share a verify gate, names containing "and", split-able dependency lines)?
3. **Weakest dependency:** Where would a partial failure cascade worst? (e.g., phase 2 unblocks 3, 4, and 5 — if 2 ships shaky, three phases inherit the bug.)

**Output:**

- If clean: record `Self-critique: clean.` and proceed.
- If findings: list 1–3 specific findings (no padding). For falsifiability issues, **rewrite the offending criteria in place** in `run.json`, the affected `phase-N.md` files, and `ROADMAP.md` before printing the summary. Re-run `validate-phase.sh` on touched specs and `python "$SUPERGOAL_DIR/scripts/sg.py" validate-run "$SUPERGOAL_ROOT"`. Surface the rewrites in the Stage 6 summary so the user sees the post-critique version, not the pre-critique one.

Honesty check: this pass must produce findings *or* a "clean" verdict per run. If it silently always says "clean" on real plans, it's theater and we remove it in the next release.

### Stage 6b — Summary print

Print a scannable summary in this exact shape:

```
✓ Plan ready for review. <N> phases.

Applied from memory:
  - <memory hit 1>
  - <memory hit 2>
  (or: "none — clean run")

Phases:
  1. <name> — <one-line deliverable>
  2. <name> — <one-line deliverable>
  ...
  N. Polish & Harden — every aspect verified

Stack: <stack> · pkg: <pm> · build/test/lint: <commands>

Key assumptions (correct any that are wrong):
  - <assumption 1>
  - <assumption 2>
  - <assumption 3>

Top risks & mitigations:
  1. <risk> → <mitigation>
  2. <risk> → <mitigation>
  3. <risk> → <mitigation>

Self-critique:
  - <finding 1, or "clean">
  - <finding 2 (optional)>
  - <finding 3 (optional)>
  (criteria rewrites applied in-place if any were flagged)

Artifacts:
  Manifest: <run-root>/run.json (source of truth)
  Events: <run-root>/events.jsonl
  Roadmap: <run-root>/ROADMAP.md
  Progress: <run-root>/STATE.md (human mirror)
  Phase specs: <run-root>/phases/phase-1..N.md
  Evidence vault: <run-root>/evidence/

Trust debt:
  <mechanical> mechanical / <human> human / <trust-prior> trust-prior
  <pct>% trust-prior (flag if >30%)

Once you confirm, I'll print a ready-to-paste `/goal` line. Paste it
once and the chain runs through to completion, with auto-retry and
fix-spec recovery, phase gates, final audit, and a local report.
```

Then call `AskUserQuestion` with one question, header "Start chain?", offering **concrete revision modes** (not a vague "revise plan"):

- **Start now** — run pre-flight smoke check (Stage 6.5), then print the ready-to-paste `/goal` line; I paste it and the chain runs unsupervised
- **Adjust an assumption** — pick one to change (will re-show plan)
- **Tweak a phase** — change criteria, scope, or commands for a specific phase
- **Restructure phases** — merge, split, add, or remove a phase

Keep options at 4 max. If the user picks any revision option, follow up with a second `AskUserQuestion` to pin down exactly what (e.g., "Which assumption?" with the assumptions listed). Apply the change, update `run.json`, ROADMAP/THINKING/STATE, and the affected phase specs, re-run `validate-phase.sh` on each touched spec, then run `python "$SUPERGOAL_DIR/scripts/sg.py" validate-run "$SUPERGOAL_ROOT"`. Re-show the Stage 6 summary and ask again. Loop until "Start now" or user aborts.

**Wait for the answer.** Do not dispatch `/goal` until the user picks "Start now". Never assume confirmation; never start the chain on silence.

---

## Stage 6.5 — Pre-flight smoke check

After Stage 6 returns "Start now" and **before** printing the `/goal` block, run a single pre-flight pass against the deduplicated mandatory commands. This catches the case where the baseline is already broken (e.g., `pnpm build` red before phase 1 ever ran) — without this, the 3-strike loop would thrash trying to "fix" phase 1 work that was never the cause.

**Procedure:**

1. Read `run.json` and union every phase's `commands` ids into a deduplicated set, using the run-level command registry for the actual shell command.
2. Run each once. Capture exit code and last ~5 lines.
3. **If all green:**
   - Append a `Notable events` line to `$SUPERGOAL_ROOT/STATE.md`: `<DATE> — Pre-flight green: <N> commands clean.`
   - Record `preflight.pass` in `events.jsonl` with `python "$SUPERGOAL_DIR/scripts/sg.py" record-event "$SUPERGOAL_ROOT" --type preflight.pass --status pass --message "<N> commands clean"`.
   - Print `PREFLIGHT_GREEN` with the per-command summary.
   - Proceed to Stage 7.
4. **If any red:**
   - Append `<DATE> — Pre-flight red: <cmd> exited <code>.` to `STATE.md`.
   - Record `preflight.fail` in `events.jsonl`.
   - Print `PREFLIGHT_RED` with the failing command, exit code, last ~5 lines.
   - Re-show the Stage 6 summary with the failures surfaced and a revised menu (still 4 options to stay under the `AskUserQuestion` ceiling): **"Skip pre-flight, dispatch anyway"** (replaces "Start now" — the user might know the baseline is intentionally broken, e.g., phase 1's whole job is to fix it) / **"Adjust an assumption"** / **"Tweak a phase"** / **"Restructure phases"**. If "Skip pre-flight, dispatch anyway" → log `<DATE> — Pre-flight bypassed by user.` and proceed to Stage 7. Any other choice loops back through the normal Stage 6 revision flow; after the user finishes revising, Stage 6.5 re-runs.

**Honesty test:** real command run, real exit code. The "skip anyway" option keeps the user in control — no forced re-plan if the baseline being red is the point.

---

## Stage 7 — Hand off the `/goal` dispatch (one paste)

Slash commands on both Claude Code and Codex fire **only from user input** — agent message text is never parsed as a command. So Stage 7 is not an automatic dispatch; it's an honest one-paste handoff. After explicit "Start now" in Stage 6:

1. Update `run.json`: `run.status = READY_TO_DISPATCH`, `run.current_phase = 1`, and **capture the baseline ref** — set `run.baseline_ref` to the output of `git rev-parse HEAD 2>/dev/null || echo "no-git"`. Mirror the same values into `STATE.md`. The audit reads the baseline to diff deliverables against the complete working tree.
2. Copy the operating manual, run kernel, and comparison helper into this run's namespace, baking the run root into the manual:
   ```bash
   sed "s#{{RUN_ROOT}}#$SUPERGOAL_ROOT#g" "$SUPERGOAL_DIR/templates/PROTOCOL.md" > "$SUPERGOAL_ROOT/PROTOCOL.md"
   cp "$SUPERGOAL_DIR/scripts/sg.py" "$SUPERGOAL_ROOT/sg.py"
   cp "$SUPERGOAL_DIR/scripts/repo-state.sh" "$SUPERGOAL_ROOT/repo-state.sh"
   chmod +x "$SUPERGOAL_ROOT/sg.py" "$SUPERGOAL_ROOT/repo-state.sh" 2>/dev/null || true
   ```
   `PROTOCOL.md` is the manual the executing agent reads at the start of the `/goal` session; the `sed` substitutes the concrete run root for every `{{RUN_ROOT}}` placeholder. `sg.py` is copied so the executor has the exact kernel version the planner validated. `repo-state.sh` is the complete-working-tree comparison helper the gate/audit invoke (strategy in `references/repo-state-comparison.md`).
3. Verify each `$SUPERGOAL_ROOT/phases/phase-N.md` exists; run `bash $SUPERGOAL_DIR/scripts/validate-phase.sh "$SUPERGOAL_ROOT/phases/phase-<N>.md"` on each. Then run `python "$SUPERGOAL_ROOT/sg.py" validate-run "$SUPERGOAL_ROOT"` and require `SUPERGOAL_RUN_KERNEL_READY`.
4. Print a fenced code block with the **ready-to-paste `/goal` command**. **Substitute the literal value of `$SUPERGOAL_ROOT` for every `<run-root>` below** (e.g. `.supergoal/add-dark-mode-Ab3Kx9`) — the pasted line must contain the real directory, not the variable or the `<run-root>` placeholder. The condition is short, instructional but measurable, and well under the 4000-char `/goal` argument limit:

````
```
/goal "Execute the Supergoal v1 run at <run-root>. First read <run-root>/PROTOCOL.md and validate <run-root>/run.json with python <run-root>/sg.py validate-run <run-root>. For each pending phase, read <run-root>/phases/phase-N.md, do the scoped work, save command logs and required proof under <run-root>/evidence/phase-N/, print SUPERGOAL_PHASE_VERIFY, then run python <run-root>/sg.py gate-phase <run-root> N before SUPERGOAL_PHASE_DONE. Follow <run-root>/PROTOCOL.md for 3-strike recovery. After all phases pass gates, run python <run-root>/sg.py audit <run-root>, then python <run-root>/sg.py report <run-root>. Done only when AUDIT_COMPLETE, RUN_REPORT_WRITTEN, and SUPERGOAL_RUN_COMPLETE appear, with no FAILURE_HANDOFF or AUDIT_HANDOFF this run."
```
````

5. Follow the fenced block with **exactly this one-line instruction**:

> **Paste the `/goal` line above into your input to dispatch the chain.** From there it runs autonomously — event telemetry, evidence files, phase gates, auto-retry, fix-spec recovery, memory writeback, audit, and report — until `SUPERGOAL_RUN_COMPLETE` appears.

6. **Stop.** Do not generate any further output. The Supergoal invocation ends here. The user's paste begins the autonomous run under a fresh `/goal` session, which reads `PROTOCOL.md`, `ROADMAP.md`, `STATE.md`, and the phase specs from disk and runs the loop documented in the next sections.

Once `/goal` is active (you'll see the `◎ /goal active` indicator on Claude Code), the per-turn evaluator keeps the agent working until the end-state condition holds. On Codex, the auto-continuation loop does the same. The agent inside the `/goal` session has zero special context from the Supergoal invocation; everything it needs is in the files on disk — by design.

---

## Phase execution loop (inside the single `/goal` session)

The executor's authoritative loop lives in `<run-root>/PROTOCOL.md`. Short version:

1. Validate `run.json` with `python <run-root>/sg.py validate-run <run-root>`.
2. Read the next pending phase from `run.json`, then the matching `phases/phase-N.md` spec.
3. Record phase start in `events.jsonl`.
4. Do the scoped work. Keep edits inside `allowed_paths` unless the manifest is deliberately revised before continuing.
5. Save command logs under `evidence/phase-N/commands/<command-id>.log`; each log must include an explicit exit marker.
6. Save required evidence under `evidence/phase-N/`.
7. Print `SUPERGOAL_PHASE_VERIFY` with criterion status, verification class, and evidence path.
8. Run `python <run-root>/sg.py gate-phase <run-root> N`. This verifies required evidence, command logs, scope drift, and trust debt.
9. Only after the gate passes, print `MEMORY_SAVED` and `SUPERGOAL_PHASE_DONE`.
10. After all phases pass, run `python <run-root>/sg.py audit <run-root>` and `python <run-root>/sg.py report <run-root>`. Only then print `SUPERGOAL_RUN_COMPLETE`.

### Final audit (Stage 10 of the loop — before completion)

Per-phase VERIFY blocks are self-reports. A phase can pass its own check while a later phase silently breaks it. The v1 audit uses `run.json`, command logs, required evidence, deliverables checked through `repo-state.sh`, and event history.

The audit runs after the final phase. If it finds gaps, it writes a focused fix spec and re-runs itself. Cap at 3 audit rounds; on the 3rd round's failure, `AUDIT_HANDOFF`.

**Audit steps:**

1. Print `AUDIT_START` with round number, total phase count, criteria count, command ids, and trust-prior count.
2. Run `python <run-root>/sg.py audit <run-root>`.
3. If it prints `AUDIT_GAPS`, write `<run-root>/phases/audit-fix-<round>.md`, execute only the focused fix, record the gap in `events.jsonl`, and rerun the audit.
4. On the 3rd failed audit round, print `AUDIT_HANDOFF`, update `run.json` and `STATE.md` to `BLOCKED`, run `python <run-root>/sg.py report <run-root>`, and stop.
5. If it prints `AUDIT_COMPLETE`, run `python <run-root>/sg.py report <run-root>` and require `RUN_REPORT_WRITTEN`.
6. Print `SUPERGOAL_RUN_COMPLETE`. If trust-prior criteria exceed 30% of total criteria, prepend an honesty banner requiring human review before merge.

The audit is the difference between "the agent said every phase passed" and "the final state matches the run contract I approved." That is the bar.

### Failure recovery (3-strike, built into the protocol)

**First failure of any criterion:**
1. Print `FAILURE_PROBE` (what failed, what tried, root-cause hypothesis).
2. Append probe to `STATE.md` failure log.
3. **Auto-retry the same phase once** with the probe injected as feedback. Do not advance.

**Second failure (auto-retry also failed):**
1. Print `FAILURE_ESCALATE`.
2. Write a focused **fix spec** at `<run-root>/phases/phase-N.fix.md` (targets only the failing criterion, no scope creep).
3. Execute the fix spec inline (same agent, same `/goal` — no new dispatch). On success, re-run the original phase's VERIFY block; on pass, advance to N+1.

**Third failure (fix spec also failed):**
1. Print `FAILURE_HANDOFF` with: failing criterion, full probe history, three things tried, suggested next move.
2. Update `STATE.md`: `Status: BLOCKED`. The user takes the wheel.
3. The `/goal` condition will not be satisfied; the host's evaluator will keep evaluating but the agent should stop attempting and surface the handoff clearly.

This recovers from flaky envs, simple typos, and missed deps automatically. Only real blockers escalate.

### Mid-run interruption

If the user sends any message during the `/goal` run, the agent pauses at the next phase boundary, addresses the message, and asks before resuming. Phase boundaries are after `SUPERGOAL_PHASE_DONE` and before reading the next phase spec.

---

## Memory writeback rules (referenced by PROTOCOL.md)

Memory is load-bearing. Future runs start smarter because past runs wrote down what they learned. The phase execution loop's step 6 references these rules.

**At each phase boundary**, ask: "Did this phase surface anything a future Supergoal run on a similar task would benefit from knowing?"

Worth saving:
- A library API quirk that wasn't in the docs
- A user preference confirmed during this run ("user accepted dark-only UI without pushback")
- A project-level fact ("auth lives in `lib/auth/` not `app/api/auth/`")
- A failure pattern + fix ("X always fails on first build; second build works")

Write the memory file under the detected MEM_DIR using the standard `name` / `description` / `metadata.type` frontmatter. Link it from `MEMORY.md`. Print `MEMORY_SAVED: <name>` to the transcript. If nothing non-obvious this phase: print `MEMORY_SAVED: none`.

**At the final phase**, always write a `project_<slug>.md` memory pointing at the new/changed project (location, stack, status, ROADMAP link). Guarantees future Supergoal runs on the same project start from the latest state.

**Never save:** secrets, transient task details, ephemeral state. Bar is "useful to a future run." When in doubt, skip.

---

## Operating principles (read every run)

- **One `/goal`, short condition.** `/goal` takes an end-state, not a task body. Long content lives in files the agent reads from disk. This is the natural shape on both Claude Code and Codex.
- **Frictionless is the goal.** Memory + prompt + recon should answer most questions. Zero clarifying questions on well-described tasks is a win.
- **Adapt to available tools.** Detect what's there (Context7, WebSearch, MCPs, skills). Use what's available; degrade gracefully without it. Never hard-require a tool that might not be present.
- **Memory is load-bearing.** Preload at Stage 0, surface as "Applied from memory: …" in Stage 1, write back at every phase boundary.
- **"Perfect" is not a stopping condition — criteria are.** Translate every "perfect" into observable, falsifiable criteria.
- **Two human gates, no more.** Clarifying gaps (Stage 1 — walk the full category checklist for greenfield in batches of up to 4 until all material info is gathered; often zero for brownfield) and plan review (Stage 6). Between and after, autonomous.
- **The loop self-heals.** Auto-retry once, then write a fix spec and execute inline, then escalate. Don't stop on first failure.
- **The evaluator only sees the transcript.** Phase specs require the agent to surface their contract — START, commands, evidence, VERIFY, DONE — into the conversation, not just point at files.
- **Each phase is independently shippable** in spirit. If phase 3 can't build/test on its own, the slicing is wrong.
- **The Polish & Harden phase is mandatory.** It's how "every aspect is perfect" gets enforced.

---

## When to deviate from the workflow

- **Very small task** (< 1 hour of work, single file): tell the user this doesn't need Supergoal, suggest just doing it. Don't force the machinery.
- **The user pushes back on a phase during intake**: collapse, re-plan, continue.
- **Mid-run interruption**: if the user stops the run and asks for a change, update the affected `<run-root>/phases/phase-N.md` spec, run `validate-phase.sh` on it, then ask the user to resume (they can re-dispatch the same `/goal` or just say "continue"). No need to restart phase 1.

---

## Reference files

- `references/planning-depth.md` — what makes a plan deep enough to deserve "Super"
- `references/phase-design.md` — how to slice phases that auto-chain cleanly
- `references/goal-format.md` — what `/goal` is on Claude Code + Codex, Supergoal's single-`/goal` shape, required transcript blocks

## Scripts

- `scripts/detect-stack.sh` — identifies language, package manager, framework, build/test/lint commands (brownfield)
- `scripts/detect-env.sh` — greenfield environment recon
- `scripts/summarize-repo.sh` — compressed repo map (brownfield)
- `scripts/validate-phase.sh` — checks a phase spec has the required SUPERGOAL_PHASE_START marker and a non-empty acceptance criteria section
- `scripts/sg.py` — v1 run kernel: init-run, record-event, gate-phase, audit, resume, report, validate-run

## Templates

- `templates/ROADMAP.md` — rendered plan with command registry, trust debt, allowed paths, and deliverables
- `templates/STATE.md` — human-readable progress mirror; `run.json` is canonical
- `templates/phase-goal.txt` — phase spec skeleton with allowed paths, verification classes, evidence files, and gate command
- `templates/PROTOCOL.md` — v1 execution loop, evidence vault, phase gate, failure recovery, audit, and report generation (copied to `<run-root>/PROTOCOL.md` at dispatch, with `{{RUN_ROOT}}` substituted for the run root)

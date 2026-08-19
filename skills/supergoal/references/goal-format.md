# `/goal` format reference

## What `/goal` actually is

`/goal <end-state condition>` is a host slash command available in both Claude Code and Codex (Codex CLI). It is **not** a task description. It is a **measurable end-state condition** that a fast evaluator checks against the transcript after each agent turn. The agent keeps working — running tools, editing files — until the condition holds, at which point control returns to the user.

Key implications:

1. **Condition is short.** A long task body in the `/goal` argument is the wrong shape. Long content belongs in files the agent reads from disk.
2. **The evaluator only sees the transcript.** Conditions must be phrased so the agent's own output can prove them ("X printed", "Y exit code surfaced", "Z file count reported"). The evaluator does not independently run tools or read files.
3. **Host behaviour:**
   - **Claude Code**: a small fast model (Haiku) checks the condition each turn; "no" → continue with the reason as guidance; "yes" → clear goal, return control.
   - **Codex**: auto-continuation loop drives the goal to terminal status (complete / budget_limited / paused / cleared). Five subcommands: `/goal <objective>`, `/goal` (status), `/goal pause`, `/goal resume`, `/goal clear`.

## Supergoal's single-`/goal` shape

Supergoal uses **one** `/goal` per run, dispatched by the **user** at the end of Stage 7. Slash commands fire only from user input on both Claude Code and Codex — the planner cannot fire `/goal` from its own message text. Stage 7's job is to write `run.json`, markdown mirrors, phase specs, the run kernel, and the protocol to disk, then print a copy-paste-ready `/goal` block. The user pastes once; from there, the run is autonomous.

The condition is (`<run-root>` is this run's namespaced artifact dir, e.g. `.supergoal/add-dark-mode-Ab3Kx9`; the planner substitutes the concrete path before printing the block so the pasted line carries the real directory — never the placeholder):

```
Execute the Supergoal v1 run at <run-root>. First read
<run-root>/PROTOCOL.md and validate <run-root>/run.json with
python <run-root>/sg.py validate-run <run-root>. For each pending phase,
read <run-root>/phases/phase-N.md, do the scoped work, save command logs
and required proof under <run-root>/evidence/phase-N/, print
SUPERGOAL_PHASE_VERIFY, then run python <run-root>/sg.py gate-phase
<run-root> N before SUPERGOAL_PHASE_DONE. Follow <run-root>/PROTOCOL.md
for 3-strike recovery. After all phases pass gates, run python
<run-root>/sg.py audit <run-root>, then python <run-root>/sg.py report
<run-root>.

Done only when AUDIT_COMPLETE, RUN_REPORT_WRITTEN, and
SUPERGOAL_RUN_COMPLETE appear, with no FAILURE_HANDOFF or AUDIT_HANDOFF
this run.
```

This works on both hosts. There is no per-phase `/goal` dispatch and no inter-session chain — once active, a single `/goal` session reads PROTOCOL.md, uses `run.json` as the source of truth, loops through every phase spec, runs phase gates, runs the final audit, writes the report, and only completes when the audit is clean.

## Required transcript blocks (Supergoal-specific)

The phase specs and PROTOCOL.md require the agent to print these named blocks during execution. In v1 they are transcript mirrors of structured state, not the source of truth.

### `SUPERGOAL_RUN_KERNEL_READY`

Printed after `python <run-root>/sg.py validate-run <run-root>` passes.

### `PHASE_GATE_VERIFY`

Printed by `python <run-root>/sg.py gate-phase <run-root> N`. A pass is required before `SUPERGOAL_PHASE_DONE`.

### `SCOPE_DRIFT`

Printed by the phase gate when changed files are outside the phase's `allowed_paths`.

### `TRUST_DEBT`

Printed by validation and phase gates as `<trust-prior>/<total> trust-prior (<pct>%)`.

### `RUN_REPORT_WRITTEN`

Printed by `python <run-root>/sg.py report <run-root>` after `report.html` is written.

### `SUPERGOAL_PHASE_START` (once per phase, at execution start)

```
SUPERGOAL_PHASE_START
Phase: <N> of <total> — <name>
Phase id: <N>
Task: <one-line from ROADMAP.md>
Type: <greenfield|brownfield|bugfix|refactor|ui>
Allowed paths: <comma-separated path scopes>
Mandatory command ids: <comma-separated command ids from run.json>
Acceptance criteria: <count>
Trust-prior criteria: <count>
Evidence required: <comma-separated required evidence files>
Depends on phases: <list, or "none">
Run root: <run-root>
```

### `SUPERGOAL_PHASE_VERIFY` (once per phase, before DONE)

```
SUPERGOAL_PHASE_VERIFY
Acceptance:
- <criterion 1>: <pass|fail> / <mechanical|human|trust-prior> — <evidence path>
- <criterion 2>: <pass|fail> / <mechanical|human|trust-prior> — <evidence path>
...
Engineering:
- <command id>: <pass|fail> — <evidence/phase-N/commands/<id>.log>
Evidence files:
- <required evidence path>: <present|missing>
Gate:
- command: python <run-root>/sg.py gate-phase <run-root> N
- status: <pass|fail>
```

### `MEMORY_SAVED` (once per phase, between VERIFY and DONE)

```
MEMORY_SAVED: <memory-name>     (or "none — nothing non-obvious this phase")
```

### `SUPERGOAL_PHASE_DONE` (once per phase, final block of the phase)

```
SUPERGOAL_PHASE_DONE
Phase <N> complete. STATE.md updated.
```

### `AUDIT_START` (once per audit round, after the last phase)

```
AUDIT_START
Round: <1|2|3>
Phases to verify: <N>
Criteria to re-check: <count>
Commands to re-run: <comma-separated, deduplicated set>
```

### `AUDIT_VERIFY` (once per audit round, after re-checks complete)

```
AUDIT_VERIFY
Per-phase completeness:
- Phase 1: <DONE present | DONE missing>
- Phase 2: ...
Re-run mandatory commands:
- <cmd>: exit <code> — <last line>
- ...
Acceptance criteria spot-check:
- Phase 1 / "<criterion>": <pass | fail | trust-prior-verify> — <evidence>
- ...
Deliverables (complete-working-tree check vs Baseline ref via repo-state.sh):
- Phase 1 / "<deliverable bullet>": <present | missing> — <repo-state.sh deliverable evidence>
- Phase 2 / "<deliverable bullet>": <present | missing> — <evidence>
- ...
Summary: <pass count> pass, <fail count> fail, <trust count> trust-prior, <missing count> deliverable-gaps
```

### `AUDIT_GAPS` (only if gaps found this round)

```
AUDIT_GAPS
Round: <N>
Gaps:
- <gap 1>: <details>
- <gap 2>: <details>
Writing fix spec at <run-root>/phases/audit-fix-<N>.md, executing inline.
```

### `AUDIT_COMPLETE` (zero gaps — emit before SUPERGOAL_RUN_COMPLETE)

```
AUDIT_COMPLETE
Rounds: <N>
Phases re-verified: <count>
Commands re-run clean: <count>
Acceptance criteria: <pass count> pass / <0> fail / <trust count> trust-prior
Deliverables: <present count> present / <0> missing
Audit coverage: <re_verified> re-verified / <trust> trust-prior (<pct>%)
```

### `AUDIT_HANDOFF` (3 audit rounds all failed — stop)

```
AUDIT_HANDOFF
Round: 3
Persistent gaps:
- <gap>
- ...
Three audit rounds attempted; fix specs at <run-root>/phases/audit-fix-{1,2,3}.md
Suggested next move: <one line>
STATE.md updated to BLOCKED.
```

### `SUPERGOAL_RUN_COMPLETE` (once, after AUDIT_COMPLETE)

```
SUPERGOAL_RUN_COMPLETE
[⚠ Audit coverage: <re_verified> re-verified, <trust_prior> trust-prior (<pct>%). Eyeball UI/UX before merging.]   ← only when trust-prior fraction > 30%
Audit coverage: <re_verified> re-verified, <trust_prior> trust-prior (<pct>%).
All <N> phases complete. Audit passed in <rounds> round(s).
Summary: <5 lines max — what shipped, what changed, what to verify manually>
```

The first banner is **only** printed when trust-prior is more than 30% of total checks. Below 30%, only the plain `Audit coverage:` line appears — same honesty, no false alarm.

## Failure blocks (used by recovery protocol)

### `FAILURE_PROBE` (first failure)

```
FAILURE_PROBE
Phase: <N> — <name>
Failed criterion: <text>
Tried: <what was attempted>
Hypothesis: <root cause guess>
Next: auto-retry with probe injected
```

### `FAILURE_ESCALATE` (second failure — fix spec)

```
FAILURE_ESCALATE
Phase: <N> — <name>
Failed criterion: <text>
Retry probe history:
  attempt 1: <summary>
  attempt 2: <summary>
Writing fix spec at <run-root>/phases/phase-<N>.fix.md
```

### `FAILURE_HANDOFF` (third failure — stop)

```
FAILURE_HANDOFF
Phase: <N> — <name>
Failed criterion: <text>
Three attempts tried:
  1. <summary>
  2. <summary>
  3. <fix spec summary>
Suggested next move: <one line>
STATE.md updated to BLOCKED. User intervention required.
```

## Anti-patterns

- **Don't stuff long task content into the `/goal` argument.** Use a short condition; put work in files.
- **Don't make conditions the evaluator can't verify from the transcript.** "Tests pass" is wrong (evaluator can't run tests); "`SUPERGOAL_PHASE_DONE` printed for all phases" is right.
- **Don't chain `/goal` commands across sessions.** One run = one `/goal`. The agent loops internally inside that session.
- **Don't skip evidence to save space.** Files have no char budget — be exhaustive.

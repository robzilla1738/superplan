# Supergoal v1 execution protocol

This file is read by the executing agent at the start of the single `/goal` session. It is the operating manual for the run, but the source of truth is `{{RUN_ROOT}}/run.json`.

All paths below are rooted at this run's artifact directory (`{{RUN_ROOT}}`). The concrete namespaced path is baked in when this file is copied at Stage 7, so two runs in the same working tree read and write separate artifacts.

## Kernel files

- `{{RUN_ROOT}}/run.json` - canonical run manifest: phases, commands, allowed paths, verification classes, deliverables, status.
- `{{RUN_ROOT}}/events.jsonl` - append-only black box recorder.
- `{{RUN_ROOT}}/evidence/phase-N/` - command logs, diffs, screenshots, and other proof files.
- `{{RUN_ROOT}}/sg.py` - standard-library run kernel.
- `{{RUN_ROOT}}/repo-state.sh` - complete-working-tree comparison helper.
- `{{RUN_ROOT}}/report.html` - inspectable run report generated near the end of the run.

## Required transcript mirrors

The transcript is no longer the source of truth, but these blocks still make the run visible to the host and the user:

- `SUPERGOAL_RUN_KERNEL_READY`
- `SUPERGOAL_PHASE_START`
- `SUPERGOAL_PHASE_VERIFY`
- `PHASE_GATE_VERIFY`
- `SCOPE_DRIFT`
- `TRUST_DEBT`
- `MEMORY_SAVED`
- `SUPERGOAL_PHASE_DONE`
- `AUDIT_START` / `AUDIT_VERIFY` / `AUDIT_GAPS` / `AUDIT_COMPLETE` / `AUDIT_HANDOFF`
- `RUN_REPORT_WRITTEN`
- `SUPERGOAL_RUN_COMPLETE`
- `FAILURE_PROBE` / `FAILURE_ESCALATE` / `FAILURE_HANDOFF`

## Startup

1. Run `python "{{RUN_ROOT}}/sg.py" validate-run "{{RUN_ROOT}}"`.
2. Print `SUPERGOAL_RUN_KERNEL_READY` only if validation passes.
3. If validation fails, stop and surface `PLAN_LINT_RED`. Do not execute work against an invalid v1 manifest.
4. If `run.json` is missing but `STATE.md` exists, this is a legacy markdown-only run. Print `LEGACY_RUN_FALLBACK`, follow the old `STATE.md` / phase markdown flow, and do not pretend v1 mechanical gates exist.

## Phase loop

Repeat until `SUPERGOAL_RUN_COMPLETE` is printed:

1. Read `{{RUN_ROOT}}/run.json`. Find the first phase whose status is `in_progress` or `pending`; blocked phases require recovery before new work.
2. Read `{{RUN_ROOT}}/phases/phase-N.md`. This is the human work spec; `run.json` is the contract.
3. Record the phase start:

   ```bash
   python "{{RUN_ROOT}}/sg.py" record-event "{{RUN_ROOT}}" --type phase.start --phase N --status in_progress --message "phase N started"
   ```

4. Print `SUPERGOAL_PHASE_START` with the phase metadata: id, name, allowed paths, command ids, acceptance count, trust-prior count, evidence paths, dependencies.
5. Do the work described in the spec. Keep edits inside the phase's `allowed_paths` unless the phase spec explicitly expands scope.
6. Save command evidence under `{{RUN_ROOT}}/evidence/phase-N/commands/<command-id>.log`. Each log must include the command, the last useful output, and an explicit `exit 0` or non-zero exit marker.
7. Save additional evidence under `{{RUN_ROOT}}/evidence/phase-N/`:
   - `diffs/summary.txt` for notable diff excerpts or `git diff --stat`.
   - `screenshots/` for UI proof.
   - Any named files listed in `required_evidence`.
8. Print `SUPERGOAL_PHASE_VERIFY`: each criterion `pass|fail`, its verification class (`mechanical`, `human`, or `trust-prior`), and evidence file path.
9. Run the mechanical phase gate before declaring completion:

   ```bash
   python "{{RUN_ROOT}}/sg.py" gate-phase "{{RUN_ROOT}}" N
   ```

   The gate verifies required evidence, mandatory command logs, scope drift against `allowed_paths`, and trust debt. If it prints `SCOPE_DRIFT` or exits non-zero, treat that as a failed criterion and enter the 3-strike recovery protocol.

10. Memory writeback check. Anything non-obvious learned this phase? If yes, write a candidate memory file under the detected MEM_DIR with frontmatter (`name`, `description`, `metadata.type`). Link it from `MEMORY.md`. Print `MEMORY_SAVED: <name>` or `MEMORY_SAVED: none`. Final audit may promote or quarantine memory candidates; do not save secrets or transient state.
11. Only after `gate-phase` succeeds, print `SUPERGOAL_PHASE_DONE`. Update `STATE.md` to mirror the manifest, not replace it.
12. User-interrupt check. If a user message arrived since the last turn, pause at this boundary, address it, and ask before resuming.
13. If phases remain, continue with the next pending phase.
14. If all phases are complete, run the final audit. Do not print `SUPERGOAL_RUN_COMPLETE` before `AUDIT_COMPLETE`.

## Final audit

Per-phase VERIFY blocks are self-reports. The audit closes that loophole by using `run.json`, `ROADMAP.md`, repo-state evidence, command logs, and phase evidence.

### Audit steps

1. Print `AUDIT_START` with round number, total phase count, total criteria count, and deduplicated mandatory command ids.
2. Run:

   ```bash
   python "{{RUN_ROOT}}/sg.py" audit "{{RUN_ROOT}}"
   ```

3. If the audit exits zero, print the emitted `AUDIT_COMPLETE` block, then generate the report:

   ```bash
   python "{{RUN_ROOT}}/sg.py" report "{{RUN_ROOT}}"
   ```

   Print `RUN_REPORT_WRITTEN` with the report path.

4. Print `SUPERGOAL_RUN_COMPLETE` only after `AUDIT_COMPLETE` and `RUN_REPORT_WRITTEN`.
5. If trust-prior criteria exceed 30% of total criteria, include a one-line honesty banner before the final summary:

   ```text
   Audit coverage warning: <trust_prior>/<total> criteria were trust-prior. Human review required before merge.
   ```

### If gaps are found

1. Print `AUDIT_GAPS` with the exact gaps from `sg.py audit`.
2. Write `{{RUN_ROOT}}/phases/audit-fix-<round>.md`, a focused fix spec targeting only the failing criteria or missing deliverables.
3. Record the failure:

   ```bash
   python "{{RUN_ROOT}}/sg.py" record-event "{{RUN_ROOT}}" --type audit.gap --status fail --message "<short gap summary>"
   ```

4. Execute the fix spec inline, then rerun the audit.
5. After 3 failed audit rounds, print `AUDIT_HANDOFF`, update `run.json` and `STATE.md` to `BLOCKED`, run `python "{{RUN_ROOT}}/sg.py" report "{{RUN_ROOT}}"`, and stop. Do not print `SUPERGOAL_RUN_COMPLETE`.

## Failure recovery

### First failure of any criterion or gate

1. Print `FAILURE_PROBE` with phase, failed criterion/gate, attempted evidence, and root-cause hypothesis.
2. Record the event:

   ```bash
   python "{{RUN_ROOT}}/sg.py" record-event "{{RUN_ROOT}}" --type failure.probe --phase N --status fail --message "<short summary>"
   ```

3. Append the probe to `{{RUN_ROOT}}/STATE.md` failure log.
4. Auto-retry the same phase once. Do not advance.

### Second failure

1. Print `FAILURE_ESCALATE`.
2. Write `{{RUN_ROOT}}/phases/phase-N.fix.md`, targeting only the failing criterion or gate.
3. Execute the fix spec inline.
4. Re-run `python "{{RUN_ROOT}}/sg.py" gate-phase "{{RUN_ROOT}}" N`.
5. On pass, continue. On fail, proceed to third-failure handling.

### Third failure

1. Print `FAILURE_HANDOFF` with full probe history and suggested next move.
2. Record the blocked event.
3. Update `run.json` and `STATE.md` to `BLOCKED`.
4. Run `python "{{RUN_ROOT}}/sg.py" report "{{RUN_ROOT}}"`.
5. Stop. The `/goal` condition is not satisfied.

## Resume

When resuming a run, start with:

```bash
python "{{RUN_ROOT}}/sg.py" resume "{{RUN_ROOT}}"
```

Follow the reported next action exactly. Do not re-plan a v1 run unless the user explicitly asks for a new plan.

## Memory writeback rules

See `memory_writeback_rules` in `SKILL.md`. Short version:

- Save only durable, non-obvious learnings a future Supergoal run would benefit from.
- Prefer candidate memories during phase work; promote durable memories after final audit.
- Never save secrets, transient task details, or ephemeral state.

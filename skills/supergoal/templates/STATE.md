# State: {{TASK_TITLE}}

**Status:** PLANNING -> IN_PROGRESS -> AUDIT_PENDING -> COMPLETE
**Current phase:** {{CURRENT_PHASE}}
**Started:** {{DATE}}
**Last update:** {{DATE}}
**Run root:** {{RUN_ROOT}}
**Baseline ref:** {{BASELINE_SHA}}
**Canonical manifest:** {{RUN_ROOT}}/run.json
**Event log:** {{RUN_ROOT}}/events.jsonl
**Report:** {{RUN_ROOT}}/report.html

This file is a human-readable mirror. For phase status, command ids, allowed paths, criteria verification classes, deliverables, and required evidence, trust `run.json`.

## Phase progress

| # | Phase | Status | Started | Completed | Gate | Notes |
|---|-------|--------|---------|-----------|------|-------|
| 1 | {{P1_NAME}} | pending | - | - | - | - |
| 2 | {{P2_NAME}} | pending | - | - | - | - |
| ... | ... | pending | - | - | - | - |
| N | Polish & Harden | pending | - | - | - | - |

## Engineering check status

Updated by each phase as it runs. Command logs live under `evidence/phase-N/commands/`.

- Build: -
- Typecheck: -
- Lint: -
- Tests: -

## Trust debt

Updated from `run.json` and phase gates.

- Mechanical criteria: {{MECHANICAL_COUNT}}
- Human criteria: {{HUMAN_COUNT}}
- Trust-prior criteria: {{TRUST_PRIOR_COUNT}}
- Trust-prior ratio: {{TRUST_PRIOR_RATIO}}

## Notable events

Append-only human summary. The durable event stream is `events.jsonl`.

- {{DATE}} - Plan locked, {{N}} phases.
- ...

## Failure log

If a phase hits FAILURE_PROBE or a gate fails, record it here:

- Phase {{N}} ({{NAME}}): {{WHAT_FAILED}} - {{WHAT_WAS_TRIED}} - {{NEXT_MOVE}}

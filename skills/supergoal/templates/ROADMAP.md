# Roadmap: {{TASK_TITLE}}

**Task:** {{ONE_LINE_TASK}}
**Type:** {{TAGS}}
**Created:** {{DATE}}
**Total phases:** {{N}}
**Run root:** {{RUN_ROOT}}
**Source of truth:** `{{RUN_ROOT}}/run.json`

## Context summary

- **Stack:** {{STACK}}
- **Package manager:** {{PM}}
- **Command registry:** {{COMMANDS}}
- **Risky areas:** {{RISKS_ONE_LINE}}

## Run kernel contract

The planner writes `run.json` first, then renders this roadmap, `STATE.md`, and phase specs from it. The executor must keep the markdown mirrors aligned, but `run.json` is canonical.

- **Manifest:** `{{RUN_ROOT}}/run.json`
- **Events:** `{{RUN_ROOT}}/events.jsonl`
- **Evidence vault:** `{{RUN_ROOT}}/evidence/`
- **Mechanical gates:** `python "{{RUN_ROOT}}/sg.py" gate-phase "{{RUN_ROOT}}" N`
- **Final audit:** `python "{{RUN_ROOT}}/sg.py" audit "{{RUN_ROOT}}`
- **Report:** `{{RUN_ROOT}}/report.html`

## Assumptions

Non-blocking decisions recorded here so we can proceed without round-trips. If any are wrong, stop the run and tell us:

- {{ASSUMPTION_1}}
- {{ASSUMPTION_2}}
- ...

## Risk top 3

1. **{{RISK_1}}** - likelihood: {{L}}, mitigation: {{M}}
2. **{{RISK_2}}** - likelihood: {{L}}, mitigation: {{M}}
3. **{{RISK_3}}** - likelihood: {{L}}, mitigation: {{M}}

## Command registry

Each command has an id used by phase gates. Command logs must be saved to `evidence/phase-N/commands/<id>.log`.

| ID | Class | Required | Command |
|----|-------|----------|---------|
| {{CMD_ID_1}} | {{CMD_CLASS_1}} | yes | `{{CMD_1}}` |
| {{CMD_ID_2}} | {{CMD_CLASS_2}} | yes | `{{CMD_2}}` |

## Phase map

| # | Phase | Depends on | Allowed paths | Trust debt | Deliverable |
|---|-------|------------|---------------|------------|-------------|
| 1 | {{P1_NAME}} | none | {{P1_ALLOWED}} | {{P1_TRUST}}/{{P1_CRITERIA}} | {{P1_DELIVERABLE}} |
| 2 | {{P2_NAME}} | 1 | {{P2_ALLOWED}} | {{P2_TRUST}}/{{P2_CRITERIA}} | {{P2_DELIVERABLE}} |
| ... | ... | ... | ... | ... | ... |
| N | Polish & Harden | 1..N-1 | * | {{PN_TRUST}}/{{PN_CRITERIA}} | Every aspect is verified |

---

## Phase 1 - {{P1_NAME}}

**Why:** {{P1_WHY}}

**Allowed paths:**
- {{P1_ALLOWED_PATH_1}}
- {{P1_ALLOWED_PATH_2}}

**Deliverables:**
- {{P1_FILE_OR_FEATURE_1}}
- {{P1_FILE_OR_FEATURE_2}}

**Acceptance criteria:**
- [{{P1_CRIT_1_CLASS}}] {{P1_CRIT_1}} (evidence: {{P1_CRIT_1_EVIDENCE}})
- [{{P1_CRIT_2_CLASS}}] {{P1_CRIT_2}} (evidence: {{P1_CRIT_2_EVIDENCE}})
- [{{P1_CRIT_3_CLASS}}] {{P1_CRIT_3}} (evidence: {{P1_CRIT_3_EVIDENCE}})

**Mandatory command ids:**
- `{{CMD_ID_1}}`
- `{{CMD_ID_2}}`

**Required evidence files:**
- {{EVIDENCE_1}}
- {{EVIDENCE_2}}

**Dependencies:** none

---

## Phase 2 - {{P2_NAME}}

(same structure)

---

## Phase N - Polish & Harden

**Why:** Catch what earlier phases missed because they were focused on shipping behavior. This is how "every aspect is perfect" gets enforced.

**Sub-passes (each must produce evidence):**

- [ ] **UX and copy** - every visible string reads well, no debug placeholders
- [ ] **States** - empty, loading, error, unauthorized verified for every new surface
- [ ] **Edges** - empty inputs, long inputs, special chars, slow network
- [ ] **Security** - input validation, auth checks, no secrets in client bundle
- [ ] **A11y** (if UI) - keyboard nav, focus, screen reader, contrast AA or better
- [ ] **Perf** - no obvious N+1, no megabyte bundles, no blocking renders
- [ ] **Diff review** - `git diff` reviewed for stray debug logs and TODOs from this run
- [ ] **Regression sweep** - full test suite plus manual check of one adjacent feature

**Mandatory command ids:**
- All build/test/lint command ids from earlier phases
- Whatever stack-specific perf/security checks apply

**Required evidence files:**
- `diffs/final-stat.txt`
- `commands/<command-id>.log` for each final command
- UI screenshots where applicable

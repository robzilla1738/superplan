#!/usr/bin/env python3
"""Supergoal v1 run kernel.

This script is intentionally standard-library only. It gives Supergoal a small
runtime contract around each run instead of relying on prose-only markdown.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import fnmatch
import glob
import html
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"
ALLOWED_RUN_STATUSES = {
    "PLANNING",
    "READY_TO_DISPATCH",
    "IN_PROGRESS",
    "AUDIT_PENDING",
    "BLOCKED",
    "COMPLETE",
}
ALLOWED_PHASE_STATUSES = {"pending", "in_progress", "complete", "blocked"}
ALLOWED_VERIFICATION_CLASSES = {"mechanical", "human", "trust-prior"}


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def die(message: str, code: int = 1) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        die(f"run.json missing at {path}")
    except json.JSONDecodeError as exc:
        die(f"run.json invalid JSON: {exc}")
    if not isinstance(data, dict):
        die("run.json must be a JSON object")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def run_root_from_arg(value: str) -> Path:
    return Path(value).expanduser().resolve()


def manifest_path(run_root: Path) -> Path:
    return run_root / "run.json"


def events_path(run_root: Path) -> Path:
    return run_root / "events.jsonl"


def phase_evidence_root(run_root: Path, phase_id: int | str) -> Path:
    return run_root / "evidence" / f"phase-{phase_id}"


def command_log_name(command_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(command_id).strip())
    return f"{safe or 'command'}.log"


def append_event(
    run_root: Path,
    event_type: str,
    *,
    phase: int | None = None,
    status: str | None = None,
    message: str | None = None,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run_root.mkdir(parents=True, exist_ok=True)
    event = {
        "ts": utc_now(),
        "type": event_type,
    }
    if phase is not None:
        event["phase"] = phase
    if status is not None:
        event["status"] = status
    if message:
        event["message"] = message
    if data:
        event["data"] = data
    with events_path(run_root).open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, sort_keys=True) + "\n")
    return event


def load_events(run_root: Path) -> list[dict[str, Any]]:
    path = events_path(run_root)
    events: list[dict[str, Any]] = []
    if not path.exists():
        return events
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            events.append({"ts": "", "type": "MALFORMED_EVENT", "message": f"line {i}"})
            continue
        if isinstance(item, dict):
            events.append(item)
    return events


def command_registry(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    commands = manifest.get("commands", [])
    if isinstance(commands, dict):
        return {str(k): {"id": str(k), **(v if isinstance(v, dict) else {"command": str(v)})} for k, v in commands.items()}
    out: dict[str, dict[str, Any]] = {}
    if isinstance(commands, list):
        for item in commands:
            if isinstance(item, dict) and item.get("id"):
                out[str(item["id"])] = item
    return out


def phases(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    value = manifest.get("phases", [])
    return value if isinstance(value, list) else []


def phase_by_id(manifest: dict[str, Any], phase_id: int | str) -> dict[str, Any] | None:
    wanted = str(phase_id)
    for phase in phases(manifest):
        if str(phase.get("id")) == wanted:
            return phase
    return None


def criteria_for_phase(phase: dict[str, Any]) -> list[dict[str, Any]]:
    raw = phase.get("criteria", [])
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for i, item in enumerate(raw, start=1):
        if isinstance(item, dict):
            out.append(item)
        else:
            out.append({"id": f"c{i}", "text": str(item), "verification": "trust-prior"})
    return out


def baseline_ref(manifest: dict[str, Any], run_root: Path) -> str:
    run = manifest.get("run", {}) if isinstance(manifest.get("run"), dict) else {}
    baseline = str(run.get("baseline_ref") or manifest.get("baseline_ref") or "").strip()
    if baseline:
        return baseline
    state = run_root / "STATE.md"
    if state.exists():
        match = re.search(r"Baseline ref:\*\*\s*([^\s<]+)|Baseline ref:\s*([^\s<]+)", state.read_text(encoding="utf-8", errors="replace"))
        if match:
            return (match.group(1) or match.group(2) or "no-git").strip()
    return "no-git"


def bash_executable() -> str | None:
    found = shutil.which("bash")
    if found:
        return found
    candidates = [
        Path("C:/Program Files/Git/bin/bash.exe"),
        Path("C:/Program Files/Git/usr/bin/bash.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def repo_state_script(run_root: Path) -> Path | None:
    candidates = [
        run_root / "repo-state.sh",
        Path(__file__).resolve().with_name("repo-state.sh"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def run_repo_state(run_root: Path, subcommand: str, *args: str) -> tuple[int, str, str]:
    script = repo_state_script(run_root)
    if script is None:
        return 127, "", "repo-state.sh not found"
    bash = bash_executable()
    if bash is None:
        return 127, "", "bash not found"
    proc = subprocess.run(
        [bash, str(script), subcommand, *args],
        cwd=str(Path.cwd()),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def changed_files(run_root: Path, manifest: dict[str, Any]) -> list[str]:
    rc, out, err = run_repo_state(run_root, "changed-files", baseline_ref(manifest, run_root))
    if rc != 0:
        return []
    ignored_prefixes: list[str] = []
    try:
        rel_run_root = run_root.resolve().relative_to(Path.cwd().resolve()).as_posix().rstrip("/")
        ignored_prefixes.append(rel_run_root + "/")
    except ValueError:
        pass
    ignored_prefixes.append(".supergoal/")

    files = []
    for line in out.splitlines():
        path = line.strip().replace("\\", "/").lstrip("./")
        if not path:
            continue
        if any(path.startswith(prefix) for prefix in ignored_prefixes if prefix):
            continue
        files.append(path)
    return files


def is_allowed_path(path: str, allowed: list[str]) -> bool:
    if not allowed or "*" in allowed:
        return True
    normalized = path.replace("\\", "/").lstrip("./")
    for raw in allowed:
        pattern = str(raw).replace("\\", "/").lstrip("./")
        if not pattern:
            continue
        if pattern == "*":
            return True
        if pattern.endswith("/"):
            if normalized.startswith(pattern):
                return True
        elif any(ch in pattern for ch in "*?[]"):
            if fnmatch.fnmatch(normalized, pattern):
                return True
        elif normalized == pattern or normalized.startswith(pattern.rstrip("/") + "/"):
            return True
    return False


def evidence_exists(run_root: Path, phase_id: int | str, evidence: str) -> bool:
    ev = str(evidence).strip()
    if not ev:
        return True
    candidates = [
        run_root / ev,
        phase_evidence_root(run_root, phase_id) / ev,
    ]
    for candidate in candidates:
        if candidate.exists():
            return True
        if any(ch in str(candidate) for ch in "*?[]") and glob.glob(str(candidate)):
            return True
    return False


def command_log_path(run_root: Path, phase_id: int | str, command_id: str) -> Path:
    return phase_evidence_root(run_root, phase_id) / "commands" / command_log_name(command_id)


def command_log_passed(log_path: Path) -> tuple[bool, str]:
    if not log_path.exists():
        return False, "missing command log"
    text = log_path.read_text(encoding="utf-8", errors="replace")
    if re.search(r"\bexit(?:\s+code)?\s*[:=]?\s*0\b", text, re.IGNORECASE):
        return True, "exit 0 found"
    if re.search(r"\brc\s*[:=]\s*0\b", text, re.IGNORECASE):
        return True, "rc=0 found"
    if re.search(r"\bexit(?:\s+code)?\s*[:=]?\s*[1-9]\d*\b", text, re.IGNORECASE):
        return False, "non-zero exit marker found"
    return False, "no exit 0 marker found"


def trust_debt_for_phase(phase: dict[str, Any]) -> tuple[int, int, float]:
    criteria = criteria_for_phase(phase)
    total = len(criteria)
    trust = sum(1 for c in criteria if str(c.get("verification", "")).strip() == "trust-prior")
    pct = (trust / total * 100.0) if total else 0.0
    return trust, total, pct


def validate_manifest(manifest: dict[str, Any], run_root: Path) -> list[str]:
    errors: list[str] = []
    if str(manifest.get("schema_version", "")) != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")

    run = manifest.get("run")
    if not isinstance(run, dict):
        errors.append("run object missing")
        run = {}
    if not run.get("id"):
        errors.append("run.id missing")
    status = str(run.get("status", "PLANNING"))
    if status not in ALLOWED_RUN_STATUSES:
        errors.append(f"run.status invalid: {status}")

    phase_list = phases(manifest)
    if not phase_list:
        errors.append("phases must contain at least one phase")

    seen_ids: set[str] = set()
    registry = command_registry(manifest)
    for idx, phase in enumerate(phase_list, start=1):
        if not isinstance(phase, dict):
            errors.append(f"phase at index {idx} is not an object")
            continue
        pid = str(phase.get("id", "")).strip()
        if not pid:
            errors.append(f"phase at index {idx} missing id")
            continue
        if pid in seen_ids:
            errors.append(f"duplicate phase id: {pid}")
        seen_ids.add(pid)
        status = str(phase.get("status", "pending"))
        if status not in ALLOWED_PHASE_STATUSES:
            errors.append(f"phase {pid} status invalid: {status}")
        if not str(phase.get("name", "")).strip():
            errors.append(f"phase {pid} name missing")
        if not isinstance(phase.get("allowed_paths", []), list):
            errors.append(f"phase {pid} allowed_paths must be a list")
        commands = phase.get("commands", [])
        if not isinstance(commands, list):
            errors.append(f"phase {pid} commands must be a list of command ids")
            commands = []
        for command_id in commands:
            if str(command_id) not in registry:
                errors.append(f"phase {pid} references unknown command id: {command_id}")
        depends_on = phase.get("depends_on", [])
        if not isinstance(depends_on, list):
            errors.append(f"phase {pid} depends_on must be a list")
            depends_on = []
        for dep in depends_on:
            if str(dep) == pid:
                errors.append(f"phase {pid} depends on itself")
        criteria = criteria_for_phase(phase)
        if not criteria:
            errors.append(f"phase {pid} has no criteria")
        for c_idx, criterion in enumerate(criteria, start=1):
            verification = str(criterion.get("verification", "")).strip()
            if verification not in ALLOWED_VERIFICATION_CLASSES:
                errors.append(f"phase {pid} criterion {c_idx} verification invalid: {verification}")

    phase_ids = {str(phase.get("id")) for phase in phase_list if isinstance(phase, dict)}
    for phase in phase_list:
        if not isinstance(phase, dict):
            continue
        pid = str(phase.get("id"))
        for dep in phase.get("depends_on", []) if isinstance(phase.get("depends_on", []), list) else []:
            if str(dep) not in phase_ids:
                errors.append(f"phase {pid} depends on missing phase {dep}")

    if phase_list:
        last = phase_list[-1]
        last_name = str(last.get("name", "")).lower() if isinstance(last, dict) else ""
        if not (("polish" in last_name and "harden" in last_name) or last.get("final") is True):
            errors.append("last phase must be 'Polish & Harden' or set final=true")

    for path in ["ROADMAP.md", "STATE.md", "phases"]:
        if not (run_root / path).exists():
            errors.append(f"expected artifact missing: {path}")

    return errors


def set_phase_status(manifest: dict[str, Any], phase_id: int | str, status: str, run_root: Path) -> None:
    phase = phase_by_id(manifest, phase_id)
    if phase is None:
        return
    phase["status"] = status
    run = manifest.setdefault("run", {})
    if isinstance(run, dict):
        run["last_update"] = utc_now()
        pending = [p for p in phases(manifest) if str(p.get("status", "pending")) in {"pending", "in_progress", "blocked"}]
        if pending:
            run["current_phase"] = pending[0].get("id")
            if run.get("status") not in {"BLOCKED", "COMPLETE"}:
                run["status"] = "IN_PROGRESS"
        else:
            run["status"] = "AUDIT_PENDING"
    write_json(manifest_path(run_root), manifest)


def cmd_init_run(args: argparse.Namespace) -> int:
    run_root = run_root_from_arg(args.run_root)
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "phases").mkdir(exist_ok=True)
    (run_root / "evidence").mkdir(exist_ok=True)
    path = manifest_path(run_root)
    if path.exists() and not args.force:
        print(f"SUPERGOAL_RUN_KERNEL_READY run.json already exists: {path}")
        return 0
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "run": {
            "id": args.id or run_root.name,
            "title": args.title or run_root.name,
            "task": args.task or "",
            "status": "PLANNING",
            "current_phase": 1,
            "run_root": str(run_root),
            "baseline_ref": args.baseline or "no-git",
            "host": args.host or "unknown",
            "legacy": False,
            "created_at": utc_now(),
            "last_update": utc_now(),
        },
        "commands": [],
        "phases": [],
    }
    write_json(path, manifest)
    append_event(run_root, "run.init", status="PLANNING", message="run kernel initialized")
    print(f"SUPERGOAL_RUN_KERNEL_READY {path}")
    return 0


def cmd_record_event(args: argparse.Namespace) -> int:
    data: dict[str, Any] | None = None
    if args.data_json:
        try:
            parsed = json.loads(args.data_json)
        except json.JSONDecodeError as exc:
            die(f"--data-json invalid JSON: {exc}")
        if not isinstance(parsed, dict):
            die("--data-json must decode to an object")
        data = parsed
    event = append_event(
        run_root_from_arg(args.run_root),
        args.type,
        phase=args.phase,
        status=args.status,
        message=args.message,
        data=data,
    )
    print(json.dumps(event, sort_keys=True))
    return 0


def cmd_validate_run(args: argparse.Namespace) -> int:
    run_root = run_root_from_arg(args.run_root)
    if not manifest_path(run_root).exists():
        if (run_root / "STATE.md").exists():
            print("LEGACY_RUN_FALLBACK markdown-only run detected")
            return 0
        print("PLAN_LINT_RED")
        print(f"- run.json missing at {manifest_path(run_root)}")
        return 1
    manifest = load_json(manifest_path(run_root))
    errors = validate_manifest(manifest, run_root)
    if errors:
        print("PLAN_LINT_RED")
        for error in errors:
            print(f"- {error}")
        return 1
    trust, total = trust_debt_for_manifest(manifest)
    pct = (trust / total * 100.0) if total else 0.0
    print("SUPERGOAL_RUN_KERNEL_READY")
    print(f"Run: {manifest.get('run', {}).get('id', run_root.name)}")
    print(f"Phases: {len(phases(manifest))}")
    print(f"TRUST_DEBT run: {trust}/{total} trust-prior ({pct:.0f}%)")
    return 0


def trust_debt_for_manifest(manifest: dict[str, Any]) -> tuple[int, int]:
    trust = 0
    total = 0
    for phase in phases(manifest):
        phase_trust, phase_total, _ = trust_debt_for_phase(phase)
        trust += phase_trust
        total += phase_total
    return trust, total


def cmd_gate_phase(args: argparse.Namespace) -> int:
    run_root = run_root_from_arg(args.run_root)
    manifest = load_json(manifest_path(run_root))
    phase = phase_by_id(manifest, args.phase)
    if phase is None:
        print("PHASE_GATE_VERIFY fail")
        print(f"- phase {args.phase} not found")
        return 1

    append_event(run_root, "phase.gate.start", phase=int(args.phase), message="phase gate verification started")
    errors: list[str] = []
    phase_id = phase.get("id", args.phase)

    for evidence in phase.get("required_evidence", []) if isinstance(phase.get("required_evidence", []), list) else []:
        if not evidence_exists(run_root, phase_id, str(evidence)):
            errors.append(f"missing evidence: {evidence}")

    registry = command_registry(manifest)
    for command_id in phase.get("commands", []) if isinstance(phase.get("commands", []), list) else []:
        log_path = command_log_path(run_root, phase_id, str(command_id))
        passed, reason = command_log_passed(log_path)
        if not passed:
            command = registry.get(str(command_id), {}).get("command", str(command_id))
            errors.append(f"mandatory command failed/missing: {command_id} ({command}) - {reason}")

    allowed = phase.get("allowed_paths", [])
    allowed_list = [str(p) for p in allowed] if isinstance(allowed, list) else []
    changed = changed_files(run_root, manifest)
    drift = [path for path in changed if not is_allowed_path(path, allowed_list)]
    if drift:
        print("SCOPE_DRIFT")
        for path in drift:
            print(f"- {path}")
        errors.append(f"{len(drift)} changed file(s) outside phase allowed_paths")

    trust, total, pct = trust_debt_for_phase(phase)
    print(f"TRUST_DEBT phase {phase_id}: {trust}/{total} trust-prior ({pct:.0f}%)")

    if errors:
        append_event(run_root, "phase.gate.fail", phase=int(args.phase), status="fail", data={"errors": errors})
        print("PHASE_GATE_VERIFY fail")
        for error in errors:
            print(f"- {error}")
        return 1

    set_phase_status(manifest, phase_id, "complete", run_root)
    append_event(run_root, "phase.gate.pass", phase=int(args.phase), status="pass")
    print("PHASE_GATE_VERIFY pass")
    print(f"Phase: {phase_id}")
    print(f"Evidence root: {phase_evidence_root(run_root, phase_id)}")
    return 0


def deliverable_present(run_root: Path, manifest: dict[str, Any], deliverable: str) -> tuple[bool, str]:
    value = str(deliverable).strip()
    if not value:
        return True, "empty deliverable ignored"
    if any(ch in value for ch in "*?[]"):
        matches = glob.glob(value, recursive=True)
        if matches:
            return True, f"glob matched {len(matches)} path(s)"
    rc, out, err = run_repo_state(run_root, "deliverable", baseline_ref(manifest, run_root), value)
    if rc == 0:
        return True, out.strip() or "present"
    return False, (out.strip() or err.strip() or "missing")


def cmd_audit(args: argparse.Namespace) -> int:
    run_root = run_root_from_arg(args.run_root)
    manifest = load_json(manifest_path(run_root))
    append_event(run_root, "audit.start", message="final audit started")
    gaps: list[str] = []

    manifest_errors = validate_manifest(manifest, run_root)
    for error in manifest_errors:
        gaps.append(f"manifest: {error}")

    for phase in phases(manifest):
        phase_id = phase.get("id")
        if phase.get("status") not in {"complete"}:
            gaps.append(f"phase {phase_id}: status is {phase.get('status', 'pending')}, expected complete")
        for command_id in phase.get("commands", []) if isinstance(phase.get("commands", []), list) else []:
            passed, reason = command_log_passed(command_log_path(run_root, phase_id, str(command_id)))
            if not passed:
                gaps.append(f"phase {phase_id}: command {command_id} not clean - {reason}")
        for deliverable in phase.get("deliverables", []) if isinstance(phase.get("deliverables", []), list) else []:
            present, evidence = deliverable_present(run_root, manifest, str(deliverable))
            if not present:
                gaps.append(f"phase {phase_id}: deliverable {deliverable} missing - {evidence}")

    trust, total = trust_debt_for_manifest(manifest)
    pct = (trust / total * 100.0) if total else 0.0
    print("AUDIT_VERIFY")
    print(f"Phases: {len(phases(manifest))}")
    print(f"TRUST_DEBT run: {trust}/{total} trust-prior ({pct:.0f}%)")
    if gaps:
        append_event(run_root, "audit.fail", status="fail", data={"gaps": gaps})
        print("AUDIT_GAPS")
        for gap in gaps:
            print(f"- {gap}")
        return 1

    run = manifest.setdefault("run", {})
    if isinstance(run, dict):
        run["status"] = "COMPLETE"
        run["last_update"] = utc_now()
        write_json(manifest_path(run_root), manifest)
    append_event(run_root, "audit.pass", status="pass")
    print("AUDIT_COMPLETE")
    return 0


def legacy_resume(run_root: Path) -> int:
    state = run_root / "STATE.md"
    if not state.exists():
        print(f"No Supergoal run state found at {run_root}")
        return 1
    text = state.read_text(encoding="utf-8", errors="replace")
    status = first_match(text, r"Status:\*\*\s*([^\n<]+)|Status:\s*([^\n<]+)") or "unknown"
    phase = first_match(text, r"Current phase:\*\*\s*([^\n<]+)|Current phase:\s*([^\n<]+)") or "unknown"
    print("LEGACY_RUN_FALLBACK")
    print(f"Status: {status.strip()}")
    print(f"Next action: resume markdown-only run at phase {phase.strip()} using PROTOCOL.md")
    return 0


def first_match(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text)
    if not match:
        return None
    for group in match.groups():
        if group:
            return group
    return None


def cmd_resume(args: argparse.Namespace) -> int:
    target = run_root_from_arg(args.run_root)
    if target.is_dir() and manifest_path(target).exists():
        return resume_one(target)
    if target.is_dir() and (target / "STATE.md").exists():
        return legacy_resume(target)
    if target.is_dir():
        runs = sorted(target.glob("*/run.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not runs:
            print(f"No v1 run.json files found under {target}")
            return 1
        for path in runs[:5]:
            resume_summary(path.parent)
        return 0
    print(f"No Supergoal run found at {target}")
    return 1


def resume_summary(run_root: Path) -> None:
    manifest = load_json(manifest_path(run_root))
    run = manifest.get("run", {}) if isinstance(manifest.get("run"), dict) else {}
    phase = next_pending_phase(manifest)
    status = run.get("status", "unknown")
    if phase:
        print(f"{run_root}: {status}; next phase {phase.get('id')} - {phase.get('name')}")
    else:
        print(f"{run_root}: {status}; no pending phase")


def next_pending_phase(manifest: dict[str, Any]) -> dict[str, Any] | None:
    blocked = [p for p in phases(manifest) if p.get("status") == "blocked"]
    if blocked:
        return blocked[0]
    for status in ("in_progress", "pending"):
        for phase in phases(manifest):
            if phase.get("status", "pending") == status:
                return phase
    return None


def resume_one(run_root: Path) -> int:
    manifest = load_json(manifest_path(run_root))
    run = manifest.get("run", {}) if isinstance(manifest.get("run"), dict) else {}
    phase = next_pending_phase(manifest)
    print("SUPERGOAL_RESUME_DOCTOR")
    print(f"Run: {run.get('id', run_root.name)}")
    print(f"Status: {run.get('status', 'unknown')}")
    if phase:
        print(f"Next action: resume phase {phase.get('id')} - {phase.get('name')}")
        print(f"Spec: {run_root / 'phases' / ('phase-' + str(phase.get('id')) + '.md')}")
    else:
        print("Next action: run final audit/report or close the completed run")
    failure_events = [event for event in load_events(run_root) if "fail" in str(event.get("type", "")).lower() or "blocked" in str(event.get("status", "")).lower()]
    if run.get("status") == "BLOCKED" or failure_events:
        print("Blocked/failure history:")
        for event in failure_events[-5:]:
            label = event.get("type", "event")
            message = event.get("message") or event.get("data") or ""
            print(f"- {event.get('ts', '')} {label}: {message}")
    return 0


def html_escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def cmd_report(args: argparse.Namespace) -> int:
    run_root = run_root_from_arg(args.run_root)
    if not manifest_path(run_root).exists():
        return legacy_report(run_root)
    manifest = load_json(manifest_path(run_root))
    events = load_events(run_root)
    report = render_report(run_root, manifest, events)
    out = run_root / "report.html"
    out.write_text(report, encoding="utf-8")
    append_event(run_root, "report.write", status="pass", message=str(out))
    print(f"RUN_REPORT_WRITTEN {out}")
    return 0


def legacy_report(run_root: Path) -> int:
    if not (run_root / "STATE.md").exists():
        print(f"No run.json or STATE.md found at {run_root}")
        return 1
    state = html_escape((run_root / "STATE.md").read_text(encoding="utf-8", errors="replace"))
    report = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Supergoal Legacy Run</title>
<style>body{{font-family:system-ui;margin:40px;line-height:1.5}}pre{{white-space:pre-wrap;background:#f6f7f9;padding:16px;border-radius:8px}}</style></head>
<body><h1>Supergoal Legacy Run</h1><p>LEGACY_RUN_FALLBACK: markdown-only run.</p><pre>{state}</pre></body></html>
"""
    out = run_root / "report.html"
    out.write_text(report, encoding="utf-8")
    print(f"RUN_REPORT_WRITTEN {out}")
    return 0


def render_report(run_root: Path, manifest: dict[str, Any], events: list[dict[str, Any]]) -> str:
    run = manifest.get("run", {}) if isinstance(manifest.get("run"), dict) else {}
    trust, total = trust_debt_for_manifest(manifest)
    trust_pct = (trust / total * 100.0) if total else 0.0
    phase_rows = []
    for phase in phases(manifest):
        phase_id = phase.get("id")
        phase_trust, phase_total, phase_pct = trust_debt_for_phase(phase)
        evidence_root = phase_evidence_root(run_root, phase_id)
        evidence_count = len([p for p in evidence_root.rglob("*") if p.is_file()]) if evidence_root.exists() else 0
        phase_rows.append(
            "<tr>"
            f"<td>{html_escape(phase_id)}</td>"
            f"<td>{html_escape(phase.get('name', ''))}</td>"
            f"<td><span class=\"pill\">{html_escape(phase.get('status', 'pending'))}</span></td>"
            f"<td>{len(phase.get('commands', []) if isinstance(phase.get('commands', []), list) else [])}</td>"
            f"<td>{phase_trust}/{phase_total} ({phase_pct:.0f}%)</td>"
            f"<td>{evidence_count}</td>"
            "</tr>"
        )
    event_rows = []
    for event in events[-80:]:
        event_rows.append(
            "<tr>"
            f"<td>{html_escape(event.get('ts', ''))}</td>"
            f"<td>{html_escape(event.get('type', ''))}</td>"
            f"<td>{html_escape(event.get('phase', ''))}</td>"
            f"<td>{html_escape(event.get('status', ''))}</td>"
            f"<td>{html_escape(event.get('message') or event.get('data') or '')}</td>"
            "</tr>"
        )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Supergoal Run Report - {html_escape(run.get('title', run_root.name))}</title>
<style>
:root {{ color-scheme: light; --ink:#111827; --muted:#667085; --line:#d9e2ec; --bg:#f7f9fb; --panel:#ffffff; --accent:#0f766e; --risk:#b42318; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color:var(--ink); background:var(--bg); line-height:1.45; }}
main {{ width:min(1120px, calc(100vw - 32px)); margin:0 auto; padding:32px 0 56px; }}
header {{ padding:24px 0 18px; border-bottom:1px solid var(--line); }}
h1 {{ margin:0 0 8px; font-size:32px; letter-spacing:0; }}
h2 {{ margin:28px 0 12px; font-size:18px; }}
p {{ margin:0 0 10px; color:var(--muted); }}
.grid {{ display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:12px; margin-top:18px; }}
.metric {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:14px; }}
.metric b {{ display:block; font-size:22px; }}
.metric span {{ color:var(--muted); font-size:13px; }}
table {{ width:100%; border-collapse:collapse; background:var(--panel); border:1px solid var(--line); border-radius:8px; overflow:hidden; }}
th, td {{ text-align:left; padding:10px 12px; border-bottom:1px solid var(--line); vertical-align:top; font-size:14px; }}
th {{ background:#eef4f7; font-size:12px; color:#334155; text-transform:uppercase; letter-spacing:.04em; }}
tr:last-child td {{ border-bottom:0; }}
.pill {{ display:inline-block; border:1px solid var(--line); border-radius:999px; padding:2px 8px; background:#fff; }}
.debt {{ color:{'#b42318' if trust_pct > 30 else '#0f766e'}; }}
@media (max-width: 760px) {{ .grid {{ grid-template-columns:1fr 1fr; }} table {{ display:block; overflow-x:auto; }} }}
</style>
</head>
<body>
<main>
<header>
<p>Supergoal v1 run report</p>
<h1>{html_escape(run.get('title', run_root.name))}</h1>
<p>{html_escape(run.get('task', ''))}</p>
</header>
<section class="grid">
<div class="metric"><b>{html_escape(run.get('status', 'unknown'))}</b><span>run status</span></div>
<div class="metric"><b>{len(phases(manifest))}</b><span>phases</span></div>
<div class="metric"><b class="debt">{trust}/{total}</b><span>trust-prior criteria ({trust_pct:.0f}%)</span></div>
<div class="metric"><b>{len(events)}</b><span>recorded events</span></div>
</section>
<h2>Phases</h2>
<table><thead><tr><th>ID</th><th>Phase</th><th>Status</th><th>Commands</th><th>Trust Debt</th><th>Evidence Files</th></tr></thead><tbody>{''.join(phase_rows)}</tbody></table>
<h2>Events</h2>
<table><thead><tr><th>Time</th><th>Type</th><th>Phase</th><th>Status</th><th>Message</th></tr></thead><tbody>{''.join(event_rows)}</tbody></table>
</main>
</body>
</html>
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Supergoal v1 run kernel")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init-run", help="create a v1 run.json skeleton")
    init.add_argument("run_root")
    init.add_argument("--id")
    init.add_argument("--title")
    init.add_argument("--task")
    init.add_argument("--baseline")
    init.add_argument("--host")
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=cmd_init_run)

    rec = sub.add_parser("record-event", help="append an event to events.jsonl")
    rec.add_argument("run_root")
    rec.add_argument("--type", required=True)
    rec.add_argument("--phase", type=int)
    rec.add_argument("--status")
    rec.add_argument("--message")
    rec.add_argument("--data-json")
    rec.set_defaults(func=cmd_record_event)

    gate = sub.add_parser("gate-phase", help="verify phase evidence, commands, and scope")
    gate.add_argument("run_root")
    gate.add_argument("phase", type=int)
    gate.set_defaults(func=cmd_gate_phase)

    audit = sub.add_parser("audit", help="run final manifest/deliverable audit")
    audit.add_argument("run_root")
    audit.set_defaults(func=cmd_audit)

    resume = sub.add_parser("resume", help="show exact next action for a run")
    resume.add_argument("run_root")
    resume.set_defaults(func=cmd_resume)

    report = sub.add_parser("report", help="write report.html under the run root")
    report.add_argument("run_root")
    report.set_defaults(func=cmd_report)

    validate = sub.add_parser("validate-run", help="validate run.json and required artifacts")
    validate.add_argument("run_root")
    validate.set_defaults(func=cmd_validate_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

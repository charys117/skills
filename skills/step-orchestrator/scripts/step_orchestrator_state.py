#!/usr/bin/env python3
"""Local runtime-state helper for the step-orchestrator skill."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re


STATE_ROOT = Path(".agents/step-orchestrator/rounds")
DEFAULT_HEARTBEAT_SECONDS = 300
TERMINAL_STATUSES = {"done", "blocked", "superseded"}
VALID_STATUSES = {"starting", "running", "done", "blocked", "superseded"}


class ScriptError(RuntimeError):
    pass


def stderr(message: str) -> None:
    print(message, file=sys.stderr)


def print_json(payload: dict[str, object]) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def run_command(args: list[str], *, cwd: Path | None = None, allow_failure: bool = False) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0 and not allow_failure:
        raise ScriptError(f"Command failed ({proc.returncode}): {' '.join(args)}\n{proc.stderr.strip()}")
    return proc


def git_root(start: Path) -> Path | None:
    proc = run_command(["git", "rev-parse", "--show-toplevel"], cwd=start, allow_failure=True)
    if proc.returncode != 0:
        return None
    return Path(proc.stdout.strip()).resolve()


def check_agents_ignored(repo_root: Path) -> None:
    workspace_probe = repo_root / ".agents" / "step-orchestrator" / "probe"
    repo_git_root = git_root(repo_root)
    if repo_git_root is not None:
        relative_probe = workspace_probe.resolve().relative_to(repo_git_root)
        proc = run_command(
            ["git", "check-ignore", "-q", str(relative_probe)],
            cwd=repo_git_root,
            allow_failure=True,
        )
        if proc.returncode == 0:
            return
    gitignore = repo_root / ".gitignore"
    if not gitignore.exists():
        stderr("[warn] .gitignore is missing in the target workspace; add .agents/ if you want runtime state to stay local.")
        return
    text = gitignore.read_text(encoding="utf-8", errors="ignore")
    if ".agents/" not in text:
        stderr("[warn] The target workspace .gitignore does not mention .agents/. Add it before committing if you want runtime state to remain local.")


def utc_now(override: str | None = None) -> datetime:
    if override:
        return parse_timestamp(override)
    return datetime.now(timezone.utc)


def parse_timestamp(value: str) -> datetime:
    cleaned = value.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    dt = datetime.fromisoformat(cleaned)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def isoformat_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso_or_none(value: str | None) -> datetime | None:
    if not value:
        return None
    return parse_timestamp(value)


def sanitize_step_id(step_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", step_id.strip())
    safe = safe.strip("-")
    if not safe:
        raise ScriptError("Step ID must contain at least one safe path character.")
    return safe


def role_prefix(role: str) -> str:
    if role == "implementer":
        return "A"
    if role == "reviewer":
        return "B"
    raise ScriptError(f"Unsupported role: {role}")


def state_root(repo_root: Path) -> Path:
    return repo_root / STATE_ROOT


def step_dir(repo_root: Path, step_id: str) -> Path:
    return state_root(repo_root) / f"step-{sanitize_step_id(step_id)}"


def round_path(repo_root: Path, step_id: str, role: str, round_number: int) -> Path:
    prefix = role_prefix(role)
    return step_dir(repo_root, step_id) / f"{prefix}{round_number}.json"


def ensure_state_path_within_root(path: Path, repo_root: Path) -> Path:
    resolved = path.resolve()
    root = state_root(repo_root).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ScriptError(f"State file must live under {root}") from exc
    return resolved


def resolve_path_from_args(args: argparse.Namespace, repo_root: Path, *, require_round: bool) -> Path:
    if getattr(args, "state_file", None):
        path = Path(args.state_file)
        if not path.is_absolute():
            path = repo_root / path
        resolved = ensure_state_path_within_root(path, repo_root)
        if getattr(args, "step_id", None) and getattr(args, "role", None) and getattr(args, "round", None):
            expected = round_path(repo_root, args.step_id, args.role, args.round).resolve()
            if resolved != expected:
                raise ScriptError(f"State file does not match the expected round path: {expected}")
        return resolved
    if not getattr(args, "step_id", None) or not getattr(args, "role", None):
        raise ScriptError("Provide either --state-file or both --step-id and --role.")
    if require_round and getattr(args, "round", None) is None:
        raise ScriptError("Provide --round when --state-file is omitted.")
    if getattr(args, "round", None) is None:
        authoritative = authoritative_round_path(repo_root, args.step_id, args.role)
        if authoritative is None:
            raise ScriptError(f"No round file found for step {args.step_id} role {args.role}.")
        return authoritative
    return round_path(repo_root, args.step_id, args.role, args.round).resolve()


def validate_state(path: Path, payload: dict[str, object]) -> dict[str, object]:
    required_text_fields = (
        "step_id",
        "step_title",
        "role",
        "owner",
        "status",
        "started_at",
        "last_heartbeat_at",
        "next_update_due_at",
    )
    for field in required_text_fields:
        if str(payload.get(field, "")).strip() == "":
            raise ScriptError(f"State file is missing required field {field}: {path}")
    if str(payload["role"]) not in {"implementer", "reviewer"}:
        raise ScriptError(f"State file has unsupported role {payload['role']}: {path}")
    try:
        round_number = int(payload.get("round", 0))
    except (TypeError, ValueError) as exc:
        raise ScriptError(f"State file has invalid round value {payload.get('round')}: {path}") from exc
    if round_number < 1:
        raise ScriptError(f"State file has invalid round value {round_number}: {path}")
    payload["round"] = round_number
    if str(payload["status"]) not in VALID_STATUSES:
        raise ScriptError(f"State file has unsupported status {payload['status']}: {path}")
    return payload


def load_state(path: Path) -> dict[str, object]:
    if not path.exists():
        raise ScriptError(f"State file does not exist: {path}")
    return validate_state(path, json.loads(path.read_text(encoding="utf-8")))


def save_state(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def parse_round_from_path(path: Path) -> int | None:
    match = re.fullmatch(r"[AB](\d+)\.json", path.name)
    if not match:
        return None
    return int(match.group(1))


def round_files(repo_root: Path, step_id: str, role: str) -> list[Path]:
    directory = step_dir(repo_root, step_id)
    if not directory.exists():
        return []
    prefix = role_prefix(role)
    files = []
    for candidate in directory.glob(f"{prefix}*.json"):
        round_number = parse_round_from_path(candidate)
        if round_number is not None:
            files.append(candidate.resolve())
    return sorted(files, key=lambda item: parse_round_from_path(item) or -1)


def authoritative_round_path(repo_root: Path, step_id: str, role: str) -> Path | None:
    files = round_files(repo_root, step_id, role)
    if not files:
        return None
    non_terminal: list[tuple[int, Path]] = []
    fallback: list[tuple[int, Path]] = []
    for candidate in files:
        state = load_state(candidate)
        round_number = int(state["round"])
        fallback.append((round_number, candidate))
        if str(state["status"]) not in TERMINAL_STATUSES:
            non_terminal.append((round_number, candidate))
    if non_terminal:
        return max(non_terminal, key=lambda item: item[0])[1]
    return max(fallback, key=lambda item: item[0])[1]


def heartbeat_window_seconds(state: dict[str, object], default_seconds: int) -> int:
    last_heartbeat = parse_iso_or_none(str(state.get("last_heartbeat_at", "")))
    next_due = parse_iso_or_none(str(state.get("next_update_due_at", "")))
    if last_heartbeat and next_due:
        delta = int((next_due - last_heartbeat).total_seconds())
        if delta > 0:
            return delta
    return default_seconds


def current_freshness(
    repo_root: Path,
    path: Path,
    state: dict[str, object],
    *,
    now: datetime,
    default_heartbeat_seconds: int,
) -> dict[str, object]:
    authoritative = authoritative_round_path(repo_root, str(state["step_id"]), str(state["role"]))
    is_authoritative = authoritative == path.resolve()
    if not is_authoritative:
        return {
            "is_authoritative": False,
            "authoritative_state_file": str(authoritative) if authoritative else "",
            "freshness": "superseded",
            "recommended_action": "ignore",
            "age_seconds": None,
            "heartbeat_window_seconds": heartbeat_window_seconds(state, default_heartbeat_seconds),
        }
    status = str(state["status"])
    window_seconds = heartbeat_window_seconds(state, default_heartbeat_seconds)
    if status in TERMINAL_STATUSES:
        return {
            "is_authoritative": True,
            "authoritative_state_file": str(path),
            "freshness": "terminal",
            "recommended_action": "stop",
            "age_seconds": None,
            "heartbeat_window_seconds": window_seconds,
        }
    last_heartbeat = parse_iso_or_none(str(state.get("last_heartbeat_at", "")))
    age_seconds = 0
    if last_heartbeat:
        age_seconds = max(0, int((now - last_heartbeat).total_seconds()))
    if age_seconds < window_seconds:
        freshness = "fresh"
        recommended_action = "wait"
    elif age_seconds < window_seconds * 2:
        freshness = "stale_once"
        recommended_action = "nudge"
    else:
        freshness = "stale_twice"
        recommended_action = "replace"
    return {
        "is_authoritative": True,
        "authoritative_state_file": str(path),
        "freshness": freshness,
        "recommended_action": recommended_action,
        "age_seconds": age_seconds,
        "heartbeat_window_seconds": window_seconds,
    }


def ensure_mutable(repo_root: Path, path: Path, state: dict[str, object]) -> None:
    status = str(state["status"])
    if status in TERMINAL_STATUSES:
        raise ScriptError(f"Cannot update a terminal round in status {status}: {path}")
    authoritative = authoritative_round_path(repo_root, str(state["step_id"]), str(state["role"]))
    if authoritative and authoritative != path.resolve():
        raise ScriptError(f"Cannot update a superseded round. Current authoritative file: {authoritative}")


def command_result(path: Path, state: dict[str, object]) -> None:
    print_json({"state_file": str(path), "state": state})


def add_common_parser_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo-root", default=".", help="Target repo root or a directory inside the repo.")
    parser.add_argument("--now", default="", help="Optional ISO8601 UTC timestamp override for deterministic tests.")


def add_locator_args(parser: argparse.ArgumentParser, *, include_step_title: bool = False, round_required: bool = True) -> None:
    parser.add_argument("--state-file", default="", help="Optional explicit round-state file path under .agents/step-orchestrator/rounds/.")
    parser.add_argument("--step-id", default="", help="Logical step identifier.")
    if include_step_title:
        parser.add_argument("--step-title", required=True, help="Step title stored in the state file.")
    parser.add_argument("--role", choices=["implementer", "reviewer"], help="Round role.")
    parser.add_argument("--round", type=int, required=round_required, help="Round number, such as 1 for A1 or B1.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Maintain local runtime state for the step-orchestrator skill.")
    add_common_parser_options(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    start_parser = subparsers.add_parser("start", help="Create and claim a new round-state file.")
    add_locator_args(start_parser, include_step_title=True, round_required=True)
    start_parser.add_argument("--owner", required=True, help="Subagent label, such as A1 or B2.")
    start_parser.add_argument("--heartbeat-seconds", type=int, default=DEFAULT_HEARTBEAT_SECONDS, help="Heartbeat window in seconds. Defaults to 300.")
    start_parser.add_argument("--phase", default="claimed", help="Current phase.")
    start_parser.add_argument("--last-checkpoint", default="", help="Most recent durable checkpoint.")
    start_parser.add_argument("--next-step", default="", help="Next expected action.")
    start_parser.add_argument("--summary", default="", help="Short current summary.")

    heartbeat_parser = subparsers.add_parser("heartbeat", help="Refresh a running round-state file.")
    add_locator_args(heartbeat_parser, round_required=False)
    heartbeat_parser.add_argument("--heartbeat-seconds", type=int, default=DEFAULT_HEARTBEAT_SECONDS, help="Heartbeat window in seconds. Defaults to 300.")
    heartbeat_parser.add_argument("--phase", default=None, help="Updated phase.")
    heartbeat_parser.add_argument("--last-checkpoint", default=None, help="Updated checkpoint.")
    heartbeat_parser.add_argument("--next-step", default=None, help="Updated next step.")
    heartbeat_parser.add_argument("--summary", default=None, help="Updated summary.")

    read_parser = subparsers.add_parser("read", help="Read a round-state file and compute freshness.")
    add_locator_args(read_parser, round_required=False)
    read_parser.add_argument("--heartbeat-seconds", type=int, default=DEFAULT_HEARTBEAT_SECONDS, help="Fallback heartbeat window in seconds when the file lacks timing data.")

    finish_parser = subparsers.add_parser("finish", help="Mark a round as done or superseded.")
    add_locator_args(finish_parser, round_required=False)
    finish_parser.add_argument("--status", choices=["done", "superseded"], default="done", help="Terminal status to write.")
    finish_parser.add_argument("--summary", default=None, help="Optional final summary.")
    finish_parser.add_argument("--phase", default=None, help="Optional final phase.")

    block_parser = subparsers.add_parser("block", help="Mark a round as blocked.")
    add_locator_args(block_parser, round_required=False)
    block_parser.add_argument("--blocker", required=True, help="Blocker reason.")
    block_parser.add_argument("--summary", default=None, help="Optional blocked summary.")
    block_parser.add_argument("--phase", default=None, help="Optional blocked phase.")

    return parser.parse_args()


def cmd_start(args: argparse.Namespace, repo_root: Path) -> None:
    check_agents_ignored(repo_root)
    if not args.step_id.strip():
        raise ScriptError("start requires --step-id.")
    if not args.role:
        raise ScriptError("start requires --role.")
    now = utc_now(args.now or None)
    path = resolve_path_from_args(args, repo_root, require_round=True)
    if path.exists():
        raise ScriptError(f"State file already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "step_id": args.step_id,
        "step_title": args.step_title,
        "role": args.role,
        "round": args.round,
        "owner": args.owner,
        "status": "starting",
        "started_at": isoformat_utc(now),
        "last_heartbeat_at": isoformat_utc(now),
        "phase": args.phase,
        "last_checkpoint": args.last_checkpoint,
        "next_step": args.next_step,
        "next_update_due_at": isoformat_utc(now + timedelta(seconds=args.heartbeat_seconds)),
        "summary": args.summary,
        "blocker": "",
    }
    save_state(path, state)
    command_result(path, state)


def cmd_heartbeat(args: argparse.Namespace, repo_root: Path) -> None:
    now = utc_now(args.now or None)
    path = resolve_path_from_args(args, repo_root, require_round=False)
    state = load_state(path)
    ensure_mutable(repo_root, path, state)
    if args.phase is not None:
        state["phase"] = args.phase
    if args.last_checkpoint is not None:
        state["last_checkpoint"] = args.last_checkpoint
    if args.next_step is not None:
        state["next_step"] = args.next_step
    if args.summary is not None:
        state["summary"] = args.summary
    state["status"] = "running"
    state["last_heartbeat_at"] = isoformat_utc(now)
    state["next_update_due_at"] = isoformat_utc(now + timedelta(seconds=args.heartbeat_seconds))
    save_state(path, state)
    command_result(path, state)


def cmd_read(args: argparse.Namespace, repo_root: Path) -> None:
    now = utc_now(args.now or None)
    path = resolve_path_from_args(args, repo_root, require_round=False)
    state = load_state(path)
    freshness = current_freshness(repo_root, path, state, now=now, default_heartbeat_seconds=args.heartbeat_seconds)
    print_json(
        {
            "state_file": str(path),
            "state": state,
            "checked_at": isoformat_utc(now),
            **freshness,
        }
    )


def cmd_finish(args: argparse.Namespace, repo_root: Path) -> None:
    now = utc_now(args.now or None)
    path = resolve_path_from_args(args, repo_root, require_round=False)
    state = load_state(path)
    if str(state["status"]) in TERMINAL_STATUSES:
        raise ScriptError(f"Cannot update a terminal round in status {state['status']}: {path}")
    if args.status != "superseded":
        ensure_mutable(repo_root, path, state)
    if args.phase is not None:
        state["phase"] = args.phase
    if args.summary is not None:
        state["summary"] = args.summary
    state["status"] = args.status
    state["last_heartbeat_at"] = isoformat_utc(now)
    state["next_update_due_at"] = isoformat_utc(now)
    save_state(path, state)
    command_result(path, state)


def cmd_block(args: argparse.Namespace, repo_root: Path) -> None:
    now = utc_now(args.now or None)
    path = resolve_path_from_args(args, repo_root, require_round=False)
    state = load_state(path)
    ensure_mutable(repo_root, path, state)
    if args.phase is not None:
        state["phase"] = args.phase
    if args.summary is not None:
        state["summary"] = args.summary
    state["status"] = "blocked"
    state["blocker"] = args.blocker
    state["last_heartbeat_at"] = isoformat_utc(now)
    state["next_update_due_at"] = isoformat_utc(now)
    save_state(path, state)
    command_result(path, state)


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    try:
        if args.command == "start":
            cmd_start(args, repo_root)
        elif args.command == "heartbeat":
            cmd_heartbeat(args, repo_root)
        elif args.command == "read":
            cmd_read(args, repo_root)
        elif args.command == "finish":
            cmd_finish(args, repo_root)
        elif args.command == "block":
            cmd_block(args, repo_root)
        else:
            raise ScriptError(f"Unsupported command: {args.command}")
        return 0
    except ScriptError as exc:
        stderr(f"[error] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Local state helper for the notion-board skill.

This script does not create or mutate Notion content. It only stores and
reports the local board binding plus sync watermarks in:

  <repo_root>/.agents/notion-board/state.json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path


SCHEMA_VERSION = 1
STATE_FILE = Path(".agents/notion-board/state.json")


class ScriptError(RuntimeError):
    pass


@dataclass
class BoardState:
    schema_version: int
    repo_root: str
    repo_name: str
    notion_profile: str
    board_page_id: str
    board_url: str
    project_guide_page_id: str = ""
    modules_db_id: str = ""
    constants_db_id: str = ""
    plans_db_id: str = ""
    work_items_db_id: str = ""
    commit_log_db_id: str = ""
    last_repo_sync_commit: str = ""
    last_commit_log_sync: str = ""


def stderr(message: str) -> None:
    print(message, file=sys.stderr)


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


def git_root(start: Path) -> Path:
    proc = run_command(["git", "rev-parse", "--show-toplevel"], cwd=start, allow_failure=True)
    if proc.returncode != 0:
        stderr("[warn] Not inside a git repo; using the current directory as repo root.")
        return start.resolve()
    return Path(proc.stdout.strip()).resolve()


def git_head(repo_root: Path) -> str | None:
    proc = run_command(["git", "rev-parse", "HEAD"], cwd=repo_root, allow_failure=True)
    return proc.stdout.strip() if proc.returncode == 0 else None


def extract_notion_id(value: str) -> str:
    match = re.search(
        r"([0-9a-fA-F]{32}|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})",
        value.strip(),
    )
    if not match:
        raise ScriptError(f"Could not extract a Notion UUID from: {value}")
    return str(uuid.UUID(match.group(1).replace("-", "")))


def state_path(repo_root: Path) -> Path:
    return repo_root / STATE_FILE


def load_state(repo_root: Path) -> BoardState | None:
    path = state_path(repo_root)
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return BoardState(**payload)


def save_state(repo_root: Path, state: BoardState) -> None:
    check_agents_ignored(repo_root)
    path = state_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def delete_state(repo_root: Path) -> None:
    path = state_path(repo_root)
    if path.exists():
        path.unlink()
    try:
        path.parent.rmdir()
    except OSError:
        pass


def check_agents_ignored(repo_root: Path) -> None:
    gitignore = repo_root / ".gitignore"
    if not gitignore.exists():
        stderr("[warn] .gitignore is missing; add .agents/ if you want board state to stay local.")
        return
    text = gitignore.read_text(encoding="utf-8", errors="ignore")
    if ".agents/" not in text:
        stderr("[warn] .gitignore does not ignore .agents/. Add it before committing if you want board state to remain local.")


def normalize_commit(value: str | None, repo_root: Path) -> str:
    if not value:
        return ""
    if value.upper() == "HEAD":
        return git_head(repo_root) or ""
    return value


def build_status(repo_root: Path, state: BoardState | None) -> dict[str, object]:
    head = git_head(repo_root)
    if state is None:
        return {
            "repo_root": str(repo_root),
            "current_head": head,
            "bound": False,
        }
    return {
        "schema_version": state.schema_version,
        "repo_root": state.repo_root,
        "repo_name": state.repo_name,
        "notion_profile": state.notion_profile,
        "board_page_id": state.board_page_id,
        "board_url": state.board_url,
        "project_guide_page_id": state.project_guide_page_id,
        "modules_db_id": state.modules_db_id,
        "constants_db_id": state.constants_db_id,
        "plans_db_id": state.plans_db_id,
        "work_items_db_id": state.work_items_db_id,
        "commit_log_db_id": state.commit_log_db_id,
        "last_repo_sync_commit": state.last_repo_sync_commit,
        "last_commit_log_sync": state.last_commit_log_sync,
        "current_head": head,
        "bound": True,
        "repo_sync_stale": bool(head and state.last_repo_sync_commit and head != state.last_repo_sync_commit),
        "commit_log_stale": bool(head and state.last_commit_log_sync and head != state.last_commit_log_sync),
    }


def print_status(repo_root: Path, state: BoardState | None) -> None:
    print(json.dumps(build_status(repo_root, state), indent=2, ensure_ascii=False))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Maintain local state for a repo-backed Notion board.")
    parser.add_argument("--repo-root", default=".", help="Target repo root or a directory inside the repo.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    bind_parser = subparsers.add_parser("bind", help="Write or update the local binding for an already-created board.")
    bind_parser.add_argument("--board-url", required=True, help="Board page URL or ID.")
    bind_parser.add_argument("--notion-profile", default="", help="Optional Notion profile label to store in local state.")
    bind_parser.add_argument("--project-guide-page-id", help="Project Guide page ID.")
    bind_parser.add_argument("--modules-db-id", help="Modules database ID.")
    bind_parser.add_argument("--constants-db-id", help="Constants database ID.")
    bind_parser.add_argument("--plans-db-id", help="Plans database ID.")
    bind_parser.add_argument("--work-items-db-id", help="Work Items database ID.")
    bind_parser.add_argument("--commit-log-db-id", help="Commit Log database ID.")
    bind_parser.add_argument(
        "--last-repo-sync-commit",
        default="",
        help="Repo-derived sync watermark. Pass HEAD to store the current HEAD.",
    )
    bind_parser.add_argument(
        "--last-commit-log-sync",
        default="HEAD",
        help="Commit log watermark. Defaults to HEAD so existing history is not backfilled.",
    )

    mark_parser = subparsers.add_parser("mark-sync", help="Update one or both local sync watermarks after a successful sync.")
    mark_parser.add_argument(
        "--repo-derived",
        nargs="?",
        const="HEAD",
        help="Set last_repo_sync_commit. Omit the value to use HEAD.",
    )
    mark_parser.add_argument(
        "--commit-log",
        nargs="?",
        const="HEAD",
        help="Set last_commit_log_sync. Omit the value to use HEAD.",
    )

    subparsers.add_parser("status", help="Print the current local binding and staleness flags.")
    subparsers.add_parser("clear", help="Delete the local state file.")

    return parser.parse_args()


def cmd_bind(args: argparse.Namespace, repo_root: Path) -> None:
    state = load_state(repo_root) or BoardState(
        schema_version=SCHEMA_VERSION,
        repo_root=str(repo_root),
        repo_name=repo_root.name,
        notion_profile="",
        board_page_id="",
        board_url="",
    )
    state.schema_version = SCHEMA_VERSION
    state.repo_root = str(repo_root)
    state.repo_name = repo_root.name
    state.notion_profile = args.notion_profile
    state.board_url = args.board_url
    state.board_page_id = extract_notion_id(args.board_url)
    state.project_guide_page_id = extract_notion_id(args.project_guide_page_id) if args.project_guide_page_id else state.project_guide_page_id
    state.modules_db_id = extract_notion_id(args.modules_db_id) if args.modules_db_id else state.modules_db_id
    state.constants_db_id = extract_notion_id(args.constants_db_id) if args.constants_db_id else state.constants_db_id
    state.plans_db_id = extract_notion_id(args.plans_db_id) if args.plans_db_id else state.plans_db_id
    state.work_items_db_id = extract_notion_id(args.work_items_db_id) if args.work_items_db_id else state.work_items_db_id
    state.commit_log_db_id = extract_notion_id(args.commit_log_db_id) if args.commit_log_db_id else state.commit_log_db_id
    state.last_repo_sync_commit = normalize_commit(args.last_repo_sync_commit, repo_root)
    state.last_commit_log_sync = normalize_commit(args.last_commit_log_sync, repo_root)
    save_state(repo_root, state)
    print_status(repo_root, state)


def cmd_mark_sync(args: argparse.Namespace, repo_root: Path) -> None:
    state = load_state(repo_root)
    if state is None:
        raise ScriptError("No board binding found. Run `bind` first.")
    changed = False
    if args.repo_derived is not None:
        state.last_repo_sync_commit = normalize_commit(args.repo_derived, repo_root)
        changed = True
    if args.commit_log is not None:
        state.last_commit_log_sync = normalize_commit(args.commit_log, repo_root)
        changed = True
    if not changed:
        raise ScriptError("Nothing to update. Pass --repo-derived and/or --commit-log.")
    save_state(repo_root, state)
    print_status(repo_root, state)


def cmd_status(repo_root: Path) -> None:
    print_status(repo_root, load_state(repo_root))


def cmd_clear(repo_root: Path) -> None:
    delete_state(repo_root)
    print_status(repo_root, None)


def main() -> int:
    args = parse_args()
    repo_root = git_root(Path(args.repo_root).resolve())
    try:
        if args.command == "bind":
            cmd_bind(args, repo_root)
        elif args.command == "mark-sync":
            cmd_mark_sync(args, repo_root)
        elif args.command == "status":
            cmd_status(repo_root)
        elif args.command == "clear":
            cmd_clear(repo_root)
        else:  # pragma: no cover
            raise ScriptError(f"Unsupported command: {args.command}")
        return 0
    except ScriptError as exc:
        stderr(f"[error] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

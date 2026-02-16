#!/usr/bin/env python3
"""
oracle.py

Build an "ask an expert" handoff bundle for an external assistant (ChatGPT Pro, etc.).

Outputs (by default):
  <repo_root>/.agents/oracle/<slug>/prompt.md
  <repo_root>/.agents/oracle/<slug>/context.zip  (includes selected repo files + MANIFEST.md)

Design goals:
- Deterministic & dependency-free (stdlib only)
- Conservative about secrets via default excludes (still review manually!)
- Small, focused context bundles
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import os
import subprocess
import sys
import textwrap
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Dict, Iterable, List, Optional, Tuple


# -------------------------
# Utilities
# -------------------------

def _eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


def _is_within(child: Path, root: Path) -> bool:
    try:
        child.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def _git_repo_root(cwd: Path) -> Optional[Path]:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(cwd),
            stderr=subprocess.DEVNULL,
        )
        p = Path(out.decode("utf-8").strip())
        return p if p.exists() else None
    except Exception:
        return None


def _slugify(text: str, max_len: int = 48) -> str:
    s = text.lower()
    s = "".join(ch if ch.isalnum() else "-" for ch in s)
    while "--" in s:
        s = s.replace("--", "-")
    s = s.strip("-")
    if not s:
        s = "oracle"
    if len(s) > max_len:
        s = s[:max_len].rstrip("-")
    ts = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{s}-{ts}"


def _read_lines(path: Path) -> List[str]:
    return path.read_text(encoding="utf-8").splitlines()


def _load_default_excludes(skill_dir: Path) -> List[str]:
    p = skill_dir / "assets" / "default_excludes.txt"
    if not p.exists():
        return []
    patterns: List[str] = []
    for line in _read_lines(p):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append(line)
    return patterns


def _match_any(rel_posix: str, patterns: List[str]) -> bool:
    """
    Match POSIX relative path against glob patterns using PurePosixPath.match(),
    which supports ** wildcards.

    Note: Path.match() matches from the start; patterns should generally begin with **/ for "any depth".
    """
    rp = PurePosixPath(rel_posix)
    for pat in patterns:
        try:
            if rp.match(pat):
                return True
        except Exception:
            # If a pattern is malformed, ignore it rather than crash.
            continue
    return False


def _dir_is_excluded(rel_posix_dir: str, patterns: List[str]) -> bool:
    # Use a dummy child file so patterns like **/node_modules/** match.
    dummy = rel_posix_dir.rstrip("/") + "/__DUMMY__"
    return _match_any(dummy, patterns) or _match_any(rel_posix_dir.rstrip("/"), patterns)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


_BINARY_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico",
    ".pdf",
    ".zip", ".tar", ".gz", ".tgz", ".7z", ".rar",
    ".mp4", ".mov", ".avi", ".mkv",
    ".mp3", ".wav", ".flac",
    ".woff", ".woff2", ".ttf", ".otf",
}


def _is_probably_text(path: Path) -> bool:
    if path.suffix.lower() in _BINARY_EXTS:
        return False
    try:
        data = path.read_bytes()
    except Exception:
        return False
    if b"\x00" in data[:4096]:
        return False
    # If it decodes as UTF-8 with few errors, treat as text.
    try:
        data.decode("utf-8")
        return True
    except Exception:
        return False


def _estimate_tokens_for_text(text: str) -> int:
    """
    Best-effort token estimate.
    Falls back to a simple heuristic (~4 chars per token for English/code mixed).
    """
    # Try tiktoken if available (optional).
    try:
        import tiktoken  # type: ignore
        enc = tiktoken.get_encoding("o200k_base")
        return len(enc.encode(text))
    except Exception:
        pass
    # Heuristic fallback
    return max(1, (len(text) + 3) // 4)


# -------------------------
# Data structures
# -------------------------

@dataclass
class Entry:
    path: Path
    reason: str


@dataclass
class FileItem:
    abs_path: Path
    rel_posix: str
    size_bytes: int
    sha256: str
    reasons: List[str]
    token_estimate: Optional[int] = None


# -------------------------
# Core logic
# -------------------------

def _parse_entry(raw: str) -> Entry:
    """
    Parse "PATH::REASON" (REASON may be omitted).
    """
    if "::" in raw:
        p, r = raw.split("::", 1)
        p = p.strip()
        r = r.strip()
    else:
        p, r = raw.strip(), ""
    if not p:
        raise ValueError(f"Invalid --entry (missing path): {raw!r}")
    return Entry(path=Path(p), reason=r or "Included for context")


def _load_entries(entries_raw: List[str], entries_from: Optional[Path]) -> List[Entry]:
    out: List[Entry] = []
    for e in entries_raw:
        out.append(_parse_entry(e))
    if entries_from:
        for line in _read_lines(entries_from):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            out.append(_parse_entry(line))
    return out


def _collect_files(
    repo_root: Path,
    entries: List[Entry],
    exclude_patterns: List[str],
    max_file_bytes: int,
) -> Dict[str, FileItem]:
    """
    Return mapping rel_posix -> FileItem
    """
    items: Dict[str, FileItem] = {}

    def add_file(abs_path: Path, rel_posix: str, reason: str) -> None:
        try:
            size = abs_path.stat().st_size
        except Exception:
            return
        if size > max_file_bytes:
            return
        if _match_any(rel_posix, exclude_patterns):
            return

        if rel_posix not in items:
            try:
                sha = _sha256_file(abs_path)
            except Exception:
                sha = ""
            items[rel_posix] = FileItem(
                abs_path=abs_path,
                rel_posix=rel_posix,
                size_bytes=size,
                sha256=sha,
                reasons=[reason],
            )
        else:
            if reason not in items[rel_posix].reasons:
                items[rel_posix].reasons.append(reason)

    repo_root_resolved = repo_root.resolve()

    for entry in entries:
        abs_entry = (repo_root / entry.path).resolve() if not entry.path.is_absolute() else entry.path.resolve()
        if not abs_entry.exists():
            raise FileNotFoundError(f"Entry not found: {entry.path}")
        if not _is_within(abs_entry, repo_root_resolved):
            raise ValueError(
                f"Entry path is outside repo root.\n"
                f"  entry: {abs_entry}\n"
                f"  repo:  {repo_root_resolved}"
            )

        if abs_entry.is_file():
            rel = abs_entry.relative_to(repo_root_resolved).as_posix()
            add_file(abs_entry, rel, entry.reason)
            continue

        # Directory walk with pruning
        for dirpath, dirnames, filenames in os.walk(abs_entry, topdown=True, followlinks=False):
            dir_abs = Path(dirpath)
            dir_rel = dir_abs.relative_to(repo_root_resolved).as_posix()

            # Prune excluded subdirectories early
            kept: List[str] = []
            for d in dirnames:
                d_abs = dir_abs / d
                d_rel = d_abs.relative_to(repo_root_resolved).as_posix()
                if _dir_is_excluded(d_rel, exclude_patterns):
                    continue
                kept.append(d)
            dirnames[:] = kept

            for fname in filenames:
                f_abs = dir_abs / fname
                if not f_abs.is_file():
                    continue
                f_rel = (PurePosixPath(dir_rel) / fname).as_posix()
                add_file(f_abs, f_rel, entry.reason)

    return items


def _render_manifest(
    repo_root: Path,
    slug: str,
    template: str,
    role: str,
    task: str,
    constraints: List[str],
    verify_cmds: List[str],
    entries: List[Entry],
    exclude_patterns: List[str],
    files: List[FileItem],
    token_total: Optional[int],
) -> str:
    now = _dt.datetime.now().isoformat(timespec="seconds")
    total_bytes = sum(f.size_bytes for f in files)

    def bullets(lines: List[str]) -> str:
        if not lines:
            return "- (none)"
        return "\n".join(f"- {x}" for x in lines)

    entries_md = "\n".join(
        f"- `{(repo_root / e.path).resolve().relative_to(repo_root.resolve()).as_posix()}` — {e.reason}"
        for e in entries
    ) if entries else "- (none)"

    # Keep file list reasonably small in MANIFEST; it can still be long, but it's useful.
    file_lines = []
    for f in files:
        reasons = "; ".join(f.reasons)
        sha_short = f.sha256[:12] if f.sha256 else ""
        tok = f.token_estimate
        tok_s = f"{tok}" if tok is not None else ""
        file_lines.append(f"| `{f.rel_posix}` | {f.size_bytes} | {tok_s} | `{sha_short}` | {reasons} |")

    manifest = f"""# Oracle Context Manifest

Generated: `{now}`
Repo root: `{repo_root.resolve()}`
Bundle slug: `{slug}`

## Task

{task}

## Expert role

Template: `{template}`
Role: **{role}**

## Constraints

{bullets(constraints)}

## How to verify locally

{bullets(verify_cmds)}

## Selected entries

{entries_md}

## Excludes applied

Default excludes come from `assets/default_excludes.txt` in this skill directory, plus any `--exclude` flags.

<details>
<summary>Exclude patterns</summary>

{chr(10).join(f"- `{p}`" for p in exclude_patterns) if exclude_patterns else "- (none)"}

</details>

## Bundle stats

- Files included: **{len(files)}**
- Total bytes (uncompressed): **{total_bytes}**
{"- Estimated tokens (best effort): **" + str(token_total) + "**" if token_total is not None else "- Estimated tokens: (not computed)"} 

## File inventory

| Path | Bytes | Tokens | SHA256 (12) | Why included |
|---|---:|---:|---|---|
{chr(10).join(file_lines) if file_lines else "| (none) | | | | |"}

## Rules for the expert assistant

- Start by reading this `MANIFEST.md`.
- Use only evidence supported by the uploaded files; do not invent missing code.
- Cite file paths for concrete claims.
- Do not ask questions; state assumptions and proceed.
- Keep output structured: Answer → Key Points → Next Steps → Risks.
"""
    return manifest


def _render_prompt(
    skill_dir: Path,
    template: str,
    role: str,
    task: str,
    constraints: List[str],
    verify_cmds: List[str],
) -> str:
    template_path = skill_dir / "assets" / "templates" / f"{template}.md"
    if template_path.exists():
        raw = template_path.read_text(encoding="utf-8")
    else:
        raw = (skill_dir / "assets" / "templates" / "general.md").read_text(encoding="utf-8")

    constraints_md = "- (none)" if not constraints else "\n".join(f"- {c}" for c in constraints)
    verify_md = "- (none)" if not verify_cmds else "\n".join(f"- {v}" for v in verify_cmds)

    return raw.format(
        ROLE=role,
        TASK=task.strip(),
        CONSTRAINTS=constraints_md,
        VERIFY=verify_md,
    )


_TEMPLATE_DEFAULT_ROLES = {
    "general": "expert assistant",
    "debugging": "senior engineer debugging with limited context",
    "code-review": "staff engineer reviewing for correctness and maintainability",
    "architecture": "principal engineer reviewing system design",
    "security": "security engineer threat-modeling",
    "performance": "performance engineer identifying bottlenecks",
    "data-sql": "database engineer reviewing correctness and performance",
    "ui-ux": "expert UI/UX designer reviewing visual and interaction design",
}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="oracle.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent(
            """\
            Build an "ask an expert" bundle (prompt.md + context.zip).

            Typical usage:
              python3 scripts/oracle.py \\
                --repo-root "$PWD" \\
                --task "Debug why tests fail" \\
                --template debugging \\
                --entry "src/my_feature::Main feature" \\
                --entry "README.md::Project overview"
            """
        ),
    )

    parser.add_argument("--repo-root", type=str, default=None, help="Repository root (defaults to git root if available, else CWD).")
    parser.add_argument("--slug", type=str, default=None, help="Output slug (defaults to slugified task + timestamp).")
    parser.add_argument("--out-dir", type=str, default=None, help="Output directory. Default: <repo_root>/.agents/oracle/<slug>/")

    parser.add_argument("--task", type=str, required=True, help="What you want the expert assistant to do.")
    parser.add_argument(
        "--template",
        type=str,
        default="general",
        choices=list(_TEMPLATE_DEFAULT_ROLES.keys()),
        help="Prompt template to use.",
    )
    parser.add_argument("--role", type=str, default=None, help="Override role string used in prompt.")
    parser.add_argument("--constraint", action="append", default=[], help="Constraint to include (repeatable).")
    parser.add_argument("--verify", action="append", default=[], help="Local verification command(s) (repeatable).")

    parser.add_argument("--entry", action="append", default=[], help="Include PATH::REASON (repeatable). PATH may be file or directory.")
    parser.add_argument("--entries-from", type=str, default=None, help="Read entries from file (one PATH::REASON per line).")

    parser.add_argument("--exclude", action="append", default=[], help="Extra exclude glob pattern(s) (repeatable).")
    parser.add_argument("--max-file-bytes", type=int, default=2_000_000, help="Skip files larger than this (default 2,000,000).")
    parser.add_argument("--estimate-tokens", action="store_true", help="Compute best-effort token estimate.")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be included; do not write output files.")

    args = parser.parse_args(argv)

    # Resolve paths
    cwd = Path.cwd()
    skill_dir = Path(__file__).resolve().parents[1]  # .../oracle/
    repo_root = Path(args.repo_root).resolve() if args.repo_root else (_git_repo_root(cwd) or cwd).resolve()

    entries_from = Path(args.entries_from).resolve() if args.entries_from else None
    entries = _load_entries(args.entry, entries_from)
    if not entries:
        _eprint("Error: no entries provided. Use --entry and/or --entries-from.")
        return 2

    slug = args.slug or _slugify(args.task)
    out_dir = Path(args.out_dir).resolve() if args.out_dir else (repo_root / ".agents" / "oracle" / slug)

    # Load excludes
    exclude_patterns = _load_default_excludes(skill_dir) + list(args.exclude or [])

    # Collect files
    try:
        files_map = _collect_files(
            repo_root=repo_root,
            entries=entries,
            exclude_patterns=exclude_patterns,
            max_file_bytes=args.max_file_bytes,
        )
    except Exception as e:
        _eprint(f"Error while collecting files: {e}")
        return 2

    files = [files_map[k] for k in sorted(files_map.keys())]

    # Token estimate
    token_total: Optional[int] = None
    if args.estimate_tokens:
        token_total = 0
        for f in files:
            if _is_probably_text(f.abs_path):
                try:
                    text = f.abs_path.read_text(encoding="utf-8", errors="replace")
                    tok = _estimate_tokens_for_text(text)
                except Exception:
                    tok = None
            else:
                tok = 0
            f.token_estimate = tok
            if tok is not None:
                token_total += tok

    role = args.role or _TEMPLATE_DEFAULT_ROLES.get(args.template, _TEMPLATE_DEFAULT_ROLES["general"])

    prompt_md = _render_prompt(
        skill_dir=skill_dir,
        template=args.template,
        role=role,
        task=args.task,
        constraints=list(args.constraint or []),
        verify_cmds=list(args.verify or []),
    )

    manifest_md = _render_manifest(
        repo_root=repo_root,
        slug=slug,
        template=args.template,
        role=role,
        task=args.task,
        constraints=list(args.constraint or []),
        verify_cmds=list(args.verify or []),
        entries=entries,
        exclude_patterns=exclude_patterns,
        files=files,
        token_total=token_total,
    )

    if args.dry_run:
        print(manifest_md)
        _eprint(f"\nDry run: would write {len(files)} files to:")
        _eprint(f"  {out_dir / 'context.zip'}")
        _eprint(f"  {out_dir / 'prompt.md'}")
        return 0

    # Write outputs
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "prompt.md").write_text(prompt_md, encoding="utf-8")
    (out_dir / "MANIFEST.md").write_text(manifest_md, encoding="utf-8")

    zip_path = out_dir / "context.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("MANIFEST.md", manifest_md)
        for f in files:
            # Ensure arcname is posix
            zf.write(str(f.abs_path), arcname=f.rel_posix)

    print(str(out_dir / "prompt.md"))
    print(str(zip_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Development helpers for running the ZenControl MCP server locally."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

WATCHED_FILENAMES = {".env", "pyproject.toml", "uv.lock"}
WATCHED_SUFFIXES = {".py"}
IGNORED_DIRNAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
}


def should_watch_path(path: Path) -> bool:
    """Return whether a path should trigger a server restart when changed."""
    if path.name in WATCHED_FILENAMES:
        return True
    return path.suffix in WATCHED_SUFFIXES


def build_snapshot(roots: list[Path]) -> dict[Path, int]:
    """Collect mtimes for watched files under the given roots."""
    snapshot: dict[Path, int] = {}

    for root in roots:
        if root.is_file():
            if should_watch_path(root):
                snapshot[root.resolve()] = root.stat().st_mtime_ns
            continue

        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [name for name in dirnames if name not in IGNORED_DIRNAMES]
            base_path = Path(dirpath)
            for filename in filenames:
                path = base_path / filename
                if should_watch_path(path):
                    snapshot[path.resolve()] = path.stat().st_mtime_ns

    return snapshot


def describe_changes(
    previous: dict[Path, int],
    current: dict[Path, int],
) -> list[str]:
    """Return human-readable descriptions of watched file changes."""
    changes: list[str] = []

    previous_paths = set(previous)
    current_paths = set(current)

    for path in sorted(previous_paths - current_paths):
        changes.append(f"deleted {path}")
    for path in sorted(current_paths - previous_paths):
        changes.append(f"added {path}")
    for path in sorted(previous_paths & current_paths):
        if previous[path] != current[path]:
            changes.append(f"modified {path}")

    return changes


def build_child_command(server_args: list[str]) -> list[str]:
    """Construct the child process command for the actual MCP server."""
    return [sys.executable, "-m", "zencontrol_mcp.server", *server_args]


def terminate_child(process: subprocess.Popen[bytes] | None) -> None:
    """Terminate the child process, escalating to kill if needed."""
    if process is None or process.poll() is not None:
        return

    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)


def main(argv: list[str] | None = None) -> int:
    """Watch the workspace and restart the stdio MCP server on changes."""
    parser = argparse.ArgumentParser(description="Watch and restart zencontrol-mcp")
    parser.add_argument(
        "--watch-path",
        action="append",
        default=[],
        help="Path to watch for changes. Can be passed multiple times.",
    )
    parser.add_argument(
        "--watch-interval",
        type=float,
        default=0.5,
        help="Polling interval in seconds (default: 0.5)",
    )
    args, server_args = parser.parse_known_args(argv)

    watch_roots = [Path(path).resolve() for path in args.watch_path] or [Path.cwd()]
    child_command = build_child_command(server_args)

    process: subprocess.Popen[bytes] | None = None
    stop_requested = False

    def request_stop(signum: int, _frame: object) -> None:
        nonlocal stop_requested
        stop_requested = True
        print(f"[zencontrol-mcp-watch] Received signal {signum}; stopping.", file=sys.stderr)

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    try:
        snapshot = build_snapshot(watch_roots)
        process = subprocess.Popen(child_command)

        while not stop_requested:
            time.sleep(args.watch_interval)

            current = build_snapshot(watch_roots)
            changes = describe_changes(snapshot, current)
            if changes:
                snapshot = current
                print(
                    "[zencontrol-mcp-watch] Restarting after changes: "
                    + ", ".join(changes[:5]),
                    file=sys.stderr,
                )
                terminate_child(process)
                process = subprocess.Popen(child_command)
                continue

            if process is not None and process.poll() is not None:
                print(
                    "[zencontrol-mcp-watch] Child exited; waiting for file changes before restart.",
                    file=sys.stderr,
                )
                process = None

        return 0
    finally:
        terminate_child(process)


if __name__ == "__main__":
    raise SystemExit(main())

"""Tests for the development watcher wrapper."""

from __future__ import annotations

from pathlib import Path

from zencontrol_cloud_mcp.dev import (
    build_child_command,
    build_snapshot,
    describe_changes,
    should_watch_path,
)


def test_should_watch_python_and_env_files(tmp_path: Path) -> None:
    python_file = tmp_path / "server.py"
    env_file = tmp_path / ".env"
    text_file = tmp_path / "notes.txt"

    assert should_watch_path(python_file) is True
    assert should_watch_path(env_file) is True
    assert should_watch_path(text_file) is False


def test_build_snapshot_ignores_virtualenv(tmp_path: Path) -> None:
    watched = tmp_path / "src" / "server.py"
    ignored = tmp_path / ".venv" / "lib.py"
    watched.parent.mkdir(parents=True)
    ignored.parent.mkdir(parents=True)
    watched.write_text("print('ok')\n")
    ignored.write_text("print('ignore')\n")

    snapshot = build_snapshot([tmp_path])

    assert watched.resolve() in snapshot
    assert ignored.resolve() not in snapshot


def test_describe_changes_reports_modified_added_and_deleted(tmp_path: Path) -> None:
    old_file = tmp_path / "old.py"
    changed_file = tmp_path / "changed.py"
    new_file = tmp_path / "new.py"

    previous = {
        old_file: 1,
        changed_file: 1,
    }
    current = {
        changed_file: 2,
        new_file: 1,
    }

    changes = describe_changes(previous, current)

    assert changes == [
        f"deleted {old_file}",
        f"added {new_file}",
        f"modified {changed_file}",
    ]


def test_build_child_command_targets_server_module() -> None:
    command = build_child_command(["--log-level", "DEBUG"])

    assert command[1:3] == ["-m", "zencontrol_cloud_mcp.server"]
    assert command[-2:] == ["--log-level", "DEBUG"]

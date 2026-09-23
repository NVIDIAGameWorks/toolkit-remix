"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
* SPDX-License-Identifier: Apache-2.0
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
* https://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
"""

__all__ = ["publish_manifest", "remove_manifest"]

import csv
import io
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

if sys.platform == "win32":
    import msvcrt


def publish_manifest(manifest: dict) -> Path | None:
    """Publish a Windows discovery manifest readable only by the current user."""
    if sys.platform != "win32":
        return None

    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise OSError("LOCALAPPDATA is required for MCP discovery publication")
    path = Path(local_app_data) / "NVIDIA" / "RTX Remix" / "mcp.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    user_sid = _current_user_sid()
    descriptor, temporary_name = tempfile.mkstemp(prefix="mcp-", suffix=".json", dir=path.parent)
    temporary_path = Path(temporary_name)
    os.close(descriptor)
    try:
        _restrict_access(temporary_path, user_sid)
        temporary_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        with _manifest_lock(path, user_sid):
            os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return path


def remove_manifest(path: Path, manifest: dict) -> None:
    """Remove a manifest only while it still describes this server instance."""
    if not path.exists():
        return
    with _manifest_lock(path, _current_user_sid()):
        try:
            published_manifest = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        if published_manifest == manifest:
            path.unlink(missing_ok=True)


def _current_user_sid() -> str:
    """Return the current Windows user's security identifier."""
    output = _run_windows_tool("whoami.exe", "/user", "/fo", "csv", "/nh")
    try:
        user_sid = next(csv.reader(io.StringIO(output)))[1]
    except (StopIteration, IndexError) as error:
        raise ValueError("whoami did not return a current-user SID") from error
    if not user_sid.startswith("S-1-"):
        raise ValueError("whoami returned an invalid current-user SID")
    return user_sid


def _restrict_access(path: Path, user_sid: str) -> None:
    """Replace inherited file permissions with current-user access."""
    _run_windows_tool("icacls.exe", str(path), "/inheritance:r", "/grant:r", f"*{user_sid}:(F)")


def _run_windows_tool(name: str, *arguments: str) -> str:
    """Run a Windows system tool without opening a console window."""
    system_root = os.environ.get("SYSTEMROOT")
    if not system_root:
        raise OSError("SystemRoot is required to secure MCP discovery files")
    result = subprocess.run(
        [str(Path(system_root) / "System32" / name), *arguments],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return result.stdout


@contextmanager
def _manifest_lock(path: Path, user_sid: str) -> Iterator[None]:
    """Serialize manifest replacement and ownership checks across processes."""
    lock_path = path.with_suffix(".lock")
    with lock_path.open("a+b") as lock_file:
        _restrict_access(lock_path, user_sid)
        if lock_file.tell() == 0:
            lock_file.write(b"\0")
            lock_file.flush()
        lock_file.seek(0)
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
        try:
            yield
        finally:
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)

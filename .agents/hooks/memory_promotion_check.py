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

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

CONFIG_FILE = Path(".agents/memory-promotion.local.json")
CACHE_FILE = Path(".agents/memory-promotion-cache.local.json")
ENV_DIRS = "AGENT_MEMORY_PROMOTION_DIRS"
MIN_TOTAL_LINES = 5
MAX_REPORTED_CHANGES = 20


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _configured_watches() -> list[tuple[str, Path]]:
    watches: list[tuple[str, Path]] = []

    config = _load_json(CONFIG_FILE)
    if isinstance(config, dict):
        for index, entry in enumerate(config.get("watch", [])):
            if isinstance(entry, str):
                watches.append((f"watch-{index + 1}", Path(entry).expanduser()))
            elif isinstance(entry, dict) and entry.get("path"):
                name = str(entry.get("name") or f"watch-{index + 1}")
                watches.append((name, Path(str(entry["path"])).expanduser()))

    for index, entry in enumerate(os.environ.get(ENV_DIRS, "").split(os.pathsep)):
        if entry.strip():
            watches.append((f"env-{index + 1}", Path(entry.strip()).expanduser()))

    return watches


def _hash_file(path: Path) -> tuple[str, int] | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None

    lines = data.decode("utf-8", errors="replace").splitlines()

    return hashlib.sha256(data).hexdigest(), len(lines)


def _snapshot(watches: list[tuple[str, Path]]) -> dict[str, dict[str, str | int]]:
    snapshot: dict[str, dict[str, str | int]] = {}
    for name, root in watches:
        if not root.exists() or not root.is_dir():
            continue

        resolved_root = root.resolve()
        root_entries: dict[str, dict[str, str | int]] = {}
        total_lines = 0
        for path in sorted(resolved_root.rglob("*.md")):
            if not path.is_file():
                continue

            hashed = _hash_file(path)
            if hashed is None:
                continue

            digest, line_count = hashed
            total_lines += line_count
            rel = path.relative_to(resolved_root).as_posix()
            root_entries[f"{name}/{rel}"] = {"sha256": digest, "lines": line_count}

        if total_lines >= MIN_TOTAL_LINES:
            snapshot.update(root_entries)

    return snapshot


def _write_cache(snapshot: dict[str, dict[str, str | int]]) -> None:
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    except OSError:
        pass


def _changed_paths(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    keys = sorted(set(old) | set(new))
    return [key for key in keys if old.get(key) != new.get(key)]


def main() -> int:
    try:
        if not sys.stdin.isatty():
            sys.stdin.read()
    except OSError:
        pass

    watches = _configured_watches()
    if not watches:
        return 0

    current = _snapshot(watches)
    if not current:
        return 0

    cached = _load_json(CACHE_FILE)
    if not isinstance(cached, dict):
        _write_cache(current)
        return 0

    changed = _changed_paths(cached, current)
    if not changed:
        return 0

    _write_cache(current)
    reported = "\n".join(f"  - {path}" for path in changed[:MAX_REPORTED_CHANGES])
    if len(changed) > MAX_REPORTED_CHANGES:
        reported += f"\n  ... and {len(changed) - MAX_REPORTED_CHANGES} more"

    print(
        "Local memory files changed since the last promotion review.\n\n"
        f"{reported}\n\n"
        "Review these changes for stable, confirmed project learnings. Promote durable knowledge to docs_dev/, "
        ".agents/rules/, or another canonical repo file before stopping. Do not promote session-specific notes.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

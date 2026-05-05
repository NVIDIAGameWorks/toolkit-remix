#!/usr/bin/env python3
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

Detect the base branch for the current git working tree.

Finds the remote branch with the fewest unique commits ahead of HEAD,
i.e., the branch this one was most likely forked from.

Usage as a standalone script::

    python tools/utils/detect_base_branch.py
    # prints: feature/comfy

Usage as an importable module::

    from detect_base_branch import detect_base_branch
    base = detect_base_branch()  # "feature/comfy"
"""

import subprocess
import sys

FALLBACK = "main"


def _git_stdout(args: list[str]) -> str | None:
    """Run a git command and return stripped stdout when it succeeds."""
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _branch_priority(name: str) -> int:
    """Return sort priority for likely base branch tie-breaks."""
    if name == "main":
        return 0
    if name.startswith("feature/"):
        return 1
    if name.startswith("release/"):
        return 2
    if name.startswith("dev/"):
        return 4
    return 3


def detect_base_branch(fallback: str = FALLBACK) -> str:
    """Return the closest likely base branch to HEAD by commit distance.

    For each likely base branch, counts commits unique to HEAD
    (``origin/X..HEAD``). The branch with the fewest unique commits is
    the most likely parent. Candidate branches are integration branches
    (``main``, ``feature/*``, ``release/*``) plus personal ``dev/*``
    branches owned by the current branch owner, when applicable. When
    multiple branches tie, integration branches are preferred over
    personal ``dev/*`` branches.

    Args:
        fallback: Branch name returned when detection fails.
    """
    current = _git_stdout(["rev-parse", "--abbrev-ref", "HEAD"])
    if current is None:
        return fallback

    ref_patterns = [
        "refs/remotes/origin/main",
        "refs/remotes/origin/feature",
        "refs/remotes/origin/release",
    ]
    current_parts = current.split("/")
    if len(current_parts) >= 2 and current_parts[0] == "dev":
        ref_patterns.append(f"refs/remotes/origin/dev/{current_parts[1]}")

    remotes = _git_stdout(["for-each-ref", "--format=%(refname:short)", *ref_patterns])
    if remotes is None:
        return fallback

    candidates: list[tuple[int, str]] = []

    for line in remotes.splitlines():
        branch = line.strip()
        if not branch.startswith("origin/"):
            continue
        short = branch.removeprefix("origin/")
        if short in (current, "HEAD"):
            continue

        dist = _git_stdout(["rev-list", "--count", f"{branch}..HEAD"])
        if dist is None:
            continue
        try:
            candidates.append((int(dist), short))
        except ValueError:
            continue

    if not candidates:
        return fallback

    min_distance = min(c[0] for c in candidates)
    tied = [short for dist, short in candidates if dist == min_distance]

    if len(tied) == 1:
        return tied[0]

    # Tiebreaker: prefer integration branches over personal dev branches
    tied.sort(key=_branch_priority)
    return tied[0]


if __name__ == "__main__":
    print(detect_base_branch())
    sys.exit(0)

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
* See the License for the specific governing permissions and
* limitations under the License.

Run ruff format using the same ruff installation as repo_lint.

Temporary: Remove this when repo_format is updated to support ruff.
"""

import os
import subprocess
import sys
from pathlib import Path

# Bootstrap repo tools
REPO_ROOT = os.path.join(os.path.dirname(os.path.realpath(__file__)), "../..")
sys.path.insert(0, os.path.join(REPO_ROOT, "tools", "repoman"))

import repoman  # noqa: E402

repoman.bootstrap()

# Now we can import from repo_lint
from omni.repo.lint import vendor_directory  # noqa: E402
from omni.repo.man.guidelines import is_windows  # noqa: E402


def _get_changed_python_files(target_branch="origin/main"):
    """Get Python files changed between merge-base and HEAD."""
    merge_base = subprocess.run(
        ["git", "merge-base", "HEAD", target_branch],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    if merge_base.returncode != 0:
        print("Warning: could not determine merge-base, falling back to HEAD~1")
        base = "HEAD~1"
    else:
        base = merge_base.stdout.strip()

    diff = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", base, "HEAD"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    files = [
        os.path.join(REPO_ROOT, f)
        for f in diff.stdout.strip().splitlines()
        if f.endswith(".py") and os.path.isfile(os.path.join(REPO_ROOT, f))
    ]
    print(f"Found {len(files)} changed Python file(s)")
    return files


def main():
    ruff_bin_path = str(Path(vendor_directory, "bin", "ruff"))
    if is_windows():
        ruff_bin_path = f"{ruff_bin_path}.exe"

    # Print ruff version for debugging
    version_result = subprocess.run([ruff_bin_path, "--version"], capture_output=True, text=True)
    print(f"Using: {version_result.stdout.strip()}")

    config_file = os.path.join(REPO_ROOT, ".ruff.toml")
    default_path = os.path.join(REPO_ROOT, "source", "extensions")

    # Build command
    args = [ruff_bin_path, "format"]
    if os.path.exists(config_file):
        args.extend(["--config", config_file])

    if "--help" in sys.argv or "-h" in sys.argv:
        print("Extra options (handled before ruff):")
        print("  --changed              Format only Python files changed in this MR")
        print("  --target-branch BRANCH Target branch for --changed (default: origin/main)")
        print("  --verify               Check formatting without modifying files")
        print()

    has_path = False
    use_changed = False
    target_branch = "origin/main"
    argv = sys.argv[1:]
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--verify":
            args.append("--check")
        elif arg == "--changed":
            use_changed = True
        elif arg == "--target-branch" and i + 1 < len(argv):
            i += 1
            target_branch = argv[i]
        elif not arg.startswith("-"):
            args.append(arg)
            has_path = True
        else:
            args.append(arg)
        i += 1

    if use_changed and not has_path:
        changed_files = _get_changed_python_files(target_branch)
        if not changed_files:
            print("No changed Python files found.")
            sys.exit(0)
        args.extend(changed_files)
        has_path = True

    if not has_path:
        args.append(default_path)

    print(f"Running: {' '.join(args)}")
    result = subprocess.run(args)
    sys.exit(result.returncode)


def _get_changed_python_files(target_branch="origin/main"):
    """Get Python files changed between merge-base and HEAD."""
    merge_base = subprocess.run(
        ["git", "merge-base", "HEAD", target_branch],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    if merge_base.returncode != 0:
        print("Warning: could not determine merge-base, falling back to HEAD~1")
        base = "HEAD~1"
    else:
        base = merge_base.stdout.strip()

    diff = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", base, "HEAD"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    files = [
        os.path.join(REPO_ROOT, f)
        for f in diff.stdout.strip().splitlines()
        if f.endswith(".py") and os.path.isfile(os.path.join(REPO_ROOT, f))
    ]
    print(f"Found {len(files)} changed Python file(s)")
    return files


if __name__ == "__main__":
    main()

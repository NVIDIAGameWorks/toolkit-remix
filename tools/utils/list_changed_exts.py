"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

Script to list changed extensions that need changelog updates
"""

import argparse
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"

try:
    from detect_base_branch import detect_base_branch
except ImportError:
    detect_base_branch = None


def ensure_project_root():
    """Change to project root directory to ensure git commands work correctly"""
    # Find the .git directory by walking up from the script location
    script_dir = Path(__file__).resolve().parent
    current_dir = script_dir

    while current_dir != current_dir.parent:
        if (current_dir / ".git").exists():
            os.chdir(current_dir)
            return current_dir
        current_dir = current_dir.parent

    raise RuntimeError("Could not find project root (no .git directory found)")


def get_git_shas(base_branch):
    """Get the top commit and merge base commit SHAs"""
    if base_branch.startswith("-"):
        raise ValueError(f"Invalid branch name: {base_branch}")
    top_commit = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode("utf-8").strip()
    merge_base = subprocess.check_output(["git", "merge-base", f"origin/{base_branch}", "HEAD"]).decode("utf-8").strip()
    return top_commit, merge_base


def get_all_changed_extensions(merge_base):
    """Get all extensions changed between merge-base and HEAD, categorized by change type"""
    try:
        changed_files = subprocess.check_output(["git", "diff", merge_base, "HEAD", "--name-status"], text=True).splitlines()

        # Track file changes per extension
        ext_changes = defaultdict(lambda: {"A": 0, "M": 0, "D": 0})

        for line in changed_files:
            parts = line.split(maxsplit=1)
            if len(parts) < 2:
                continue

            change_type, file_paths = parts[0], parts[1]

            # Handle renames: "R100 oldpath newpath" - we need to parse both paths
            if change_type.startswith("R"):
                # Split by tabs/multiple spaces to get old and new paths
                paths = file_paths.split("\t")
                if len(paths) == 2:
                    old_path, new_path = paths
                    # Mark old extension as having deletions
                    if old_path.startswith("source/extensions/"):
                        old_ext = old_path.split("/")[2]
                        ext_changes[old_ext]["D"] += 1
                    # Mark new extension as having additions
                    if new_path.startswith("source/extensions/"):
                        new_ext = new_path.split("/")[2]
                        ext_changes[new_ext]["A"] += 1
                continue

            # For non-renames, single file path
            if not file_paths.startswith("source/extensions/"):
                continue

            ext_name = file_paths.split("/")[2]

            if change_type == "A":
                ext_changes[ext_name]["A"] += 1
            elif change_type == "D":
                ext_changes[ext_name]["D"] += 1
            elif change_type == "M":
                ext_changes[ext_name]["M"] += 1
            else:
                # Handle C (copied), etc. as modifications
                ext_changes[ext_name]["M"] += 1

        # Categorize extensions based on their overall change pattern
        new_exts = set()
        modified_exts = set()
        deleted_exts = set()

        for ext_name, changes in ext_changes.items():
            has_adds = changes["A"] > 0
            has_mods = changes["M"] > 0
            has_dels = changes["D"] > 0

            # New: only additions
            if has_adds and not has_mods and not has_dels:
                new_exts.add(ext_name)
            # Deleted: only deletions
            elif has_dels and not has_adds and not has_mods:
                deleted_exts.add(ext_name)
            # Modified: anything else (mix of operations or just modifications)
            else:
                modified_exts.add(ext_name)

        return new_exts, modified_exts, deleted_exts, ext_changes
    except (OSError, subprocess.SubprocessError) as e:
        print(f"Error: Failed to get changed extensions: {e}", file=sys.stderr)
        return set(), set(), set(), {}


def get_extensions_with_uncommitted_changes():
    """Get extensions that have uncommitted changes to config/extension.toml or docs/CHANGELOG.md"""
    try:
        result = subprocess.check_output(["git", "status", "--porcelain"], text=True)

        # Parse lines like " M source/extensions/<ext-name>/config/extension.toml"
        # or " M source/extensions/<ext-name>/docs/CHANGELOG.md"
        modified_exts = set()
        for line in result.splitlines():
            if "source/extensions/" in line:
                # Extract extension name from path
                match = re.search(r"source/extensions/([^/]+)/", line)
                if match:
                    ext_name = match.group(1)
                    # Only include if it's a changelog or version file change
                    if "CHANGELOG.md" in line or "extension.toml" in line:
                        modified_exts.add(ext_name)

        return modified_exts
    except (OSError, subprocess.SubprocessError) as e:
        print(f"Warning: Failed to get git status: {e}", file=sys.stderr)
        return set()


def get_extensions_needing_changelog(top_commit, merge_base):
    """Run repo check_changelog once and parse output for failing extensions"""
    repo_cmd = "repo.bat" if IS_WINDOWS else "repo.sh"
    try:
        result = subprocess.run(
            [repo_cmd, "check_changelog", "-s", top_commit, "-t", merge_base],
            capture_output=True,
            text=True,
            timeout=60,
            shell=IS_WINDOWS,
            check=False,
        )

        # Parse output for lines like "Version has not been incremented for source/extensions/<ext-name>"
        pattern = r"Version has not been incremented for source/extensions/([^\s]+)"
        failed_exts = re.findall(pattern, result.stdout + result.stderr)

        # Also check for other error patterns like "Extension: source/extensions/<ext-name>. There was..."
        # Use [\w.]+ to capture extension names with dots like "lightspeed.common"
        # Match both forward and back slashes for cross-platform compatibility
        changelog_pattern = r"Extension: source[/\\]extensions[/\\]([\w.]+)\."
        changelog_errors = re.findall(changelog_pattern, result.stdout + result.stderr)

        # Combine and deduplicate
        all_failed = set(failed_exts + changelog_errors)

        return sorted(all_failed)

    except subprocess.TimeoutExpired:
        print("Error: Timeout running repo check_changelog", file=sys.stderr)
        return []
    except (OSError, subprocess.SubprocessError) as e:
        print(f"Error: Failed to run repo check_changelog: {e}", file=sys.stderr)
        return []


def main():
    parser = argparse.ArgumentParser(description="List changed extensions that need changelog updates")
    parser.add_argument(
        "--base",
        default=None,
        help="Base branch to compare against (default: auto-detect closest remote branch)",
    )
    args = parser.parse_args()

    # Ensure we're running from project root for git commands to work
    ensure_project_root()

    if args.base is None:
        if detect_base_branch is not None:
            args.base = detect_base_branch()
        else:
            args.base = "main"

    top_commit, merge_base = get_git_shas(args.base)

    # Get the true total of changed extensions from git diff, categorized
    added_exts, modified_exts, deleted_exts, _ = get_all_changed_extensions(merge_base)
    all_changed_exts = added_exts | modified_exts | deleted_exts

    # Get extensions that fail the changelog check
    exts_needing_changelog = get_extensions_needing_changelog(top_commit, merge_base)

    # Get extensions with uncommitted changes (work in progress)
    exts_with_uncommitted = get_extensions_with_uncommitted_changes()

    # Filter out extensions that already have uncommitted changes (already processed)
    exts_remaining = sorted(set(exts_needing_changelog) - exts_with_uncommitted)

    # Print summary
    total = len(all_changed_exts)

    print(
        f"{total} total extensions changed ({len(added_exts)} new, {len(modified_exts)} modified, {len(deleted_exts)} deleted)")
    print(
        f"{len(exts_needing_changelog)} need version bumps, {len(exts_with_uncommitted)} in progress, {len(exts_remaining)} remaining:")
    print()

    for ext in exts_remaining:
        print(ext)


if __name__ == "__main__":
    main()

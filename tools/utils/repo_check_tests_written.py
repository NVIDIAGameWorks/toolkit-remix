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

import fnmatch
import os
import subprocess
import sys
from pathlib import Path

# Exit code used when at least one extension changed its source without changing its tests. The CI job is marked
# `allow_failure: true`, so this surfaces as a pipeline warning rather than a merge blocker.
MISSING_TESTS_EXIT_CODE = 1


def get_changed_files(source_hash: str, original_hash: str) -> list[tuple[str, str]]:
    """
    Find all the files that changed between two commits.

    Args:
        source_hash: The source commit hash
        original_hash: The original commit hash

    Returns:
        A list of change type + file name tuples.
    """
    diff_output = subprocess.check_output(
        # Use --no-pager to avoid paging the output
        # Use --name-status to get the change type alongside each file name
        ["git", "--no-pager", "diff", "--name-status", f"{original_hash}..{source_hash}"],
        text=True,
        encoding="utf-8",
    )
    return parse_name_status(diff_output)


def parse_name_status(diff_output: str) -> list[tuple[str, str]]:
    """
    Parse the output of `git diff --name-status` into change type + file name tuples.

    A rename is reported by git as a single `R<score>` line holding both the old and the new path. It is split into a
    deletion of the old path and an addition of the new one so that moving a source file between extensions counts
    against the extension that received it.

    A copy is reported the same way as a `C<score>` line and is split identically. The old path becomes a deletion,
    which is discarded from the accounting because the original file is untouched by a copy, and only the new path is
    counted against the extension that received it.

    Args:
        diff_output: The raw output of `git diff --name-status`

    Returns:
        A list of change type + file name tuples.
    """
    changed_files = []
    for line in diff_output.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        change_type = parts[0][0]
        if change_type in ("R", "C") and len(parts) == 3:
            changed_files.append(("D", parts[1]))
            changed_files.append(("A", parts[2]))
            continue
        if len(parts) < 2:
            continue
        changed_files.append((change_type, parts[1]))
    return changed_files


def is_excluded(file_path: str, exclude_patterns: list[str]) -> bool:
    """
    Check whether a file is covered by one of the exclusion patterns.

    Patterns use `fnmatch` syntax, where `*` also matches path separators. A pattern of `source/pythonapps/*`
    therefore excludes the whole tree below it.

    Args:
        file_path: The posix path of the file to test
        exclude_patterns: The patterns that mark a file as excluded

    Returns:
        True when the file matches any exclusion pattern.
    """
    return any(fnmatch.fnmatch(file_path, pattern) for pattern in exclude_patterns)


def group_changes_by_extension(
    changed_files: list[tuple[str, str]],
    extension_path_prefix: str,
    exclude_patterns: list[str],
    test_dir_name: str,
) -> dict[str, dict[str, list[str]]]:
    """
    Group the changed Python files per extension, split into source files and test files.

    Deletions are dropped before grouping. Removing code does not create an obligation to write tests, and an
    extension whose only changes are deletions must not be reported.

    Args:
        changed_files: The change type + file name tuples to group
        extension_path_prefix: The common path holding every extension
        exclude_patterns: The patterns marking files that are not subject to the check
        test_dir_name: The name of the directory holding an extension's tests

    Returns:
        A mapping of extension name to its changed `source` and `tests` files.
    """
    prefix = Path(extension_path_prefix).as_posix().rstrip("/") + "/"
    grouped: dict[str, dict[str, list[str]]] = {}

    for change_type, file_path in changed_files:
        posix_path = Path(file_path).as_posix()
        if change_type == "D":
            continue
        if not posix_path.startswith(prefix) or not posix_path.endswith(".py"):
            continue
        if is_excluded(posix_path, exclude_patterns):
            continue

        relative_parts = Path(posix_path.removeprefix(prefix)).parts
        # A file directly under the prefix does not belong to an extension.
        if len(relative_parts) < 2:
            continue

        extension_name = relative_parts[0]
        changes = grouped.setdefault(extension_name, {"source": [], "tests": []})
        category = "tests" if test_dir_name in relative_parts[1:] else "source"
        changes[category].append(posix_path)

    return grouped


def find_extensions_missing_tests(grouped_changes: dict[str, dict[str, list[str]]]) -> list[str]:
    """
    Find the extensions that changed source files without changing any test file.

    Args:
        grouped_changes: The per-extension changes produced by `group_changes_by_extension`

    Returns:
        A sorted list of extension names that are missing test changes.
    """
    return sorted(name for name, changes in grouped_changes.items() if changes["source"] and not changes["tests"])


def format_report(
    missing_extensions: list[str],
    grouped_changes: dict[str, dict[str, list[str]]],
    test_dir_name: str,
) -> str:
    """
    Build the markdown report posted to the merge request.

    Args:
        missing_extensions: The extension names that are missing test changes
        grouped_changes: The per-extension changes produced by `group_changes_by_extension`
        test_dir_name: The name of the directory holding an extension's tests

    Returns:
        The markdown body of the report.
    """
    lines = [
        ":warning: **Source changed without test changes**",
        "",
        f"These extensions have modified Python source files but no modified files under their `{test_dir_name}/` "
        "directory:",
        "",
    ]
    for extension_name in missing_extensions:
        source_files = grouped_changes[extension_name]["source"]
        lines.append(f"- **{extension_name}** ({len(source_files)} changed source file(s))")
        for source_file in sorted(source_files):
            lines.append(f"  - `{source_file}`")
    lines += [
        "",
        "This is a warning, not a merge blocker. Add or update the matching tests, or apply the "
        "`no-tests-needed` label when tests genuinely do not apply to this change.",
    ]
    return "\n".join(lines)


def has_skip_label(skip_label: str, merge_request_labels: str) -> bool:
    """
    Check whether the merge request carries the opt-out label.

    Args:
        skip_label: The label that disables the check
        merge_request_labels: The comma separated labels of the merge request

    Returns:
        True when the opt-out label is present.
    """
    if not skip_label or not merge_request_labels:
        return False
    return skip_label in [label.strip() for label in merge_request_labels.split(",")]


def setup_repo_tool(parser, _):
    parser.prog = "check_tests_written"
    parser.description = "Warn when an extension's Python source changed but none of its test files did"
    parser.add_argument(
        "-s",
        "--source-hash",
        dest="source_hash",
        required=False,
        help="Override the source commit to compare from",
    )
    parser.add_argument(
        "-t",
        "--original-hash",
        dest="original_hash",
        required=False,
        help="Override the original commit to compare to",
    )
    parser.add_argument(
        "-r",
        "--report-file",
        dest="report_file",
        required=False,
        help="Path of the markdown report to write when extensions are missing test changes",
    )

    def run_repo_tool(options, config):
        settings = config["repo_check_tests_written"]
        extension_path_prefix = settings["extension_path_prefix"]
        test_dir_name = settings["test_dir_name"]
        skip_label = settings["skip_label"]
        exclude_patterns = settings["files"]["exclude"]

        source_hash = options.source_hash or settings["source_commit"]
        original_hash = options.original_hash or settings["original_commit"]

        if has_skip_label(skip_label, os.environ.get("CI_MERGE_REQUEST_LABELS", "")):
            print(f"The '{skip_label}' label is set. Skipping the test check.")
            return

        print("Comparing:", original_hash, "->", source_hash)

        changed_files = get_changed_files(source_hash, original_hash)
        grouped_changes = group_changes_by_extension(
            changed_files, extension_path_prefix, exclude_patterns, test_dir_name
        )
        missing_extensions = find_extensions_missing_tests(grouped_changes)

        if not missing_extensions:
            print("Success! Every extension with source changes also has test changes.")
            return

        report = format_report(missing_extensions, grouped_changes, test_dir_name)
        print(report)
        if options.report_file:
            Path(options.report_file).write_text(report, encoding="utf-8")

        sys.exit(MISSING_TESTS_EXIT_CODE)

    return run_repo_tool

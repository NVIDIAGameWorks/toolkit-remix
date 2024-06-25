"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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
import re
import subprocess
import sys
from difflib import SequenceMatcher


def get_diff_lines(file_path: str, source_hash: str, target_hash: str):
    """
    Retrieve the differences between the current commit and the given source_hash for a specified file.

    This function executes a git command to fetch the diff output between the current branch and the main branch
    for the given file path. It returns the diff as a list of lines, which can be processed further.

    Args:
        file_path: The path to the file for which the diff is required.
        source_hash: The source commit hash to compare the current file against
        target_hash: The target commit hash to compare the current file against

    Returns:
        A list of strings where each string is a line from the git diff output.
    """
    try:
        # Get the number of lines in the CHANGELOG file to have a complete diff of the file
        with open(file_path, 'r') as file_content:
            lines = len(file_content.readlines())
        diff_output = subprocess.check_output(
            # Use --no-page to avoid paging the output
            # Use --unified={lines} to avoid trimming the diff context
            ["git", "--no-pager", "diff", f"--unified={lines}", f"{target_hash}..{source_hash}", '--', file_path],
            text=True
        )
    except TypeError:
        return []
    return diff_output.splitlines()


def check_new_entries_in_unreleased(
    diff_lines: list[str], section_header: str, section_pattern: str, similarity_threshold: float
):
    """
    Check if there are new entries added under a specific section in the diff lines.

    This function iterates through the lines of a diff to determine if there are any new lines added under a specified
    section (e.g., '## [Unreleased]'). It uses the section header to locate the start of the section and a regex pattern
    to identify the end or another section start, ensuring that only additions within the desired section are considered

    Args:
        diff_lines: A list of strings representing lines from a git diff output.
        section_header: The header marking the start of the section to check for additions (e.g., '[Unreleased]').
        section_pattern: A regex pattern to identify the start of a section (e.g., '^## ').
        similarity_threshold: The similarity threshold to use when checking for modified lines.

    Returns:
        True if there are new additions under the specified section, False otherwise.
    """

    in_unreleased_section = False
    added_lines = set()
    removed_lines = set()

    for line in diff_lines:
        if section_header in line:
            in_unreleased_section = True
        # Lines might contain additional spaces from the git diff, so we need to strip them
        elif re.match(section_pattern, line.strip()) and section_header not in line:
            # Do not break, if we change a large block the unreleased section will appear twice
            in_unreleased_section = False

        # Check for added lines, ignoring diff metadata lines
        if in_unreleased_section and line.startswith('+') and not line.startswith('+++'):
            added_lines.add(line[1:].strip())
        # Check for removed lines, ignoring diff metadata lines
        elif in_unreleased_section and line.startswith('-') and not line.startswith('---'):
            removed_lines.add(line[1:].strip())

    # Check each added line against all removed lines
    for added_line in added_lines:
        is_new = True
        for removed_line in removed_lines:
            # An added line is only added if there is no removed line that's similar to it, otherwise it's modified
            similarity = SequenceMatcher(None, added_line, removed_line).ratio()
            if similarity > similarity_threshold:
                is_new = False  # Line is similar to a removed line, not new
                break
        if is_new:
            return True  # Found at least one genuinely new line

    return False


def setup_repo_tool(parser, _):
    parser.prog = "check_changelog"
    parser.description = "Verify that the CHANGELOG.md file has had its '## [Unreleased]' section modified"
    parser.add_argument(
        "-s",
        "--source-hash",
        dest="source_hash",
        required=False,
        help="Override the source commit to compare the changelog file from",
    )
    parser.add_argument(
        "-t",
        "--target-hash",
        dest="target_hash",
        required=False,
        help="Override the target commit to compare the changelog file to",
    )

    def run_repo_tool(options, config):
        settings = config["repo_check_changelog"]
        file_name = settings["file_name"]
        section_pattern = settings["section_pattern"]
        similarity_threshold = settings["similarity_threshold"]
        section_header = settings["section_header"]
        source_commit = settings["source_commit"]
        target_commit = settings["target_commit"]

        source_hash = options.source_hash if options.source_hash else source_commit
        target_hash = options.target_hash if options.target_hash else target_commit

        print("Comparing:", source_hash, "->", target_hash)

        diff_lines = get_diff_lines(file_name, source_hash, target_hash)
        if not check_new_entries_in_unreleased(diff_lines, section_header, section_pattern, similarity_threshold):
            print(f"No new entries added to the '{section_header}' section in {file_name}")
            sys.exit(1)

        print("Success!")

    return run_repo_tool

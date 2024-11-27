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
import difflib
import re
import subprocess
import sys
import toml
from pathlib import Path


def get_changed_files(source_hash: str, original_hash: str) -> list[tuple[str, str]]:
    """
    Find all the files that have changed since the last commit.

    Args:
        source_hash: The source commit hash
        original_hash: The original commit hash

    Returns:
        A list of change type + file names that have changed since the last commit.
    """
    changed_files = subprocess.check_output(
        # Use --no-page to avoid paging the output
        # Use --name-only to only return the file names, not the changed diff
        ["git", "--no-pager", "diff", "--name-status", f"{original_hash}..{source_hash}"],
        text=True
    )
    return [(file[0], file[2:]) for file in changed_files.splitlines()]


def find_changed_extensions(changed_files: list[tuple[str, str]], prefix_path: Path) -> list[Path]:
    """
    Given the list of changed files, find all the extensions that have changes in them.

    Args:
        changed_files: List of changed files
        prefix_path: The common path for all extensions

    Returns:
        A list of the extensions that contain changes.
    """
    str_prefix = prefix_path.as_posix()
    # ignore extensions that were deleted. We don't need to check anything here.
    changed_extension_files = [
        Path(chg) for change_type, chg in changed_files if chg.startswith(str_prefix) and change_type != "D"
    ]
    rel_paths = [chg.relative_to(prefix_path) for chg in changed_extension_files]
    ext_name_parts = set([chg.parts[0] for chg in rel_paths])
    return [prefix_path / ext_name for ext_name in ext_name_parts]


def validate_extension_changes(
    source_hash: str,
    original_hash: str,
    changed_extension: Path,
    extension_changelog_file: str,
    extension_config_file: str,
) -> str | None:
    """
    Given a changed extension's path, check that the required changes have been made.
        - that the version in `config/extension.toml` has been incremented
        - that at least one line has been added to the `docs/CHANGELOG.md` file

    Args:
        source_hash: The source commit hash
        original_hash: The original commit hash
        changed_extension: the path of the extension to verify
        extension_changelog_file: The path off the main extension's path for the changelog file
        extension_config_file: The path off the main extension's path for the config file

    Returns:
        A string describing the error. If no errors are found, None is returned.
    """

    def get_source(file_path, hashval):
        """Use `git show` to get the version of a file at the given commit"""
        try:
            return subprocess.check_output(["git", "show", f"{hashval}:{file_path.as_posix()}"], text=True)
        except subprocess.CalledProcessError:
            # File does not exist at that commit; return empty string
            return ""

    def compare_semantic_version(first_version: str, second_version: str) -> int:
        """
        Compare two semantic version strings.

        Returns:
             1 if the first version is greater than the second version
             0 if the first version is equal to the second version
             -1 if the first version is less than the second version

        Raises:
            ValueError: If either version is not in 'x.y.z' format
        """
        try:
            major1, minor1, patch1 = first_version.split(".")
            major1, minor1, patch1 = int(major1), int(minor1), int(patch1)
        except ValueError:
            raise ValueError(f"Invalid semantic version string: {first_version}") from None
        try:
            major2, minor2, patch2 = second_version.split(".")
            major2, minor2, patch2 = int(major2), int(minor2), int(patch2)
        except ValueError:
            raise ValueError(f"Invalid semantic version string: {second_version}") from None
        if major1 == major2:
            if minor1 == minor2:
                return 1 if patch1 > patch2 else -1 if patch1 < patch2 else 0
            else:
                return 1 if minor1 > minor2 else -1 if minor1 < minor2 else 0
        else:
            return 1 if major1 > major2 else -1 if major1 < major2 else 0

    # Verify that the version in the source is newer than the original
    config_file = changed_extension / extension_config_file
    source_text = get_source(config_file, source_hash)
    original_text = get_source(config_file, original_hash)
    try:
        source_parsed = toml.loads(source_text)
    except toml.TomlDecodeError:
        print(f"Error parsing {config_file}")
        raise
    try:
        original_parsed = toml.loads(original_text)
    except toml.TomlDecodeError:
        # we can't load the original, so we skip the check here
        return ""
    source_version = source_parsed.get("package", {}).get("version")
    original_version = original_parsed.get("package", {}).get("version")
    if not source_version:
        return f"Extension: {changed_extension}. No version found in current config file"
    if original_version:
        # Compare with the newer source
        version_compare = compare_semantic_version(source_version, original_version)
        if version_compare != 1:
            if version_compare == 0:
                return f"Version has not been incremented for {changed_extension.as_posix()}"
            return f"Version is older than previous for {changed_extension.as_posix()}"

    # The version has been properly updated. Make sure that it is documented.
    # The format we need is a line with `## [x.y.z]`, where `x.y.z` is the original version
    log_file = changed_extension / extension_changelog_file
    diff_lines = get_diff_lines(str(log_file), source_hash, original_hash)
    added = [ln.lstrip("+") for ln in diff_lines if ln.startswith("+")]

    # There needs to be one line with the new version header, and at least one valid comment line for the change
    version_found = False
    descrip_found = False
    required_version_line = f"## [{source_version}]"
    for ln in added:
        ln = ln.strip()
        if ln.startswith(required_version_line):
            version_found = True
        elif ln.startswith("- "):
            # Change descriptions in markdown begin with a dash ("- ").
            descrip_found = True
    if not version_found:
        return f"Extension: {changed_extension}. There was no entry in {log_file} for version {source_version}"
    if not descrip_found:
        return f"Extension: {changed_extension}. There was no change description in {log_file} for version {source_version}"

    # All is well; return
    return ""


def get_diff_lines(file_path: str, source_hash: str, original_hash: str):
    """
    Retrieve the differences between the current commit and the given source_hash for a specified file.

    This function executes a git command to fetch the diff output between the current branch and the main branch
    for the given file path. It returns the diff as a list of lines, which can be processed further.

    Args:
        file_path: The path to the file for which the diff is required.
        source_hash: The source commit hash to compare the current file against
        original_hash: The original commit hash to compare the current file against

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
            ["git", "--no-pager", "diff", f"--unified={lines}", f"{original_hash}..{source_hash}", '--', file_path],
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
            similarity = difflib.SequenceMatcher(None, added_line, removed_line).ratio()
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
        "--original-hash",
        dest="original_hash",
        required=False,
        help="Override the original commit to compare the changelog file to",
    )

    def run_repo_tool(options, config):
        settings = config["repo_check_changelog"]
        file_name = settings["file_name"]
        section_pattern = settings["section_pattern"]
        similarity_threshold = settings["similarity_threshold"]
        section_header = settings["section_header"]
        source_commit = settings["source_commit"]
        original_commit = settings["original_commit"]
        extension_path_prefix = settings["extension_path_prefix"]
        extension_changelog_file = settings["extension_changelog_file"]
        extension_config_file = settings["extension_config_file"]

        source_hash = options.source_hash if options.source_hash else source_commit
        original_hash = options.original_hash if options.original_hash else original_commit

        print("Comparing:", source_hash, "->", original_hash)

        # Get list of all changed files
        # Find all the .py files under 'source/extensions`
        # For each:
            # Find the base path of the extension: 'source/extensions/([^/]+)/.*'
            # Verify that there is also change to `config/extension.toml' and 'docs/CHANGELOG.md'
            # Analyze the extension.toml file to ensure that the version line has been incremented
        changed_files = get_changed_files(source_hash, original_hash)
        prefix_path = Path(extension_path_prefix)
        changed_extensions = find_changed_extensions(changed_files, prefix_path)
        # Validate that all changed extensions have an incremented version as well as a CHANGELOG update
        failures = []
        for changed_extension in changed_extensions:
            failures.append(
                validate_extension_changes(
                    source_hash, original_hash, changed_extension, extension_changelog_file, extension_config_file
                )
            )
        # If there are any non-empty failures, fail.
        if any(failures):
            failures_string = ""
            for f in failures:
                if f:
                    failures_string += f + "\n"
            print(f"The following extensions were not updated correctly:\n{failures_string}")
            sys.exit(1)

        # Now validate the overall CHANGELOG.md
        diff_lines = get_diff_lines(file_name, source_hash, original_hash)
        if not check_new_entries_in_unreleased(diff_lines, section_header, section_pattern, similarity_threshold):
            print(f"No new entries added to the '{section_header}' section in {file_name}")
            sys.exit(1)

        print("Success!")

    return run_repo_tool

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
import subprocess
from pathlib import Path
from omni.repo.kit_tools.bump import bump_extension, get_all_extensions

from InquirerPy import inquirer
from InquirerPy.base.control import Choice


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
    return [ext_name for ext_name in ext_name_parts]


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


def setup_repo_tool(parser, _):
    parser.prog = "bump_changed_extensions"
    parser.description = "Run repo bump for all changed extensions"
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
        settings = config["repo_bump_changed_extensions"]
        source_commit = settings["source_commit"]
        original_commit = settings["original_commit"]
        extension_path_prefix = settings["extension_path_prefix"]
        default_text = settings["default_changelog_text"]

        source_hash = options.source_hash if options.source_hash else source_commit
        original_hash = options.original_hash if options.original_hash else original_commit

        print("Comparing:", source_hash, "->", original_hash)

        # Get list of all changed files
        # Find all the .py files under 'source/extensions`
        # For each:
            # Find the base path of the extension: 'source/extensions/([^/]+)/.*'
            # Verify that there is also change to `config/extension.toml' and 'docs/CHANGELOG.md'
        changed_files = get_changed_files(source_hash, original_hash)
        prefix_path = Path(extension_path_prefix)
        changed_extensions = set(find_changed_extensions(changed_files, prefix_path))

        extension_folders = [prefix_path]
        extensions = [e for e in get_all_extensions(extension_folders) if e.name in changed_extensions]
        if not extensions:
            print("No extensions or apps changed. Exiting.")
            return

        # Pick version component to bump
        component = inquirer.select(
            message="Which version component (X) to bump?",
            choices=[
                Choice(value="prerelease", name="Prerelease (1.0.0-X)"),
                Choice(value="patch", name="Patch (1.0.X)"),
                Choice(value="minor", name="Minor (1.X.0)"),
                Choice(value="major", name="Major (X.0.0)"),
            ],
            default=None,
        ).execute()

        # Ask for changelog
        changelog = inquirer.text(message="Changelog (optional):", default=default_text, multiline=True).execute()

        print(f"Selected to bump the {component} of following extensions:")
        for ext in extensions:
            print(f"  {ext.ext_id:<40} (path: {ext.path})")
        if changelog:
            print("Changelog:")
            print(changelog)

        # Confirm
        proceed = inquirer.confirm(message="Proceed?", default=True).execute()
        if not proceed:
            return

        # Let's go!
        print("\nApply changes...")
        for ext in extensions:
            bump_extension(ext, component, changelog)

        print("Done!")

    return run_repo_tool

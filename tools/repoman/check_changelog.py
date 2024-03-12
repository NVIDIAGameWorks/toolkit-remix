"""
* Copyright (c) 2024, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""

import os
import re
import subprocess
import sys
from operator import or_


def get_unreleased_length(txt, section_header, section_pattern, require=True):
    """
    Find the '[Unreleased]' section of the changelog, and return the number of non-blank lines in it.

    We want to always require that section in any commit, but it may be absent in the branch we are merging into.
    """
    split = [section for section in re.split(section_pattern, txt) if section.startswith(section_header)]
    if not split:
        if require:
            sys.exit(f"No '{section_header}' section was found")
        else:
            return 0
    non_blanks = [ln for ln in split[0].splitlines() if ln]
    return len(non_blanks)


def validate_change(orig, curr, section_header, section_pattern):
    """
    Validate that the number of lines in the unreleased section has changed.

    On most commits we will require that at least one line be added to this section. On releases, the lines will be
    moved to a release section, and this section will remain but be empty.
    """
    unrel_orig = get_unreleased_length(orig, section_header, section_pattern, require=False)
    unrel_curr = get_unreleased_length(curr, section_header, section_pattern, require=True)
    return unrel_curr != unrel_orig


def setup_repo_tool(parser, config):
    parser.prog = "check_changelog"
    parser.description = "Verify that the CHANGELOG.md file has had its '## [Unreleased]' section modified"

    def run_repo_tool(options, config):
        main_sha = os.environ.get("CI_MERGE_REQUEST_DIFF_BASE_SHA")
        commit_sha = os.environ.get("CI_COMMIT_SHA")
        settings = config["repo_check_changelog"]
        file_name = settings["file_name"]
        section_header = settings["section_header"]
        section_pattern = settings["section_pattern"]
        orig_proc = subprocess.run(["git", "show", f"{main_sha}:{file_name}"], capture_output=True)
        orig_text = orig_proc.stdout.decode()
        curr_proc = subprocess.run(["git", "show", f"{commit_sha}:{file_name}"], capture_output=True)
        curr_text = curr_proc.stdout.decode()

        if orig_text == curr_text:
            sys.exit(f"{file_name} was not updated")
        if not validate_change(orig_text, curr_text, section_header, section_pattern):
            sys.exit(f"No lines were added or removed from the '{section_header}' section of '{file_name}'.")

        print("Success!")

    return run_repo_tool

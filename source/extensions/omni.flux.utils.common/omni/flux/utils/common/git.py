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

__all__ = ["get_git_hash", "get_git_branch"]

import subprocess


def get_git_hash(revision: str = "HEAD", hash_length: int = 8) -> str | None:
    """
    Get the current git hash.

    Returns:
        The git hash, or None if the git hash cannot be found.
    """
    git_output = _execute_git(["rev-parse", f"--short={hash_length}", revision])
    if git_output["returncode"] != 0:
        return None
    return git_output["stdout"]


def get_git_branch() -> str | None:
    """
    Get the current git branch.

    Returns:
        The git branch, or None if the git branch cannot be found.
    """
    git_output = _execute_git(["rev-parse", "--abbrev-ref", "HEAD"])
    if git_output["returncode"] != 0:
        return None
    return git_output["stdout"]


def _execute_git(args: list[str], timeout: int = 5) -> dict:
    """
    Execute a git command.

    Args:
        args: List of git command arguments (without the 'git' prefix)

    Returns:
        Dictionary containing:
        - returncode: Exit code of the git command (0 for success)
        - stdout: Standard output from the command
        - stderr: Standard error from the command (optional)
    """
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        )
        return {"returncode": result.returncode, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
    except FileNotFoundError:
        # Git is not installed
        return {"returncode": 1, "stdout": "", "stderr": "git command not found"}
    except subprocess.TimeoutExpired:
        # Command timed out
        return {"returncode": 1, "stdout": "", "stderr": "git command timed out"}
    except Exception as e:  # noqa PLW0718
        # Any other error
        return {"returncode": 1, "stdout": "", "stderr": str(e)}

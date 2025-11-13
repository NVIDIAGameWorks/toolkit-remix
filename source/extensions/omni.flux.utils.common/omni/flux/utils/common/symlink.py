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
import sys
from pathlib import Path
from typing import Tuple

from .uac import UnsupportedPlatformError as _UnsupportedPlatformError
from .uac import is_admin as _is_admin
from .uac import sudo as _sudo


def is_broken_symlink(path_obj: Path) -> bool:
    """Check if a symlink is broken."""
    if not path_obj.is_symlink():
        raise ValueError(f"Path '{path_obj}' is not a symlink")

    # Check if the symlink is broken by checking if the symlink exists and the target does not
    try:
        if path_obj.readlink() and not path_obj.exists():
            return True
    except OSError:
        # Some platforms may raise exceptions here if the symlink is invalid or if the filesystem does not
        # support reading symlinks. For example, on Windows, reading a broken symlink or a file with
        # insufficient permissions may throw OSError.
        return True

    return False


def get_path_or_symlink(path_obj: Path) -> Path | None:
    """
    Get a path object for path or symlink.

    If the path does not exist or the symlink is broken, return None.
    """
    if path_obj.is_symlink() and is_broken_symlink(path_obj):
        return None
    if path_obj.exists():
        return path_obj
    return None


def create_folder_symlinks(links_targets: list[Tuple[str, str]], create_junction: bool = False):
    """
    Create symlink(s). If create_junction is False and the user doesn't have the permission to create symlink(s),
    it will prompt the Windows UAC for Windows user.

    Args:
        links_targets: list of links and targets folders to use
        create_junction: for Windows, create a junction instead
    """

    # Unlink broken symlinks
    for link, _ in links_targets:
        link_obj = Path(link)
        if link_obj.exists() and link_obj.is_symlink() and is_broken_symlink(link_obj):
            link_obj.unlink()

    def _generate_cmd(symlink_cmd, symlink_type, reverse: bool = False):
        _cmd = []
        for i, (link, target) in enumerate(links_targets):
            if i != 0:
                _cmd.append("&&")
            if reverse:
                _cmd.extend([symlink_cmd, symlink_type, f'"{target}"', f'"{link}"'])
            else:
                _cmd.extend([symlink_cmd, symlink_type, f'"{link}"', f'"{target}"'])
        return _cmd

    match sys.platform:
        case "win32":
            if create_junction:
                cmd = _generate_cmd("mklink", "/J")
                subprocess.check_call(" ".join(cmd), shell=True)
            elif _is_admin():
                cmd = _generate_cmd("mklink", "/d")
                subprocess.check_call(" ".join(cmd), shell=True)
            else:
                cmd = ["/c"]
                cmd.extend(_generate_cmd("mklink", "/d"))
                _sudo("cmd", params=cmd)
        case "linux":
            cmd = _generate_cmd("ln", "-s", reverse=True)
            subprocess.check_call(" ".join(cmd), shell=True)
        case _:
            raise _UnsupportedPlatformError

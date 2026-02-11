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

import ctypes
import os
import subprocess
import sys


class UnsupportedPlatformError(Exception):
    pass


def sudo(executable: str, params: list[str] = None):
    """
    This will run the given executable and request to elevate administrative rights.

    Args:
        executable: the executable to run
        params: list of args to run with the executable
    """
    if not params:
        params = []

    match sys.platform:
        case "win32":
            result = ctypes.windll.shell32.ShellExecuteW(None, "runas", executable, " ".join(params), None, 1)
            if result <= 32:
                # The value 1223 indicates that the operation was cancelled by the user.
                raise RuntimeError("Elevation failed or was cancelled by the user")
        case "linux":
            # Search for sudo executable in order to avoid using shell=True with subprocess
            sudo_path = None
            for env_path in os.environ.get("PATH", "").split(os.pathsep):
                if os.path.isfile(os.path.join(env_path, "sudo")):
                    sudo_path = os.path.join(env_path, "sudo")
            if sudo_path is None:
                raise SystemError("Cannot find sudo executable.")
            subprocess.run(
                ["sudo", executable] + params, check=True, capture_output=True, text=True, stdin=subprocess.DEVNULL
            )
        case _:
            raise UnsupportedPlatformError


def is_admin() -> bool:
    """
    Tell if the current user has admin right or not
    """
    match sys.platform:
        case "win32":
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        case "linux":
            return os.getuid() == 0
        case _:
            raise UnsupportedPlatformError

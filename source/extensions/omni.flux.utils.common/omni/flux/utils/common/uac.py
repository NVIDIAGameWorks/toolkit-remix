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

# This file is based on the code from https://gist.github.com/BYK/0d456bcee068c56464be
"""   # noqa PLW0105
Copyright (c) 2013 by JustAMan at GitHub
Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""
import os  # noqa E402
import subprocess  # noqa E402
import sys  # noqa E402


class UnsupportedPlatformError(Exception):
    pass


if sys.platform == "win32":
    import ctypes
    from ctypes import c_char_p, c_int, c_ulong, c_void_p
    from ctypes.wintypes import BOOL, DWORD, HANDLE, HINSTANCE, HKEY, HWND

    class ShellExecuteInfo(ctypes.Structure):
        _fields_ = [
            ("cbSize", DWORD),
            ("fMask", c_ulong),
            ("hwnd", HWND),
            ("lpVerb", c_char_p),
            ("lpFile", c_char_p),
            ("lpParameters", c_char_p),
            ("lpDirectory", c_char_p),
            ("nShow", c_int),
            ("hInstApp", HINSTANCE),
            ("lpIDList", c_void_p),
            ("lpClass", c_char_p),
            ("hKeyClass", HKEY),
            ("dwHotKey", DWORD),
            ("hIcon", HANDLE),
            ("hProcess", HANDLE),
        ]

        def __init__(self, **kw):
            ctypes.Structure.__init__(self)
            self.cbSize = ctypes.sizeof(self)
            for field_name, field_value in kw.items():
                setattr(self, field_name, field_value)

    PShellExecuteInfo = ctypes.POINTER(ShellExecuteInfo)

    ShellExecuteEx = ctypes.windll.Shell32.ShellExecuteExA
    ShellExecuteEx.argtypes = (PShellExecuteInfo,)
    ShellExecuteEx.restype = BOOL

    WaitForSingleObject = ctypes.windll.kernel32.WaitForSingleObject
    WaitForSingleObject.argtypes = (HANDLE, DWORD)
    WaitForSingleObject.restype = DWORD

    CloseHandle = ctypes.windll.kernel32.CloseHandle
    CloseHandle.argtypes = (HANDLE,)
    CloseHandle.restype = BOOL

    SEE_MASK_NOCLOSEPROCESS = 0x00000040
    SEE_MASK_NO_CONSOLE = 0x00008000
    INFINITE = -1


def sudo(executable: str, params: list[str] = None, show_window: bool = False):
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
            execute_info = ShellExecuteInfo(
                fMask=SEE_MASK_NOCLOSEPROCESS | SEE_MASK_NO_CONSOLE,
                hwnd=ctypes.windll.user32.GetForegroundWindow(),
                lpVerb=b"runas",
                lpFile=executable.encode("utf-8"),
                lpParameters=" ".join(params).encode("utf-8"),
                lpDirectory=None,
                nShow=5 if show_window else 0,
            )

            ret = ShellExecuteEx(ctypes.byref(execute_info))
            if not ret:
                raise ctypes.WinError()

            WaitForSingleObject(execute_info.hProcess, INFINITE)
            CloseHandle(execute_info.hProcess)
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
    match sys.platform:  # noqa R503
        case "win32":
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        case "linux":
            return os.getuid() == 0  # noqa PLE1101
        case _:
            raise UnsupportedPlatformError

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

from __future__ import annotations

import argparse
import contextlib
import io
import runpy
import sys
from pathlib import Path

DESCRIPTION = "Run a Python script under Packman Python while capturing target output."


def _run_script(script: Path, args: list[str]) -> tuple[int, str, str]:
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    old_argv = sys.argv[:]
    sys.argv = [str(script), *args]

    try:
        with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
            try:
                runpy.run_path(str(script), run_name="__main__")
                return 0, stdout_buf.getvalue(), stderr_buf.getvalue()
            except SystemExit as exc:
                code = exc.code
                if code is None:
                    return 0, stdout_buf.getvalue(), stderr_buf.getvalue()
                if isinstance(code, int):
                    return code, stdout_buf.getvalue(), stderr_buf.getvalue()
                stderr = stderr_buf.getvalue()
                if stderr and not stderr.endswith("\n"):
                    stderr += "\n"
                return 1, stdout_buf.getvalue(), f"{stderr}{code}\n"
    except Exception as exc:  # noqa: BLE001 - runner boundary must convert target crashes to stderr + exit code.
        print(f"{script}: unhandled script failure: {exc}", file=stderr_buf)
        return 1, stdout_buf.getvalue(), stderr_buf.getvalue()
    finally:
        sys.argv = old_argv


def main() -> int:
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument("--stdout-file", required=True, type=Path)
    parser.add_argument("--stderr-file", required=True, type=Path)
    parser.add_argument("--exit-code-file", required=True, type=Path)
    parser.add_argument("script", type=Path)
    parser.add_argument("script_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    script_args = args.script_args
    if script_args and script_args[0] == "--":
        script_args = script_args[1:]

    code, stdout, stderr = _run_script(args.script, script_args)
    args.stdout_file.write_text(stdout, encoding="utf-8")
    args.stderr_file.write_text(stderr, encoding="utf-8")
    args.exit_code_file.write_text(str(code), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

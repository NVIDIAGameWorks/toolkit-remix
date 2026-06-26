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
import json
import subprocess
import sys
from pathlib import Path

DESCRIPTION = "Run configured Stop-hook checks and format failures for each agent."
CHECK_TIMEOUT = 300


def _run_check(script: Path, stdin_data: str) -> tuple[int, str]:
    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=CHECK_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return 2, f"{script.stem}: timed out after {CHECK_TIMEOUT}s"

    output = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
    return result.returncode, output


def _format_failures(failures: list[str]) -> str:
    return "\n\n".join(failures)


def _emit_failure(agent: str, message: str) -> int:
    if agent == "codex":
        print(json.dumps({"decision": "block", "reason": message}))
        return 0

    if agent == "cursor":
        print(json.dumps({"followup_message": message}))
        return 0

    print(message, file=sys.stderr)
    return 2


def main() -> int:
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument("--agent", choices=("claude", "codex", "cursor"), required=True)
    parser.add_argument("checks", nargs="+", type=Path)
    args = parser.parse_args()

    stdin_data = "" if sys.stdin.isatty() else sys.stdin.read()
    failures: list[str] = []

    for check in args.checks:
        if not check.exists():
            failures.append(f"{check}: hook check not found")
            continue

        code, output = _run_check(check, stdin_data)
        if code == 0:
            continue

        label = check.stem.replace("_", " ")
        if code == 2:
            failures.append(f"{label} failed:\n{output or 'blocked without remediation text'}")
        else:
            failures.append(f"{label} hook runtime error:\n{output or f'exit code {code}'}")

    if not failures:
        if args.agent == "cursor":
            print(json.dumps({}))
        return 0

    return _emit_failure(args.agent, _format_failures(failures))


if __name__ == "__main__":
    raise SystemExit(main())

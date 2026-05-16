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

DESCRIPTION = "Shared stop hook runner for project completion gates."
GATE_RUNNER_TIMEOUT = 300


def _run_gate(script: Path, stdin_data: str) -> tuple[int, str]:
    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=GATE_RUNNER_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return 2, f"{script.stem}: timed out after {GATE_RUNNER_TIMEOUT}s"

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
    parser.add_argument("scripts", nargs="+", type=Path)
    args = parser.parse_args()

    stdin_data = "" if sys.stdin.isatty() else sys.stdin.read()
    failures: list[str] = []

    for script in args.scripts:
        if not script.exists():
            failures.append(f"{script}: hook script not found")
            continue

        code, output = _run_gate(script, stdin_data)
        if code == 0:
            continue

        label = script.stem.replace("_", " ")
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

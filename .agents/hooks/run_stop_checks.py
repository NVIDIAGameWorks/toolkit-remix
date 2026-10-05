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
    """Run a check with the original hook input and collect its diagnostics."""
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


def _continuation_stop_reason(agent: str, stdin_data: str) -> str | None:
    """Explain why continuation is withheld, or return None for an explicitly eligible stop."""
    invalid_reason = "Stop metadata is missing or invalid, so no automatic continuation was requested."
    try:
        payload = json.loads(stdin_data)
    except json.JSONDecodeError:
        return invalid_reason

    if not isinstance(payload, dict):
        return invalid_reason

    if agent == "cursor":
        loop_count = payload.get("loop_count")
        status = payload.get("status")
        if type(loop_count) is not int or loop_count < 0 or status not in ("completed", "aborted", "error"):
            return invalid_reason
        if status != "completed":
            return f"Cursor reported a run status of '{status}'. No automatic continuation was requested."
        if loop_count > 0:
            return (
                "Cursor reports a previous automatic Stop-hook continuation. "
                "No further automatic continuation was requested."
            )
        return None

    stop_hook_active = payload.get("stop_hook_active")
    if stop_hook_active is False:
        return None
    if stop_hook_active is True:
        return "The client reports an active Stop-hook continuation. No further automatic continuation was requested."
    return invalid_reason


def _emit_failure(agent: str, message: str, stop_reason: str | None) -> int:
    """Request one repair or end automation with an explicit unresolved-check report."""
    if stop_reason is not None:
        stop_reason = f"Completion checks remain unresolved. {stop_reason} User feedback is required."
        report = f"{stop_reason}\n\n{message}"
        if agent == "cursor":
            print(json.dumps({}))
            print(report, file=sys.stderr)
        else:
            print(json.dumps({"continue": False, "stopReason": stop_reason, "systemMessage": report}))
        return 0

    message += (
        "\n\nThis is the only automatic continuation for these completion checks. "
        "Make one focused repair attempt when the fix is clear and within the user's instructions, then verify it. "
        "If a check still fails, cannot be resolved, conflicts with the user's instructions, or requires a user decision, "
        "name the failed checks in your final response, ask one concrete question for guidance, and end the turn. "
        "In that final response, explicitly state: 'Completion checks remain unresolved. "
        "Automatic continuation has stopped; I need your guidance.' "
        "Do not repeat unchanged blocked-status messages or claim that unresolved gates passed."
    )
    if agent == "codex":
        print(json.dumps({"decision": "block", "reason": message}))
        return 0

    if agent == "cursor":
        print(json.dumps({"followup_message": message}))
        return 0

    print(message, file=sys.stderr)
    return 2


def main() -> int:
    """Verify the checks and bound automatic continuation using the client's stop metadata."""
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

    return _emit_failure(args.agent, "\n\n".join(failures), _continuation_stop_reason(args.agent, stdin_data))


if __name__ == "__main__":
    raise SystemExit(main())

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

import argparse
import json
import subprocess
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path

from .providers import (
    ClaudeProvider,
    CodexProvider,
    CursorProvider,
    Provider,
    ProviderReadiness,
    ProviderSelection,
    ProviderSetupRequired,
    SetupIssue,
)
from .review_pipeline import _git_root, doctor, prepare_review, progress, review, scope
from .review_scope import check_forge_cli


__all__ = ["main"]


_PROVIDER_TYPES: dict[str, type[Provider]] = {
    "codex": CodexProvider,
    "claude": ClaudeProvider,
    "cursor": CursorProvider,
}
PROVIDERS = tuple(_PROVIDER_TYPES)

_DEFAULT_HEAD_REF = "HEAD"
_LANE_ORDER_FALLBACK = 99
_PREFLIGHT_TIMEOUT_SECONDS = 30.0

# The reasoning effort review workers use when the caller passes no `--reasoning`. Medium is the
# default because the 100-file calibration run measured it at about half the cost of the
# provider default on the identical packet shape (0.79s vs 1.51s per rule-file unit at the
# median) with no timeout pressure and no discovery penalty observed. A caller who passes
# `--reasoning` overrides this; a caller who passes nothing gets "medium" recorded in the run
# metadata and every worker timing entry, so the resolved effort is auditable.
_DEFAULT_REASONING = "medium"

# Setup codes that only the user can repair, by remedy. See `_setup_required_payload`.
_INSTALL_SETUP_CODES = frozenset({"CLI_NOT_FOUND", "CLI_UNEXECUTABLE", "FORGE_CLI_NOT_FOUND", "FORGE_CLI_UNEXECUTABLE"})
_LOGIN_SETUP_CODES = frozenset({"AUTH_REQUIRED", "FORGE_AUTH_REQUIRED"})


class UsageError(ValueError):
    """Report command-line usage errors."""


def emit_json(value: dict) -> None:
    """Emit one canonical JSON object on stdout."""
    print(json.dumps(value, ensure_ascii=False, sort_keys=True), file=sys.stdout)


class JsonArgumentParser(argparse.ArgumentParser):
    """Raise usage failures so the CLI can emit JSON."""

    def __init__(self, *args, **kwargs):
        """Disable ambiguous long-option abbreviations."""
        kwargs.setdefault("allow_abbrev", False)
        super().__init__(*args, **kwargs)
        self.command_options: dict[str, list[str]] = {}

    def error(self, message):
        """Raise one usage error instead of exiting with text output."""
        raise UsageError(message)


def _parser() -> JsonArgumentParser:
    """Build the small public command surface."""
    parser = JsonArgumentParser(add_help=False, description="Scripted native-agent Remix review")
    subparsers = parser.add_subparsers(dest="command", required=True)
    doctor_parser = subparsers.add_parser("doctor", add_help=False)
    parser.command_options["doctor"] = _provider_args(doctor_parser)
    review_parser = subparsers.add_parser("review", add_help=False)
    review_options = _provider_args(review_parser)
    review_options += review_parser.add_argument("--jobs", type=int).option_strings
    review_options += review_parser.add_argument("--deadline-seconds", type=int).option_strings
    review_options += review_parser.add_argument("--verify-model").option_strings
    review_options += _scope_args(review_parser)
    review_options += [
        option
        for action in (
            review_parser.add_argument("--previous-run"),
            review_parser.add_argument("--feedback", type=Path),
        )
        for option in action.option_strings
    ]
    parser.command_options["review"] = review_options
    scope_parser = subparsers.add_parser("scope", add_help=False)
    parser.command_options["scope"] = _scope_args(scope_parser)
    progress_parser = subparsers.add_parser("progress", add_help=False)
    parser.command_options["progress"] = [
        *progress_parser.add_argument("--run").option_strings,
        *progress_parser.add_argument("--review").option_strings,
    ]
    return parser


def _provider_args(parser: argparse.ArgumentParser) -> list[str]:
    """Add provider/model/reasoning options and return their flags."""
    return [
        option
        for action in (
            parser.add_argument("--agent", required=True, choices=PROVIDERS),
            parser.add_argument("--model"),
            parser.add_argument("--reasoning"),
        )
        for option in action.option_strings
    ]


def _scope_args(parser: argparse.ArgumentParser) -> list[str]:
    """Add remote-review and committed-workspace scope options and return their flags."""
    return [
        option
        for action in (
            parser.add_argument("--review"),
            parser.add_argument("--base"),
            parser.add_argument("--head", default=_DEFAULT_HEAD_REF),
        )
        for option in action.option_strings
    ]


def _selections(arguments: argparse.Namespace) -> tuple[ProviderSelection, ...]:
    """Assign the single provider selection for the one review lane."""
    return (_normalize_selection("primary", arguments.agent, arguments.model, arguments.reasoning),)


def _validate_scope(arguments: argparse.Namespace) -> None:
    """Validate the scope options shared by `review` and `scope`."""
    if arguments.review and (arguments.base is not None or arguments.head != _DEFAULT_HEAD_REF):
        raise UsageError("--review cannot be combined with --base or --head")


def _validate_review(arguments: argparse.Namespace) -> None:
    """Validate the review command contract."""
    if arguments.jobs is not None and arguments.jobs < 1:
        raise UsageError("--jobs must be positive")
    if arguments.deadline_seconds is not None and arguments.deadline_seconds < 1:
        raise UsageError("--deadline-seconds must be positive")
    _validate_scope(arguments)
    feedback = getattr(arguments, "feedback", None)
    if feedback is not None:
        if arguments.previous_run is None:
            raise UsageError("--feedback requires --previous-run")
        if arguments.base is not None:
            raise UsageError("--feedback cannot be combined with --base")
    if arguments.verify_model is not None:
        text = arguments.verify_model.strip()
        if not text or len(text) > 256 or text.startswith("-") or any(ord(character) < 32 for character in text):
            raise UsageError("--verify-model must be a nonempty provider identifier")
        arguments.verify_model = text


def _help_payload(parser: JsonArgumentParser, arguments: list[str]) -> dict:
    """Return JSON help."""
    command = next((value for value in arguments if value in parser.command_options), None)
    payload = {"schema_version": 1, "description": parser.description, "commands": list(parser.command_options)}
    if command:
        payload["command"] = command
        payload["options"] = parser.command_options[command]
    return payload


def _normalize_selection(lane: str, provider: str, model: str | None, reasoning: str | None) -> ProviderSelection:
    """Validate lane controls without local model allowlists, resolving the reasoning default."""
    if provider not in _PROVIDER_TYPES:
        raise UsageError(f"unknown provider: {provider}")
    # Resolve the reasoning default here, at the CLI boundary, so the resolved value is what the
    # providers receive and what the run records — not a downstream inference from the code path.
    reasoning = reasoning if reasoning is not None else _DEFAULT_REASONING
    values = []
    for name, value in (("model", model), ("reasoning", reasoning)):
        text = value.strip() if value is not None else None
        if text is not None and (
            not text or len(text) > 256 or text.startswith("-") or any(ord(character) < 32 for character in text)
        ):
            raise UsageError(f"{name} must be a nonempty provider identifier")
        values.append(text)
    return ProviderSelection(lane, provider, values[0], values[1])


def _providers(selections: tuple[ProviderSelection, ...]) -> dict[str, Provider]:
    """Create one adapter per selected provider."""
    return {name: _PROVIDER_TYPES[name]() for name in sorted({selection.provider for selection in selections})}


def _readiness(
    selections: tuple[ProviderSelection, ...],
    providers: dict[str, Provider],
    deadline_mono: float | None = None,
) -> dict[str, ProviderReadiness]:
    """Run selected provider setup once within the whole-run deadline."""
    if not selections:
        return {}
    now = time.monotonic()
    deadline = now + _PREFLIGHT_TIMEOUT_SECONDS
    if deadline_mono is not None:
        deadline = min(deadline, deadline_mono)
    if deadline <= now:
        raise TimeoutError("The review deadline expired before provider readiness checks.")
    selection = selections[0]
    return {selection.provider: providers[selection.provider].preflight(selections, deadline)}


def _setup_required_payload(issues: tuple[SetupIssue, ...]) -> dict:
    """Return actionable setup errors for the selected provider or the forge CLI."""
    lane_order = {"scope": -1, "primary": 0, "review": 1, "synthesis": 2}
    ordered = sorted(
        (
            replace(
                issue,
                affected_lanes=tuple(
                    sorted(issue.affected_lanes, key=lambda lane: (lane_order.get(lane, _LANE_ORDER_FALLBACK), lane))
                ),
            )
            for issue in issues
        ),
        key=lambda item: (item.provider, item.code, item.affected_lanes),
    )
    forge_only = all(issue.affected_lanes == ("scope",) for issue in ordered)
    codes = {issue.code for issue in ordered}
    # An install or a login is the user's action: the login is interactive, and a CLI installed
    # during the session is not on the running shell's PATH. Every other code (a model, a
    # reasoning value, a configuration file, an unreadable auth status) is a repair the caller
    # can attempt itself.
    if codes & _INSTALL_SETUP_CODES:
        question = (
            "Install or reinstall the named CLI, open a new terminal so PATH includes it, run its login command "
            "there, then ask me to retry. Do you want to do that now?"
        )
    elif codes & _LOGIN_SETUP_CODES:
        question = "Run the login command from the error in your own terminal, then ask me to retry. Do you want to do that now?"
    else:
        question = "Do you want me to fix the listed setup issues and retry?"
    return {
        "schema_version": 1,
        "status": "setup_required",
        "stage": "forge_preflight" if forge_only else "provider_preflight",
        "message": (
            "The forge CLI cannot serve the exact merge request diff, so the review did not start."
            if forge_only
            else "Selected provider setup is incomplete, so the review did not start."
        ),
        "errors": [asdict(issue) for issue in ordered],
        "question": question,
    }


def main(argv: list[str] | None = None) -> int:
    """Run the lightweight scripted review command."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    parser = _parser()
    if "--help" in arguments:
        emit_json(_help_payload(parser, arguments))
        return 0
    try:
        parsed = parser.parse_args(arguments)
        prepared = None
        started_mono = None
        deadline_mono = None
        if parsed.command == "progress":
            emit_json(progress(parsed.run, parsed.review))
            return 0
        if parsed.command in {"review", "scope"}:
            # Usage errors must cost nothing: validate before any provider CLI starts.
            (_validate_review if parsed.command == "review" else _validate_scope)(parsed)
            # The forge CLI check is cheap and runs first, so a missing `glab` never costs a
            # provider preflight and never invites a fallback to the local branch.
            if parsed.review:
                check_forge_cli(_git_root(), parsed.review)
        if parsed.command == "scope":
            emit_json(scope(parsed))
            return 0
        if parsed.command == "review":
            started_mono = time.monotonic()
            deadline_mono = started_mono + parsed.deadline_seconds if parsed.deadline_seconds is not None else None
            prepared = prepare_review(parsed, deadline_mono=deadline_mono) if parsed.previous_run is not None else None
        selections = _selections(parsed)
        providers = _providers(selections)
        readiness = _readiness(selections, providers, deadline_mono)
        if parsed.command == "doctor":
            emit_json(doctor(selections, readiness, providers))
            return 0
        if parsed.command == "review":
            result = review(
                parsed,
                selections,
                readiness,
                providers,
                prepared,
                started_mono=started_mono,
                deadline_mono=deadline_mono,
            )
            emit_json(result)
            return 0 if result.get("status") == "complete" else 1
        raise UsageError(f"unknown command: {parsed.command}")
    except UsageError as error:
        print(str(error), file=sys.stderr)
        emit_json({"schema_version": 1, "error": "usage_error", "message": str(error)})
        return 2
    except ProviderSetupRequired as error:
        emit_json(_setup_required_payload(error.issues))
        return 3
    except KeyboardInterrupt:
        emit_json({"schema_version": 1, "status": "interrupted"})
        return 130
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        emit_json({"schema_version": 1, "error": "runtime_error", "message": str(error)})
        return 1

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

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from pathlib import Path

from ..process_pool import ProbeTimeout, WorkerSpec, clean_environment, run_probe


__all__ = [
    "ModelCapability",
    "Provider",
    "ProviderCapabilities",
    "ProviderReadiness",
    "ProviderSelection",
    "ProviderSetupRequired",
    "ReasoningCapability",
    "SetupIssue",
    "WorkerRequest",
    "denial_tool_kind",
    "merge_permission_denials",
]


# Tools the worker specification grants: read-only and web capabilities. A sandbox denial of one
# of these is a normal refusal, so the receipt stays valid and the denial becomes a gap.
READ_ONLY_DENIED_TOOLS = frozenset({"Read", "Glob", "Grep", "WebSearch", "WebFetch"})
# Tools the worker specification never grants. A denial of one of these means the worker attempted
# a write, which is a contract violation or a compromised prompt, and it must fail loudly.
WRITE_DENIED_TOOLS = frozenset({"Write", "Edit", "NotebookEdit", "Bash"})


def denial_tool_kind(entry: object) -> str:
    """Classify one permission-denial entry as "read", "write", or "unknown".

    Both call sites share this one classification so the accept and the stop paths cannot drift.
    An entry that cannot be classified is "unknown": a non-object entry, a missing tool name, or
    a tool in neither set never defaults to the accepting branch, so a future tool fails closed.
    """
    tool = entry.get("tool_name") if isinstance(entry, dict) else None
    if tool in READ_ONLY_DENIED_TOOLS:
        return "read"
    if tool in WRITE_DENIED_TOOLS:
        return "write"
    return "unknown"


def merge_permission_denials(receipt: dict, envelope: dict) -> dict:
    """Fold a result envelope's permission denials into a copy of the receipt, or raise.

    A denied read-only or web tool is an honest limit, like a gap: the worker asked, the sandbox
    refused, and the review work is still valid. Each such denial becomes one gap that names the
    tool. A denied write tool stays terminal, and an unclassifiable entry fails closed; both
    raise ValueError so the envelope is rejected. The given receipt is never edited in place, and
    a `gaps` value that is not a list of strings is rejected, never repaired.
    """
    denials = envelope.get("permission_denials") or ()
    if not isinstance(denials, (list, tuple)):
        raise ValueError(f"worker returned an unclassifiable permission denial: {denials!r:.200}")
    gaps = []
    for entry in denials:
        kind = denial_tool_kind(entry)
        if kind == "read":
            detail = entry.get("tool_input")
            hint = f" for {json.dumps(detail, sort_keys=True)[:160]}" if isinstance(detail, dict) else ""
            gaps.append(
                f"The sandbox denied the {entry['tool_name']} tool{hint}, so any check that needed it did not run."
            )
        elif kind == "write":
            raise ValueError(f"the worker attempted a write: the sandbox denied the {entry['tool_name']} tool")
        else:
            raise ValueError(f"worker returned an unclassifiable permission denial: {entry!r:.200}")
    if not gaps:
        return receipt
    existing = receipt.get("gaps", [])
    if not isinstance(existing, list) or not all(isinstance(gap, str) for gap in existing):
        raise ValueError("worker receipt has a gaps value that is not a list of strings")
    return {**receipt, "gaps": [*existing, *gaps]}


@dataclass(frozen=True)
class ProviderSelection:
    """Identify one provider lane and its native controls."""

    lane: str
    provider: str
    model: str | None
    reasoning: str | None


@dataclass(frozen=True)
class SetupIssue:
    """Describe one provider readiness failure."""

    provider: str
    affected_lanes: tuple[str, ...]
    code: str
    message: str


@dataclass(frozen=True)
class ModelCapability:
    """Describe one model exposed by a provider."""

    id: str
    reasoning: tuple[str, ...] = ()
    reasoning_complete: bool = False


@dataclass(frozen=True)
class ReasoningCapability:
    """Describe one provider's reasoning control."""

    mode: str
    values: tuple[str, ...] = ()
    complete: bool = False


@dataclass(frozen=True)
class ProviderCapabilities:
    """Normalize provider controls before exposing them as doctor JSON."""

    models: tuple[ModelCapability, ...]
    models_complete: bool
    reasoning: ReasoningCapability


@dataclass(frozen=True)
class ProviderReadiness:
    """Capture one provider's validated native capabilities."""

    command: tuple[str, ...]
    capabilities: ProviderCapabilities
    account: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkerRequest:
    """Describe one provider-neutral review worker request."""

    worker_id: str
    schema_path: Path
    worker_cwd: Path
    project_root: Path
    prompt_path: Path
    stdout_path: Path
    stderr_path: Path
    read_paths: tuple[Path, ...]
    selection: ProviderSelection

    @property
    def read_roots(self) -> tuple[Path, ...]:
        """Return unique directories providers may expose for reading."""
        return tuple(sorted({path if path.is_dir() else path.parent for path in self.read_paths}, key=str))


class ProviderSetupRequired(RuntimeError):  # noqa: N818 - canonical public contract
    """Report selected provider setup failures."""

    def __init__(self, issues: tuple[SetupIssue, ...]):
        """Store sanitized provider setup issues."""
        super().__init__("selected provider setup is incomplete")
        self.issues = issues


class Provider(ABC):
    """Define native-provider operations used by the shared runtime."""

    name: str
    initial_jobs: int

    def preflight(self, selections: tuple[ProviderSelection, ...], deadline: float) -> ProviderReadiness:
        """Resolve, authenticate, discover, and validate this native provider."""
        lanes = tuple(selection.lane for selection in selections)
        command = self._resolve_command(lanes, deadline)
        try:
            account = self.check_authentication(command, deadline)
            capabilities = self.discover_capabilities(command, deadline)
        except ProviderSetupRequired as error:
            raise ProviderSetupRequired(
                tuple(issue if issue.affected_lanes else replace(issue, affected_lanes=lanes) for issue in error.issues)
            ) from None
        selection_issues = []
        for selection in selections:
            try:
                self._validate_selection(selection, capabilities)
            except ProviderSetupRequired as error:
                selection_issues.extend(error.issues)
        if selection_issues:
            raise ProviderSetupRequired(tuple(selection_issues))
        return ProviderReadiness(command, capabilities, account)

    @abstractmethod
    def command_candidates(self) -> tuple[tuple[str, ...], ...]:
        """Return shell-free native CLI command candidates."""
        raise NotImplementedError

    @abstractmethod
    def check_authentication(self, command: tuple[str, ...], deadline: float) -> dict[str, str]:
        """Verify native CLI authentication and return a sanitized account descriptor."""
        raise NotImplementedError

    @abstractmethod
    def discover_capabilities(self, command: tuple[str, ...], deadline: float) -> ProviderCapabilities:
        """Discover live model and reasoning controls."""
        raise NotImplementedError

    def prepare_workspace(self, request: WorkerRequest) -> None:
        """Prepare provider-owned worker configuration when required."""
        del request

    @abstractmethod
    def build_worker(self, readiness: ProviderReadiness, request: WorkerRequest) -> WorkerSpec:
        """Translate one canonical request into a native process specification."""
        raise NotImplementedError

    @abstractmethod
    def decode(self, stdout_path: Path) -> dict:
        """Decode native structured output into one canonical worker result."""
        raise NotImplementedError

    def usage(self, stdout_path: Path, stderr_path: Path) -> dict[str, int]:
        """Return token counts that the provider reported, or an empty mapping."""
        del stdout_path, stderr_path
        return {}

    def needs_user_action(self, returncode: int, stdout: str, stderr: str) -> bool:
        """Return whether one worker failure should stop fan-out for user action.

        The envelope's permission denials classify through the same helper as receipt decoding.
        A denied read-only or web tool is a normal limit, so the packet follows the ordinary
        retry and failure path. A denied write tool means the worker broke the contract, and an
        unclassifiable entry fails closed; both stop the run for user action.
        """
        del returncode, stderr
        try:
            envelope = json.loads(stdout)
        except json.JSONDecodeError:
            return False
        if not isinstance(envelope, dict):
            return False
        denials = envelope.get("permission_denials") or ()
        if not isinstance(denials, (list, tuple)):
            return True
        return any(denial_tool_kind(entry) != "read" for entry in denials)

    def _probe(
        self,
        argv: tuple[str, ...],
        deadline: float,
        code: str,
        message: str,
        *,
        environment: dict[str, str] | None = None,
        timeout_message: str | None = None,
    ):
        """Run one readiness probe and map execution failures to setup issues."""
        try:
            return run_probe(
                argv,
                cwd=None,
                environment=clean_environment() if environment is None else environment,
                deadline=deadline,
            )
        except ProbeTimeout:
            self.fail_setup((), "PREFLIGHT_TIMEOUT", timeout_message or f"{self.name.title()} readiness timed out.")
        except OSError:
            self.fail_setup((), code, message)

    def _optional_probe(
        self,
        argv: tuple[str, ...],
        deadline: float,
        *,
        environment: dict[str, str] | None = None,
    ):
        """Return optional provider metadata without blocking an otherwise usable CLI."""
        try:
            return run_probe(
                argv,
                cwd=None,
                environment=clean_environment() if environment is None else environment,
                deadline=min(deadline, time.monotonic() + 5.0),
            )
        except (OSError, ProbeTimeout):
            return None

    def fail_setup(self, lanes: tuple[str, ...], code: str, message: str) -> None:
        """Raise one sanitized provider setup failure."""
        raise ProviderSetupRequired(
            (
                SetupIssue(
                    provider=self.name,
                    affected_lanes=lanes,
                    code=code,
                    message=message,
                ),
            )
        )

    def _resolve_command(self, lanes: tuple[str, ...], deadline: float) -> tuple[str, ...]:
        candidates = self.command_candidates()
        if not candidates:
            self.fail_setup(
                lanes,
                "CLI_NOT_FOUND",
                f"{self.name.title()} CLI was not found. Install it and add its command to PATH.",
            )
        for candidate in candidates:
            try:
                run_probe(
                    (*candidate, "--version"),
                    cwd=None,
                    environment=clean_environment(),
                    deadline=deadline,
                )
            except ProbeTimeout:
                self.fail_setup(lanes, "PREFLIGHT_TIMEOUT", f"{self.name} readiness timed out.")
            except OSError:
                continue
            return candidate
        self.fail_setup(
            lanes, "CLI_UNEXECUTABLE", f"{self.name.title()} CLI could not be executed. Update or reinstall it."
        )
        raise AssertionError("unreachable")

    def _validate_selection(self, selection: ProviderSelection, capabilities: ProviderCapabilities) -> None:
        model = selection.model
        reasoning = selection.reasoning
        models = {entry.id: entry for entry in capabilities.models}
        if model is not None and capabilities.models_complete and model not in models:
            self._fail_selection(
                selection,
                "INVALID_MODEL",
                (
                    f"{self.name} model {model!r} is not available. Omit the model override or run doctor "
                    "without it to inspect current options."
                ),
            )
        reasoning_info = capabilities.reasoning
        if reasoning is None:
            return
        if reasoning_info.mode == "encoded_in_model":
            self._fail_selection(selection, "INVALID_REASONING", f"{self.name} exposes reasoning through model IDs.")
        allowed = reasoning_info.values
        complete = reasoning_info.complete
        if reasoning_info.mode == "per_model":
            if model in models:
                allowed = models[model].reasoning
                complete = capabilities.models_complete and models[model].reasoning_complete
            else:
                complete = False
        if complete and reasoning not in allowed:
            self._fail_selection(
                selection,
                "INVALID_REASONING",
                (
                    f"{self.name} reasoning {reasoning!r} is not available. Omit the reasoning override or run "
                    "doctor without it to inspect current options."
                ),
            )

    def _fail_selection(self, selection: ProviderSelection, code: str, message: str) -> None:
        raise ProviderSetupRequired(
            (
                SetupIssue(
                    self.name,
                    (selection.lane,),
                    code,
                    message,
                ),
            )
        )

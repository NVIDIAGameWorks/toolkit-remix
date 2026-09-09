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
import re
from pathlib import Path

from ..artifacts import write_json as _write_json
from ..process_pool import WorkerSpec, clean_environment, resolve_executable
from .base import (
    ModelCapability,
    Provider,
    ProviderCapabilities,
    ProviderReadiness,
    ReasoningCapability,
    WorkerRequest,
    merge_permission_denials,
)


__all__ = ["CursorProvider"]


def _parse_models(output: str) -> list[ModelCapability]:
    """Parse Cursor's optional model list from JSON or simple text output."""
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        payload = None
    values = payload.get("models") if isinstance(payload, dict) else payload
    if isinstance(values, list):
        identifiers = [
            value if isinstance(value, str) else value.get("id") if isinstance(value, dict) else None
            for value in values
        ]
    else:
        clean = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", output)
        identifiers = [match.group(1) for line in clean.splitlines() if (match := re.match(r"^\s*([^\s]+)\s+-", line))]
    return [ModelCapability(value) for value in dict.fromkeys(identifiers) if isinstance(value, str) and value]


class CursorProvider(Provider):
    """Adapt Cursor Agent's result envelope and private permission files."""

    name = "cursor"
    initial_jobs = 8

    def __init__(self) -> None:
        self._command_aliases: dict[tuple[str, ...], str] = {}
        self._help_text: dict[tuple[str, ...], str] = {}
        self._selected_command_alias = "cursor-agent"

    def command_candidates(self) -> tuple[tuple[str, ...], ...]:
        candidates = []
        direct = resolve_executable("cursor-agent")
        if direct:
            command = (str(direct),)
            candidates.append(command)
            self._command_aliases[command] = "cursor-agent"
        generic = resolve_executable("agent")
        if generic:
            command = (str(generic),)
            candidates.append(command)
            self._command_aliases[command] = "agent"
        return tuple(candidates)

    def check_authentication(self, command: tuple[str, ...], deadline: float) -> dict[str, str]:
        self._selected_command_alias = self._command_aliases.get(command, "cursor-agent")
        if self._selected_command_alias == "agent":
            # `agent` is only accepted when its public help identifies Cursor.
            # No suffix or install-layout probing: the CLI is a black box.
            identity = self._probe(
                (*command, "--help"),
                deadline,
                "CLI_UNEXECUTABLE",
                "Cursor Agent could not be executed.",
                timeout_message="Cursor Agent readiness timed out.",
            )
            identity_text = (identity.stdout + identity.stderr).decode("utf-8", errors="replace")
            if identity.returncode or not re.search(r"\bcursor[ -]agent\b", identity_text, re.IGNORECASE):
                self.fail_setup((), "CLI_INCOMPATIBLE", "The generic agent executable is not Cursor Agent.")
            self._help_text[command] = identity_text
        result = self._probe(
            (*command, "status"),
            deadline,
            "AUTH_CHECK_FAILED",
            "Cursor Agent authentication could not be checked.",
            timeout_message="Cursor Agent readiness timed out.",
        )
        status = (result.stdout + result.stderr).decode("utf-8", errors="replace").lower()
        unauthenticated = any(
            marker in status for marker in ("not logged", "unauthenticated", "login required", "no credentials")
        )
        if unauthenticated:
            self.fail_setup((), "AUTH_REQUIRED", "Cursor Agent is not authenticated. Run 'cursor-agent login'.")
        if result.returncode:
            self.fail_setup((), "AUTH_CHECK_FAILED", "Cursor Agent authentication could not be checked.")
        # Cursor exposes no verified sanitized identity contract.
        return {}

    def discover_capabilities(self, command: tuple[str, ...], deadline: float) -> ProviderCapabilities:
        """Discover Cursor model controls."""
        help_text = self._help_text.get(command)
        if help_text is None:
            help_result = self._optional_probe((*command, "--help"), deadline)
            help_text = (
                (help_result.stdout + help_result.stderr).decode("utf-8", errors="replace")
                if help_result is not None and help_result.returncode == 0
                else ""
            )
        suffix = None
        # Model listing is optional and best-effort. Unknown models still go
        # through Cursor's real packet canary instead of a stale local allowlist.
        if "--list-models" in help_text:
            suffix = ("--list-models",)
        elif re.search(r"(?m)^\s*models(?:\s|$)", help_text):
            suffix = ("models",)
        models = []
        if suffix is not None:
            result = self._optional_probe((*command, *suffix), deadline)
            if result is not None and result.returncode == 0:
                models = _parse_models(result.stdout.decode("utf-8", errors="replace"))
        return ProviderCapabilities(
            tuple(models),
            False,
            ReasoningCapability("encoded_in_model"),
        )

    def prepare_workspace(self, request: WorkerRequest) -> None:
        """Write private Cursor read permissions for this one worker."""
        read_rules = [f"Read({root.as_posix()}/**)" for root in request.read_roots]
        _write_json(
            request.worker_cwd / ".cursor" / "cli.json",
            {"permissions": {"allow": read_rules, "deny": ["Shell(*)", "Write(**)"]}},
        )

    def build_worker(self, readiness: ProviderReadiness, request: WorkerRequest) -> WorkerSpec:
        """Build one headless Cursor Agent packet worker."""
        argv = [*readiness.command, "-p", "--trust", "--mode=ask", "--output-format", "json"]
        model = request.selection.model
        if model is not None:
            argv.extend(("--model", model))
        return WorkerSpec(
            worker_id=request.worker_id,
            argv=tuple(argv),
            cwd=request.worker_cwd,
            environment=clean_environment(),
            prompt_path=request.prompt_path,
            stdout_path=request.stdout_path,
            stderr_path=request.stderr_path,
        )

    def decode(self, stdout_path: Path) -> dict:
        """Extract one receipt from Cursor's structured result envelope."""
        try:
            payload = json.loads(stdout_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("Cursor worker returned malformed JSON") from error
        if (
            not isinstance(payload, dict)
            or payload.get("type") != "result"
            or payload.get("subtype") != "success"
            or payload.get("is_error") is not False
        ):
            raise ValueError("Cursor worker returned an invalid structured envelope")
        receipt = payload.get("structured_output", payload.get("result"))
        if isinstance(receipt, str):
            try:
                receipt = json.loads(receipt)
            except json.JSONDecodeError as error:
                raise ValueError("Cursor worker returned malformed result JSON") from error
        if not isinstance(receipt, dict):
            raise ValueError("Cursor worker did not return a receipt object")
        return merge_permission_denials(receipt, payload)

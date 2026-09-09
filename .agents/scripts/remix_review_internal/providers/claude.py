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

from ..process_pool import WorkerSpec, clean_environment, resolve_executable
from .base import (
    Provider,
    ProviderCapabilities,
    ProviderReadiness,
    ReasoningCapability,
    WorkerRequest,
    merge_permission_denials,
)


__all__ = ["ClaudeProvider"]


_NESTING_VARIABLES = (
    "CLAUDECODE",
    "CLAUDE_CODE_CHILD_SESSION",
    "CLAUDE_CODE_SESSION_ID",
)
_REASONING_VARIABLES = (
    "CLAUDE_CODE_DISABLE_THINKING",
    "CLAUDE_CODE_EFFORT_LEVEL",
    "MAX_THINKING_TOKENS",
)


class ClaudeProvider(Provider):
    """Adapt Claude Code's JSON result envelope to the shared worker API."""

    name = "claude"
    initial_jobs = 22

    def command_candidates(self) -> tuple[tuple[str, ...], ...]:
        executable = resolve_executable("claude")
        return ((str(executable),),) if executable else ()

    def check_authentication(self, command: tuple[str, ...], deadline: float) -> dict[str, str]:
        """Use Claude's auth JSON, but never surface raw account data."""
        result = self._probe(
            (*command, "--setting-sources", "", "auth", "status", "--json"),
            deadline,
            "AUTH_CHECK_FAILED",
            "Claude Code authentication could not be checked.",
            environment=self._environment(False),
            timeout_message="Claude Code readiness timed out.",
        )
        try:
            status = json.loads(result.stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.fail_setup((), "AUTH_CHECK_FAILED", "Claude Code authentication could not be checked.")
        if isinstance(status, dict) and status.get("loggedIn") is False:
            self.fail_setup((), "AUTH_REQUIRED", "Claude Code is not authenticated. Run 'claude auth login'.")
        if result.returncode or not isinstance(status, dict) or status.get("loggedIn") is not True:
            self.fail_setup((), "AUTH_CHECK_FAILED", "Claude Code authentication could not be checked.")
        keys = (
            ("authMethod", "auth_method"),
            ("apiProvider", "api_provider"),
            ("orgName", "organization"),
            ("orgId", "organization_id"),
            ("subscriptionType", "subscription"),
        )
        account: dict[str, str] = {}
        for source, target in keys:
            value = status.get(source)
            if value:
                account[target] = str(value)
        return account

    def discover_capabilities(self, command: tuple[str, ...], deadline: float) -> ProviderCapabilities:
        """Discover Claude Code reasoning controls."""
        # Claude has no complete noninteractive model catalog. Help-derived
        # effort values are advisory; explicit model validation is canary-owned.
        result = self._optional_probe((*command, "--help"), deadline, environment=self._environment(False))
        help_text = (
            (result.stdout + result.stderr).decode("utf-8", errors="replace")
            if result is not None and result.returncode == 0
            else ""
        )
        effort = re.search(r"--effort[^\n]*(?:\n[ \t]+)?\(([^()\n]*)\)", help_text)
        values = [] if effort is None else [value.strip(" \t\r\n'\"") for value in effort.group(1).split(",")]
        values = [value for value in values if re.fullmatch(r"[A-Za-z0-9_.-]+", value)]
        return ProviderCapabilities(
            (),
            False,
            ReasoningCapability("model_dependent", tuple(values)),
        )

    def build_worker(self, readiness: ProviderReadiness, request: WorkerRequest) -> WorkerSpec:
        """Build one read-only Claude packet worker from a bounded invoking-context snapshot."""
        # Read, Glob, and Grep cover the workspace. WebSearch and WebFetch are read-only network tools.
        # The worker gets no shell and no write tools, so no project or outside state can change.
        tools = "Read,Glob,Grep,WebSearch,WebFetch"
        argv = [
            *readiness.command,
            "-p",
            # No --safe-mode: project instructions must load. The worker cwd is a bounded
            # invoking-context snapshot, so CLAUDE.md and agent rules never come from a reviewed
            # checkout. Hooks stay disabled because they execute commands, and MCP stays pinned
            # to none.
            "--no-session-persistence",
            "--setting-sources",
            "user,project",
            "--output-format",
            "json",
            "--json-schema",
            request.schema_path.read_text(encoding="utf-8"),
            "--strict-mcp-config",
            "--settings",
            json.dumps({"disableAllHooks": True}),
            "--permission-mode",
            "dontAsk",
            "--tools",
            tools,
        ]
        model = request.selection.model
        reasoning = request.selection.reasoning
        if model is not None:
            argv.extend(("--model", model))
        if reasoning is not None:
            argv.extend(("--effort", reasoning))
        for root in request.read_roots:
            argv.extend(("--add-dir", str(root)))
        return WorkerSpec(
            worker_id=request.worker_id,
            argv=tuple(argv),
            cwd=request.project_root,
            environment=self._environment(reasoning is not None),
            prompt_path=request.prompt_path,
            stdout_path=request.stdout_path,
            stderr_path=request.stderr_path,
        )

    def decode(self, stdout_path: Path) -> dict:
        """Extract the schema-validated receipt from Claude's result envelope."""
        try:
            envelope = json.loads(stdout_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("Claude worker returned malformed JSON") from error
        if (
            not isinstance(envelope, dict)
            or envelope.get("type") != "result"
            or envelope.get("subtype") != "success"
            or envelope.get("is_error") is not False
            or not isinstance(envelope.get("structured_output"), dict)
        ):
            raise ValueError("Claude worker returned an invalid structured envelope")
        # A denied tool call no longer destroys a valid receipt: read-only denials become gaps,
        # write attempts and unclassifiable entries raise inside the merge.
        return merge_permission_denials(envelope["structured_output"], envelope)

    def usage(self, stdout_path: Path, stderr_path: Path) -> dict[str, int]:
        """Parse token counts from Claude stdout result envelope."""
        del stderr_path
        try:
            envelope = json.loads(stdout_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(envelope, dict):
            return {}
        raw_usage = envelope.get("usage")
        if not isinstance(raw_usage, dict):
            return {}
        result: dict[str, int] = {}
        input_tokens = raw_usage.get("input_tokens") if "input_tokens" in raw_usage else raw_usage.get("input")
        if isinstance(input_tokens, int):
            result["input"] = input_tokens
        output_tokens = raw_usage.get("output_tokens") if "output_tokens" in raw_usage else raw_usage.get("output")
        if isinstance(output_tokens, int):
            result["output"] = output_tokens
        cached_tokens = (
            raw_usage.get("cache_read_input_tokens")
            if "cache_read_input_tokens" in raw_usage
            else raw_usage.get("cached")
        )
        if isinstance(cached_tokens, int):
            result["cached"] = cached_tokens
        total_tokens = raw_usage.get("total_tokens") if "total_tokens" in raw_usage else raw_usage.get("total")
        if isinstance(total_tokens, int):
            result["total"] = total_tokens
        elif "input" in result or "output" in result:
            result["total"] = result.get("input", 0) + result.get("output", 0)
        return result

    @staticmethod
    def _environment(explicit_reasoning: bool) -> dict[str, str]:
        environment = clean_environment()
        for name in _NESTING_VARIABLES:
            environment.pop(name, None)
        if explicit_reasoning:
            for name in _REASONING_VARIABLES:
                environment.pop(name, None)
        environment.update(
            {
                "CLAUDE_CODE_AUTO_CONNECT_IDE": "false",
                # Additional review directories are code evidence, never instruction roots.
                "CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD": "0",
                "CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS": "1",
                "CLAUDE_CODE_DISABLE_OFFICIAL_MARKETPLACE_AUTOINSTALL": "1",
                "DISABLE_AUTOUPDATER": "1",
            }
        )
        return environment

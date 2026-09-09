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

import json
import re
from pathlib import Path

from ..process_pool import WorkerSpec, clean_environment, resolve_executable
from .base import (
    ModelCapability,
    Provider,
    ProviderCapabilities,
    ProviderReadiness,
    ReasoningCapability,
    WorkerRequest,
)


__all__ = ["CodexProvider"]


class CodexProvider(Provider):
    """Adapt Codex CLI's bare structured-output contract to the shared worker API."""

    name = "codex"
    initial_jobs = 22

    def command_candidates(self) -> tuple[tuple[str, ...], ...]:
        executable = resolve_executable("codex")
        return ((str(executable),),) if executable else ()

    def check_authentication(self, command: tuple[str, ...], deadline: float) -> dict[str, str]:
        result = self._probe((*command, "login", "status"), deadline, "AUTH_CHECK_FAILED", "Codex auth status failed.")
        raw = (result.stdout + result.stderr).decode("utf-8", errors="replace")
        output = raw.lower()
        unauthenticated = any(
            marker in output for marker in ("not logged in", "not authenticated", "login required", "no credentials")
        )
        if unauthenticated:
            self.fail_setup((), "AUTH_REQUIRED", "Codex is not authenticated. Run 'codex login'.")
        if result.returncode:
            self.fail_setup((), "AUTH_CHECK_FAILED", "Codex authentication could not be checked.")
        match = re.search(r"logged in using\s+([^\n]+)", raw, re.IGNORECASE)
        if match:
            method = match.group(1).strip()
            if re.fullmatch(r"[A-Za-z0-9 ._-]{1,40}", method) and "@" not in method:
                return {"auth_method": method}
        return {}

    def discover_capabilities(self, command: tuple[str, ...], deadline: float) -> ProviderCapabilities:
        """Discover Codex model and reasoning controls."""
        # `exec --help` is the hard requirement. Model discovery is advisory: if
        # `debug models` changes, the packet canary remains the source of truth.
        exec_result = self._probe(
            (*command, "exec", "--help"),
            deadline,
            "CLI_INCOMPATIBLE",
            "Codex noninteractive mode could not be inspected.",
        )
        if exec_result.returncode:
            self.fail_setup((), "CLI_INCOMPATIBLE", "Codex does not expose noninteractive mode.")
        result = self._optional_probe((*command, "debug", "models"), deadline)
        payload = None
        if result is not None and result.returncode == 0:
            try:
                payload = json.loads(result.stdout)
            except (UnicodeDecodeError, json.JSONDecodeError):
                payload = None
        raw_models = payload.get("models", []) if isinstance(payload, dict) else []
        raw_models = raw_models if isinstance(raw_models, list) else []
        models = []
        for item in raw_models:
            if not isinstance(item, dict) or not isinstance(item.get("slug"), str) or not item["slug"]:
                continue
            levels = item.get("supported_reasoning_levels")
            if not isinstance(levels, list):
                continue
            reasoning = tuple(
                level["effort"]
                for level in levels
                if isinstance(level, dict) and isinstance(level.get("effort"), str) and level["effort"]
            )
            if len(reasoning) == len(levels):
                models.append(ModelCapability(item["slug"], reasoning, True))
        models = tuple({model.id: model for model in models}.values())
        complete = bool(models) and len(models) == len(raw_models)
        return ProviderCapabilities(
            models,
            complete,
            ReasoningCapability(
                "per_model", tuple(sorted({level for model in models for level in model.reasoning})), complete
            ),
        )

    def build_worker(self, readiness: ProviderReadiness, request: WorkerRequest) -> WorkerSpec:
        """Build one read-only `codex exec` invocation for a packet."""
        selection = []
        if request.selection.model is not None:
            selection.extend(("--model", request.selection.model))
        if request.selection.reasoning is not None:
            selection.extend(("-c", f"model_reasoning_effort={json.dumps(request.selection.reasoning)}"))
        config_values = (
            "mcp_servers={}",
            "notify=[]",
            "check_for_update_on_startup=false",
            # The built-in web search tool is read-only and stays separate from shell network access.
            'web_search="live"',
            self._permissions(request),
            'default_permissions="remix_reviewer"',
            "allow_login_shell=false",
            'shell_environment_policy.inherit="core"',
            "shell_environment_policy.ignore_default_excludes=false",
            'shell_environment_policy.exclude=["CODEX_HOME","CODEX_ACCESS_TOKEN","CODEX_API_KEY","OPENAI_API_KEY"]',
            "shell_environment_policy.set={}",
        )
        config_args = tuple(item for value in config_values for item in ("-c", value))
        # Project rules and agent documents load from the request's bounded invoking-context
        # snapshot. A reviewed checkout never supplies instructions. Hooks, plugins, memories,
        # apps, shell snapshot, and nested subagents stay disabled for determinism.
        argv = (
            *readiness.command,
            "exec",
            *selection,
            "--ephemeral",
            "--strict-config",
            "--disable",
            "apps",
            "--disable",
            "hooks",
            "--disable",
            "plugins",
            "--disable",
            "memories",
            "--disable",
            "multi_agent",
            "--disable",
            "shell_snapshot",
            *config_args,
            "--output-schema",
            str(request.schema_path),
            "-",
        )
        return WorkerSpec(
            request.worker_id,
            argv,
            request.project_root,
            clean_environment(),
            request.prompt_path,
            request.stdout_path,
            request.stderr_path,
        )

    def decode(self, stdout_path: Path) -> dict:
        """Read Codex's bare receipt object."""
        try:
            payload = json.loads(stdout_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("Codex worker returned malformed JSON") from error
        if not isinstance(payload, dict):
            raise ValueError("Codex worker did not return a receipt object")
        return payload

    def usage(self, stdout_path: Path, stderr_path: Path) -> dict[str, int]:
        """Parse total tokens used from Codex output logs."""
        text = ""
        for path in (stderr_path, stdout_path):
            try:
                if path.is_file():
                    text += "\n" + path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                pass
        if not text:
            return {}
        match = re.search(r"(?i)tokens\s+used[\s\n:]+([0-9,]+)", text)
        if not match:
            return {}
        try:
            return {"total": int(match.group(1).replace(",", ""))}
        except ValueError:
            return {}

    def needs_user_action(self, returncode: int, stdout: str, stderr: str) -> bool:
        """Recognize explicit Codex permission errors without scanning echoed prompts."""
        if super().needs_user_action(returncode, stdout, stderr):
            return True
        markers = ("permission denied", "approval required")
        error_lines = (
            line.lower()
            for line in stderr.splitlines()
            if line.lstrip().lower().startswith(("error:", '"code":', '"message":'))
        )
        return any(marker in line for line in error_lines for marker in markers)

    @staticmethod
    def _permissions(request: WorkerRequest) -> str:
        paths = {request.worker_cwd, request.project_root, *request.read_paths}
        resolved = [path.resolve(strict=True) for path in paths]
        roots = sorted(str(path) for path in resolved if path.is_dir())
        files = sorted(str(path) for path in resolved if path.is_file())
        if len(roots) + len(files) != len(resolved):
            raise RuntimeError("Codex permission path is not a regular file or directory")
        workspace_roots = ",".join(f"{json.dumps(path)}=true" for path in roots)
        filesystem = [
            f"{json.dumps(':minimal')}={json.dumps('read')}",
            f"{json.dumps(':workspace_roots')}={{{json.dumps('.')}={json.dumps('read')}}}",
            *(f"{json.dumps(path)}={json.dumps('read')}" for path in files),
        ]
        return (
            "permissions={remix_reviewer={workspace_roots={"
            + workspace_roots
            + "},filesystem={"
            + ",".join(filesystem)
            + "},network={enabled=false}}}"
        )

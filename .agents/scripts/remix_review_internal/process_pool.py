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

import contextlib
import functools
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


__all__ = [
    "ProbeTimeout",
    "ProviderPool",
    "WorkerCompletion",
    "WorkerSpec",
    "clean_environment",
    "git_executable",
    "resolve_executable",
    "run_git",
    "run_probe",
]


class ProbeTimeout(TimeoutError):  # noqa: N818 - public contract
    """Report that one CLI probe exceeded its deadline."""


def clean_environment(source: dict[str, str] | None = None) -> dict[str, str]:
    """Return a child environment without Packman Python overrides."""
    environment = dict(os.environ if source is None else source)
    environment.pop("PYTHONHOME", None)
    environment.pop("PYTHONPATH", None)
    return environment


def resolve_executable(name: str) -> Path | None:
    """Resolve one PATH command."""
    value = shutil.which(name)
    return Path(value).resolve() if value else None


@functools.lru_cache(maxsize=1)
def git_executable() -> Path:
    """Resolve Git from PATH once."""
    executable = resolve_executable("git")
    if executable is None:
        raise RuntimeError("Git was not found on PATH.")
    return executable


def run_git(
    repository: Path,
    *args: str,
    check: bool = True,
    environment: dict[str, str] | None = None,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[bytes]:
    """Run Git in one repository."""
    return subprocess.run(
        [str(git_executable()), "-C", str(repository), *args],
        check=check,
        capture_output=True,
        env=environment,
        shell=False,
        timeout=timeout,
    )


def _terminate(process: subprocess.Popen[bytes], grace_seconds: float = 5.0) -> None:
    """Terminate one direct process, then kill it if needed."""
    if process.poll() is not None:
        return
    with contextlib.suppress(OSError):
        process.terminate()
    try:
        process.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(OSError):
            process.kill()
        process.wait(timeout=grace_seconds)


def run_probe(
    argv: tuple[str, ...],
    *,
    cwd: Path | None,
    environment: dict[str, str],
    deadline: float,
    stdin: bytes = b"",
) -> subprocess.CompletedProcess[bytes]:
    """Run one shell-free CLI probe."""
    if not argv:
        raise ValueError("CLI probe requires an executable")
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ProbeTimeout("CLI preflight deadline expired")
    process = subprocess.Popen(
        argv,
        cwd=cwd,
        env=environment,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
    )
    try:
        stdout, stderr = process.communicate(input=stdin, timeout=remaining)
    except subprocess.TimeoutExpired:
        # Termination cleanup is best effort: it must never replace the original failure.
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            _terminate(process)
        raise ProbeTimeout("CLI preflight deadline expired") from None
    except BaseException:
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            _terminate(process)
        raise
    return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)


@dataclass(frozen=True)
class WorkerSpec:
    """Describe one direct provider CLI process."""

    worker_id: str
    argv: tuple[str, ...]
    cwd: Path
    environment: dict[str, str]
    prompt_path: Path
    stdout_path: Path
    stderr_path: Path
    timeout_seconds: float = 600.0


@dataclass
class _WorkerHandle:
    """Own one direct provider CLI process."""

    spec: WorkerSpec
    process: subprocess.Popen[bytes]
    deadline: float

    def stop(self) -> None:
        """Stop this worker."""
        _terminate(self.process)


@dataclass(frozen=True)
class WorkerCompletion:
    """Describe one completed provider worker."""

    spec: WorkerSpec
    returncode: int
    timed_out: bool = False


class ProviderPool:
    """Bound direct provider CLI processes for one provider."""

    def __init__(self, limit: int) -> None:
        """Create one bounded pool that can lower and restore its own limit."""
        self.limit = max(1, limit)
        self.ceiling = self.limit
        self._active: dict[str, _WorkerHandle] = {}

    def relax(self) -> None:
        """Restore one worker slot after a success, up to the configured ceiling."""
        self.limit = min(self.ceiling, self.limit + 1)

    def start(self, spec: WorkerSpec) -> _WorkerHandle:
        """Start one fresh worker process."""
        if self.available_slots() < 1:
            raise RuntimeError("provider pool is full")
        with contextlib.ExitStack() as files:
            prompt = files.enter_context(spec.prompt_path.open("rb"))
            stdout = files.enter_context(spec.stdout_path.open("xb"))
            stderr = files.enter_context(spec.stderr_path.open("xb"))
            process = subprocess.Popen(
                spec.argv,
                cwd=spec.cwd,
                env=spec.environment,
                stdin=prompt,
                stdout=stdout,
                stderr=stderr,
                shell=False,
            )
        handle = _WorkerHandle(spec, process, time.monotonic() + spec.timeout_seconds)
        self._active[spec.worker_id] = handle
        return handle

    def poll(self) -> tuple[WorkerCompletion, ...]:
        """Collect finished or timed-out workers."""
        done = []
        now = time.monotonic()
        for worker_id, handle in tuple(self._active.items()):
            timed_out = handle.process.poll() is None and now >= handle.deadline
            if timed_out:
                handle.stop()
            if handle.process.poll() is not None:
                self._active.pop(worker_id)
                done.append(WorkerCompletion(handle.spec, handle.process.returncode, timed_out))
        return tuple(done)

    def terminate_all(self) -> None:
        """Stop every active worker, and report any worker that refuses to stop."""
        failures = []
        for handle in tuple(self._active.values()):
            try:
                handle.stop()
            except (OSError, subprocess.SubprocessError) as error:
                failures.append(f"{handle.spec.worker_id}: {error}")
        for failure in failures:
            print(f"[remix-review] worker could not be stopped: {failure}", file=sys.stderr)
        # Reap the workers that stopped. A worker that already refused `stop` raises here too,
        # and that retry must not abort teardown.
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            self.poll()

    def available_slots(self) -> int:
        """Return currently available worker slots."""
        return max(0, self.limit - len(self._active))

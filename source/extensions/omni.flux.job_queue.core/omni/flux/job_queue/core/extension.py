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

import pathlib

import carb
import carb.tokens
from omni.ext import IExt

from .core import JobQueueCore
from .interface import QueueInterface

__all__ = ("FluxJobQueueCoreExtension", "get_job_queue")

_core: JobQueueCore | None = None


def _get_queue_db_path() -> str:
    """Return the persistent production queue path and create its parent directory.

    Returns:
        Absolute path to the production SQLite database.

    Raises:
        RuntimeError: If the application documents token cannot be resolved.
    """
    documents = carb.tokens.get_tokens_interface().resolve("${app_documents}")
    if not documents:
        raise RuntimeError("Could not resolve ${app_documents} path")
    db_path = pathlib.Path(documents) / "data" / "job_queue" / "job_queue.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return str(db_path)


def get_job_queue() -> QueueInterface:
    """Return the process-wide job queue.

    Returns:
        The shared queue interface.

    Raises:
        RuntimeError: If the extension has not started.
    """
    if _core is None:
        raise RuntimeError("Job queue core extension is not started")
    return _core.queue


class FluxJobQueueCoreExtension(IExt):
    """Own the process-wide queue and apply-handler runtime."""

    def on_startup(self, _ext_id: str) -> None:
        """Recover the shared queue and create its apply runtime.

        Args:
            _ext_id: Kit extension identifier.

        Raises:
            RuntimeError: If the app documents path cannot be resolved.
        """
        global _core
        carb.log_info("[omni.flux.job_queue.core] Startup")
        _core = JobQueueCore(_get_queue_db_path())

    def on_shutdown(self) -> None:
        """Release the shared queue and begin apply-runtime cleanup."""
        global _core
        carb.log_info("[omni.flux.job_queue.core] Shutdown")
        if _core is not None:
            _core.destroy()
        _core = None

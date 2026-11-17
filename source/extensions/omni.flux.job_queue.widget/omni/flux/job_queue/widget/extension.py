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

import carb
import omni.ext

from .display_adapter_registry import DisplayAdapterRegistry
from .notifications import JobResultNotifier

__all__ = ("FluxJobQueueWidgetExtension", "get_display_adapter_registry", "get_job_result_notifier")

_EXTENSION_NOT_STARTED_MESSAGE = "Job queue widget extension is not started"

_registry: DisplayAdapterRegistry | None = None
_result_notifier: JobResultNotifier | None = None


def get_display_adapter_registry() -> DisplayAdapterRegistry:
    """Return the shared display-adapter registry.

    Returns:
        The Display Adapter Registry instance.

    Raises:
        RuntimeError: If the extension has not started.
    """
    if _registry is None:
        raise RuntimeError(_EXTENSION_NOT_STARTED_MESSAGE)
    return _registry


def get_job_result_notifier() -> JobResultNotifier:
    """Return the shared result notifier.

    Raises:
        RuntimeError: If the extension has not started or has shut down.
    """
    if _result_notifier is None:
        raise RuntimeError(_EXTENSION_NOT_STARTED_MESSAGE)
    return _result_notifier


class FluxJobQueueWidgetExtension(omni.ext.IExt):
    """Own the shared job queue widget registry and result notifier."""

    def on_startup(self, _ext_id: str) -> None:
        """Create the shared registry and result notifier.

        Args:
            _ext_id: Kit extension identifier.
        """
        global _registry, _result_notifier
        carb.log_info("[omni.flux.job_queue.widget] Startup")
        _registry = DisplayAdapterRegistry()
        _result_notifier = JobResultNotifier()

    def on_shutdown(self) -> None:
        """Destroy the shared registry and result notifier."""
        global _registry, _result_notifier
        carb.log_info("[omni.flux.job_queue.widget] Shutdown")
        if _result_notifier:
            _result_notifier.destroy()
        _result_notifier = None
        if _registry:
            _registry.destroy()
        _registry = None

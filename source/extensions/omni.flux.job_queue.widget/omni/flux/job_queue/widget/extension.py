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

__all__ = ("FluxJobQueueWidgetExtension", "get_display_adapter_registry")

_registry: DisplayAdapterRegistry | None = None


def get_display_adapter_registry() -> DisplayAdapterRegistry:
    """Return the shared display-adapter registry.

    Returns:
        The Display Adapter Registry instance.

    Raises:
        RuntimeError: If the extension has not started.
    """
    if _registry is None:
        raise RuntimeError("Job queue widget extension is not started")
    return _registry


class FluxJobQueueWidgetExtension(omni.ext.IExt):
    """Owns process-wide job queue widget registries."""

    def on_startup(self, _ext_id: str) -> None:
        """Create the shared display-adapter registry.

        Args:
            _ext_id: Kit extension identifier.
        """
        global _registry
        carb.log_info("[omni.flux.job_queue.widget] Startup")
        _registry = DisplayAdapterRegistry()

    def on_shutdown(self) -> None:
        """Destroy the shared display-adapter registry."""
        global _registry
        carb.log_info("[omni.flux.job_queue.widget] Shutdown")
        if _registry:
            _registry.destroy()
        _registry = None

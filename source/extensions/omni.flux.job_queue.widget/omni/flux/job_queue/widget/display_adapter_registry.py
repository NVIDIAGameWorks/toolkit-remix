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

__all__ = ["DisplayAdapterRegistry"]

import carb
from omni.flux.factory.base import FactoryBase
from omni.flux.job_queue.core.job import Job

from .display_adapter_base import JobDisplayAdapter


class DisplayAdapterRegistry(FactoryBase[JobDisplayAdapter]):
    """Resolve one display adapter for each exact concrete job type."""

    def __init__(self):
        """Initialize exact-type adapter registrations."""
        super().__init__()
        self._adapters: dict[type[Job], JobDisplayAdapter] = {}

    def register(self, adapter_class: type[JobDisplayAdapter]) -> None:
        """Register one adapter for its declared exact job type.

        Args:
            adapter_class: Adapter class whose ``job_type`` becomes resolvable.

        Raises:
            ValueError: If another adapter already owns the exact job type or name.
        """
        existing_name = self.get_plugin_from_name(adapter_class.name)
        if existing_name is not None and existing_name is not adapter_class:
            raise ValueError(
                f"Display adapter name {adapter_class.name!r} is already registered by {existing_name.__name__}"
            )
        existing = self._adapters.get(adapter_class.job_type)
        if existing is not None and type(existing) is adapter_class:
            return
        if existing is not None:
            raise ValueError(
                f"Job type {adapter_class.job_type.__name__} already uses display adapter {type(existing).__name__}"
            )
        self.register_plugins([adapter_class])
        self._adapters[adapter_class.job_type] = adapter_class()

    def unregister(self, adapter_class: type[JobDisplayAdapter]) -> None:
        """Unregister a display adapter class and discard its cached instance.

        Args:
            adapter_class: Previously registered adapter class.
        """
        self.unregister_plugins([adapter_class])
        adapter = self._adapters.get(adapter_class.job_type)
        if adapter is not None and type(adapter) is adapter_class:
            self._adapters.pop(adapter_class.job_type)

    def destroy(self) -> None:
        """Release plugin metadata and cached stateless adapters."""
        super().destroy()
        self._adapters.clear()

    def get_adapter(self, job: Job) -> JobDisplayAdapter | None:
        """Return the cached adapter registered for the job's exact type.

        Args:
            job: Job whose exact concrete type is resolved.

        Returns:
            Cached stateless adapter, or None when no exact registration exists.
        """
        job_type = type(job)
        adapter = self._adapters.get(job_type)
        if adapter is not None:
            return adapter
        carb.log_warn(
            f"No display adapter registered for job type {job_type.__name__} "
            f"(job_id={job.job_id}). The job will display with default values."
        )
        return None

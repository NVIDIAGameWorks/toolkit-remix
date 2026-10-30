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

__all__ = ["AssetModifierFactory"]

import dataclasses
import enum
from collections.abc import Callable
from functools import partial
from typing import Any

from omni.flux.factory.base import FactoryBase
from omni.flux.job_queue.core.persistence import PersistenceCodec, get_registry
from omni.flux.utils.common import Event, EventSubscription

from .job import AssetModifierJob
from .plugins.base import AssetModifierBase


class AssetModifierFactory(FactoryBase[AssetModifierBase]):
    """Register modifier plugins and the codecs that persist their jobs and enum inputs."""

    def __init__(self):
        """Create the change event that registration and settings changes trigger."""
        super().__init__()
        self._changed = Event(copy=True)

    def subscribe_changed(self, callback: Callable[[], None]) -> EventSubscription:
        """Call back after a registration or settings change until the subscription is released."""
        return EventSubscription(self._changed, callback)

    def notify_changed(self) -> None:
        """Notify subscribers that the registered modifiers or their settings changed."""
        self._changed()

    def register_plugins(self, plugins: list[type[AssetModifierBase]]) -> None:
        """Register modifiers and their codecs. Codecs outlive unregistration so queued jobs can restore.

        Each Python type has one codec, so an enum shared by several inputs or modifiers registers once. A new job class
        under a registered modifier name raises the registry's conflict error, because queued jobs keep the old class.
        """
        registry = get_registry()
        codecs = {}
        for plugin in plugins:
            codecs[plugin.job_type] = PersistenceCodec(
                f"asset_modifiers.{plugin.name}",
                plugin.job_type,
                self._encode_job,
                partial(self._decode_job, plugin.job_type),
            )
            for item in plugin.inputs:
                if issubclass(item.value_type, enum.Enum):
                    name = f"asset_modifiers.{item.value_type.__module__}.{item.value_type.__qualname__}"
                    codecs[item.value_type] = PersistenceCodec(name, item.value_type)
        registry.register_codecs(
            [codec for value_type, codec in codecs.items() if registry.get_name(value_type) is None]
        )
        super().register_plugins(plugins)
        self._changed()

    def unregister_plugins(self, plugins: list[type[AssetModifierBase]]) -> None:
        """Remove modifier choices and keep their codecs for queued jobs."""
        super().unregister_plugins(plugins)
        self._changed()

    def destroy(self) -> None:
        """Release the registered modifiers and subscribers."""
        super().destroy()
        self._changed.clear()

    @staticmethod
    def _encode_job(job: AssetModifierJob) -> dict[str, Any]:
        """Persist every constructor field of a modifier job by name, so keyword-only fields restore too."""
        return {field.name: getattr(job, field.name) for field in dataclasses.fields(job) if field.init}

    @staticmethod
    def _decode_job(job_type: type[AssetModifierJob], payload: dict[str, Any]) -> AssetModifierJob:
        """Restore a modifier job from its persisted fields."""
        return job_type(**payload)

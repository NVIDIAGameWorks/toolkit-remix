"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

import omni.usd
from omni.flux.utils.common.interactive_usd_notices import (
    AggregatedObjectsChangedNotice as _AggregatedObjectsChangedNotice,
)
from omni.flux.utils.common.interactive_usd_notices import ListenerSubscription as _ListenerSubscription
from omni.flux.utils.common.interactive_usd_notices import register_objects_changed_listener as _register_listener
from pxr import Usd
from pydantic import Field, PrivateAttr

from .base import StageManagerUSDListenerPlugin as _StageManagerUSDListenerPlugin

_ObjectsChangedNotice = Usd.Notice.ObjectsChanged | _AggregatedObjectsChangedNotice


class StageManagerUSDNoticeListenerPlugin(_StageManagerUSDListenerPlugin[_ObjectsChangedNotice]):
    """Listener triggered whenever a USD notice is broadcast."""

    event_type: type[Usd.Notice.ObjectsChanged] = Field(default_factory=lambda: Usd.Notice.ObjectsChanged, exclude=True)

    _usd_listener: _ListenerSubscription | None = PrivateAttr(default=None)

    def setup(self):
        """Register the shared USD notice listener for the configured context."""

        super().setup()
        stage = omni.usd.get_context(self._context_name).get_stage()
        self._usd_listener = _register_listener(
            stage,
            self._on_usd_event,
        )

    def cleanup(self):
        """Revoke the shared USD notice listener."""

        super().cleanup()
        if self._usd_listener:
            self._usd_listener.Revoke()
            self._usd_listener = None

    def _on_usd_event(self, notice: _ObjectsChangedNotice, _: Usd.Stage):
        """Forward a USD notice to Stage Manager subscribers.

        Args:
            notice: USD object-change notice, or aggregated notice flushed after an interaction.
            _: Stage that emitted the notice.
        """

        self._event_occurred(notice)

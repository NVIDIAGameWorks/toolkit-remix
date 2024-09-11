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
from pxr import Tf, Usd
from pydantic import PrivateAttr

from .base import StageManagerUSDListenerPlugin as _StageManagerUSDListenerPlugin


class StageManagerUSDNoticeListenerPlugin(_StageManagerUSDListenerPlugin[Usd.Notice.ObjectsChanged]):
    """
    A listener triggered whenever a USD notice is broadcast.
    """

    event_type: type = Usd.Notice.ObjectsChanged

    _usd_listener = PrivateAttr()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._usd_listener = None

    def setup(self):
        stage = omni.usd.get_context(self.context_name).get_stage()
        self._usd_listener = Tf.Notice.Register(Usd.Notice.ObjectsChanged, self._on_usd_event, stage)

    def _on_usd_event(self, notice: Usd.Notice.ObjectsChanged, _: Usd.Stage):
        self._event_occurred(notice)

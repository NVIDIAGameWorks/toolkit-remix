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

import carb
import carb.settings
import omni.ext
from omni.flux.service.factory import get_instance as _get_service_factory_instance

from .routes import ROUTE_SERVICES as _ROUTE_SERVICES
from .service import CoreService as _CoreService

_AGENTIC_ENABLED_SETTING = "/exts/lightspeed.trex.service.core/agentic_enabled"


class TrexCoreServiceExtension(omni.ext.IExt):
    def __init__(self):
        super().__init__()

        self._core_service = None
        self._routes_registered = False

    def on_startup(self, _ext_id):
        carb.log_info("[lightspeed.trex.service.core] Startup")

        # The agentic routes are opt-in, and must register before CoreService resolves the
        # configured service names against the factory. While the gate is off they stay
        # unregistered, which CoreService skips rather than treats as fatal.
        self._routes_registered = carb.settings.get_settings().get_as_bool(_AGENTIC_ENABLED_SETTING)
        if self._routes_registered:
            _get_service_factory_instance().register_plugins(_ROUTE_SERVICES)

        self._core_service = _CoreService()

    def on_shutdown(self):
        carb.log_info("[lightspeed.trex.service.core] Shutdown")

        if self._core_service:
            self._core_service.destroy()
            self._core_service = None

        if self._routes_registered:
            _get_service_factory_instance().unregister_plugins(_ROUTE_SERVICES)
            self._routes_registered = False

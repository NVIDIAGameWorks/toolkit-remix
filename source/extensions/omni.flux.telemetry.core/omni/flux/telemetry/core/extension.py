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
import omni.ext

from .core import TelemetryCore as _TelemetryCore

_instance: _TelemetryCore = None


def get_telemetry_instance() -> _TelemetryCore:
    """
    Returns:
        The Telemetry core instance
    """
    return _instance


class TelemetryCoreExtension(omni.ext.IExt):

    def on_startup(self, _):
        global _instance
        carb.log_info("[omni.flux.telemetry.core] Startup")

        _instance = _TelemetryCore()

    def on_shutdown(self):
        global _instance
        carb.log_info("[omni.flux.telemetry.core] Shutdown")

        if _instance:
            _instance.destroy()
        _instance = None

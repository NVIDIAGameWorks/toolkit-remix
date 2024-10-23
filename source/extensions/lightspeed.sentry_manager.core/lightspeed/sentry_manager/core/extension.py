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

from .manager import SentryManager as _SentryManager

_manager = None


def get_instance():
    return _manager


class SentryExtension(omni.ext.IExt):
    def on_startup(self, _):
        global _manager
        carb.log_info("[lightspeed.sentry_manager.core] Startup")
        _manager = _SentryManager()

    def on_shutdown(self, _):
        carb.log_info("[lightspeed.sentry_manager.core] Shutdown")
        global _manager
        _manager = None

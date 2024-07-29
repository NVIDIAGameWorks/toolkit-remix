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

from .setup import Setup

_stagecraft_control_instance: Setup | None = None


def _create_instance():
    global _stagecraft_control_instance
    _stagecraft_control_instance = Setup()
    return _stagecraft_control_instance


def get_instance():
    return _stagecraft_control_instance


class TrexStageCraftControlExtension(omni.ext.IExt):
    """Create Final Configuration"""

    def on_startup(self, ext_id):
        carb.log_info("[lightspeed.trex.control.stagecraft] Startup")
        _create_instance()

    def on_shutdown(self):
        carb.log_info("[lightspeed.trex.control.stagecraft] Shutdown")
        global _stagecraft_control_instance
        if _stagecraft_control_instance:
            _stagecraft_control_instance.destroy()
        _stagecraft_control_instance = None

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

from .setup_ui import SetupUI

_SETUP_INSTANCE = None


def get_instance():
    return _SETUP_INSTANCE


class TrexSetupExtension(omni.ext.IExt):
    """Create Final Configuration"""

    def __init__(self):
        super().__init__()
        self._setup = None

    def on_startup(self, ext_id):
        global _SETUP_INSTANCE
        carb.log_info("[lightspeed.trex.app.setup] Startup")
        self._setup_ui = SetupUI()
        _SETUP_INSTANCE = self._setup_ui.get_window()

    def on_shutdown(self):
        carb.log_info("[lightspeed.trex.app.setup] Shutdown")
        self._setup_ui.destroy()
        global _SETUP_INSTANCE
        _SETUP_INSTANCE = None
        self._setup_ui = None

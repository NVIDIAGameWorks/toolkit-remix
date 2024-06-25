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

from .setup_ui import SetupUI as _SetupUI

_INSTANCE = None


def get_instance():
    return _INSTANCE


class ViewportMenuBarRenderExtension(omni.ext.IExt):
    """Create Final Configuration"""

    def on_startup(self, ext_id):
        global _INSTANCE
        carb.log_info("[lightspeed.trex.viewports.menubar.render] Startup")
        _INSTANCE = _SetupUI()

    def on_shutdown(self):
        carb.log_info("[lightspeed.trex.viewports.menubar.render] Shutdown")
        global _INSTANCE
        if _INSTANCE:
            _INSTANCE.destroy()
        _INSTANCE = None

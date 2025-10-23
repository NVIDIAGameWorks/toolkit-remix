"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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
import omni.kit
import omni.ui
from lightspeed.trex.contexts.setup import Contexts as _TrexContexts

from .workspace import HomePageWindow as _HomePageWindow


class TrexHomePageWindowExtension(omni.ext.IExt):
    """Home Page Window Extension"""

    def on_startup(self, ext_id):
        carb.log_info("[lightspeed.trex.home.widget] Startup")
        self._workspace_window = _HomePageWindow(_TrexContexts.STAGE_CRAFT.value, show_dock_tab_bars=False)
        self._workspace_window.create_window()
        omni.ui.Workspace.set_show_window_fn(self._workspace_window.title, self._workspace_window.show_window_fn)

    def on_shutdown(self):
        carb.log_info("[lightspeed.trex.home.widget] Shutdown")
        self._workspace_window.cleanup()
        omni.ui.Workspace.set_show_window_fn(self._workspace_window.title, lambda *_: None)

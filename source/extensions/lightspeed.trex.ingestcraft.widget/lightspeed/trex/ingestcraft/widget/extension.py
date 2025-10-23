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
import omni.kit.app
import omni.ui

from .workspace import IngestCraftWindow as _IngestCraftWindow

_DEFAULT_LAYOUT_EXTENSION = "/app/trex/default_layout_extension"


class TrexIngestCraftWindowExtension(omni.ext.IExt):
    """Create Final Configuration"""

    def on_startup(self, ext_id):
        carb.log_info("[lightspeed.trex.ingestcraft.widget] Startup")
        self._workspace_window = _IngestCraftWindow()
        self._workspace_window.create_window()
        omni.ui.Workspace.set_show_window_fn(self._workspace_window.title, self._workspace_window.show_window_fn)

    def on_shutdown(self):
        carb.log_info("[lightspeed.trex.ingestcraft.widget] Shutdown")
        self._workspace_window.cleanup()
        omni.ui.Workspace.set_show_window_fn(self._workspace_window.title, lambda *_: None)

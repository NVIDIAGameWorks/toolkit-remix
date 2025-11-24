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
from lightspeed.common.constants import LayoutFiles as _LayoutFiles
from lightspeed.trex.contexts import get_instance as trex_contexts_instance
from lightspeed.trex.contexts.setup import Contexts as TrexContexts
from lightspeed.trex.utils.widget.quicklayout import load_layout
from omni.flux.utils.widget.resources import get_quicklayout_config as _get_quicklayout_config

from .workspace import TextureCraftWindow as _TextureCraftWindow

_DEFAULT_LAYOUT = "/app/trex/default_layout"


class TextureCraftLayoutExtension(omni.ext.IExt):
    """Create Final Configuration"""

    def on_startup(self, ext_id):
        carb.log_info("[lightspeed.trex.texturecraft.widget] Startup")
        # create the TextureCraft configurator context
        trex_contexts_instance().create_usd_context(TrexContexts.TEXTURE_CRAFT)

        self._workspace_window = _TextureCraftWindow(None)
        self._workspace_window.create_window()
        omni.ui.Workspace.set_show_window_fn(self._workspace_window.title, self._workspace_window.show_window_fn)

        def load_default_layout(*args):
            settings = carb.settings.get_settings()
            default_layout = settings.get(_DEFAULT_LAYOUT) or ""
            if default_layout == "texturecraft":
                load_layout(_get_quicklayout_config(_LayoutFiles.TEXTURECRAFT))

            self.sub_app_ready = None

        startup_event_stream = omni.kit.app.get_app().get_startup_event_stream()
        self.sub_app_ready = startup_event_stream.create_subscription_to_pop_by_type(
            omni.kit.app.EVENT_APP_READY, load_default_layout, name="Window Menu Item - App Ready"
        )

    def on_shutdown(self):
        carb.log_info("[lightspeed.trex.texturecraft.widget] Shutdown")
        self._workspace_window.cleanup()
        omni.ui.Workspace.set_show_window_fn(self._workspace_window.title, lambda *_: None)

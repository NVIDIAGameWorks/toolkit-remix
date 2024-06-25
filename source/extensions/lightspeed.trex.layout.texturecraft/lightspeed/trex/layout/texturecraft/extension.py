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
from lightspeed.trex.contexts import get_instance as trex_contexts_instance
from lightspeed.trex.contexts.setup import Contexts as TrexContexts

from .setup_ui import SetupUI

_DEFAULT_LAYOUT_EXTENSION = "/app/trex/default_layout_extension"
_SETUP_INSTANCE = None


def get_instance():
    return _SETUP_INSTANCE


class TextureCraftLayoutExtension(omni.ext.IExt):
    """Create Final Configuration"""

    def on_startup(self, ext_id):
        global _SETUP_INSTANCE
        carb.log_info("[lightspeed.trex.layout.texturecraft] Startup")
        # create the TextureCraft configurator context
        trex_contexts_instance().create_usd_context(TrexContexts.TEXTURE_CRAFT)

        _SETUP_INSTANCE = SetupUI(ext_id)
        settings = carb.settings.get_settings()
        default_layout = settings.get(_DEFAULT_LAYOUT_EXTENSION)
        if (default_layout and ext_id.startswith(default_layout)) or not default_layout:
            _SETUP_INSTANCE.create_layout()

    def on_shutdown(self):
        global _SETUP_INSTANCE
        carb.log_info("[lightspeed.trex.layout.texturecraft] Shutdown")
        _SETUP_INSTANCE.destroy()
        _SETUP_INSTANCE = None

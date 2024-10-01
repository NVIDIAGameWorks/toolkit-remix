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
from omni import ui

from .window import FeatureFlagsWindow

_WINDOW_INSTANCE = None


def get_instance() -> FeatureFlagsWindow | None:
    """
    Returns:
        A singleton instance of the feature flags window.
    """
    return _WINDOW_INSTANCE


class FluxFeatureFlagsWindowExtension(omni.ext.IExt):
    """Create Final Configuration"""

    def on_startup(self, ext_id):
        global _WINDOW_INSTANCE
        carb.log_info("[omni.flux.feature_flags.window] Startup")

        _WINDOW_INSTANCE = FeatureFlagsWindow(
            visible=False,
            dockPreference=ui.DockPreference.DISABLED,
            flags=(
                ui.WINDOW_FLAGS_NO_COLLAPSE
                | ui.WINDOW_FLAGS_NO_MOVE
                | ui.WINDOW_FLAGS_NO_RESIZE
                | ui.WINDOW_FLAGS_MODAL
            ),
        )

    def on_shutdown(self):
        global _WINDOW_INSTANCE
        carb.log_info("[omni.flux.feature_flags.window] Shutdown")

        if _WINDOW_INSTANCE:
            _WINDOW_INSTANCE.destroy()
        _WINDOW_INSTANCE = None

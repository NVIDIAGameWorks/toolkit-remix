"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = ["StageManagerComfyListenerPluginsExtension"]

from omni.flux.stage_manager.factory import get_instance
from omni.ext import IExt

from .comfy_listener import StageManagerComfyListenerPlugin


class StageManagerComfyListenerPluginsExtension(IExt):
    """Extension that registers ComfyUI listener plugins with the Stage Manager factory."""

    _PLUGINS = [StageManagerComfyListenerPlugin]

    def on_startup(self, ext_id):
        """Register listener plugins when the extension starts.

        Args:
            ext_id: Identifier assigned to this extension; unused.
        """
        get_instance().register_plugins(self._PLUGINS)

    def on_shutdown(self):
        """Unregister listener plugins on extension shutdown."""
        get_instance().unregister_plugins(self._PLUGINS)

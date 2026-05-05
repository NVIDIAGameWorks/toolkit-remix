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

__all__ = ["RemixStageManagerUSDInteractionPluginsExtension"]

import omni.ext
from omni.flux.stage_manager.factory import get_instance

from .all_categories import RemixAllCategoriesInteractionPlugin
from .all_lights import RemixAllLightsInteractionPlugin
from .all_materials import RemixAllMaterialsInteractionPlugin
from .all_meshes import RemixAllMeshesInteractionPlugin
from .all_prims import RemixAllPrimsInteractionPlugin
from .all_skeletons import RemixAllSkeletonsInteractionPlugin
from .all_tags import RemixAllTagsInteractionPlugin


class RemixStageManagerUSDInteractionPluginsExtension(omni.ext.IExt):
    """Extension that registers Remix USD interaction plugins with the Stage Manager factory."""

    _PLUGINS = [
        RemixAllCategoriesInteractionPlugin,
        RemixAllLightsInteractionPlugin,
        RemixAllMaterialsInteractionPlugin,
        RemixAllMeshesInteractionPlugin,
        RemixAllPrimsInteractionPlugin,
        RemixAllSkeletonsInteractionPlugin,
        RemixAllTagsInteractionPlugin,
    ]

    def on_startup(self, ext_id):
        """
        Register interaction plugins on extension startup.

        Args:
            ext_id: The extension identifier
        """
        get_instance().register_plugins(self._PLUGINS)

    def on_shutdown(self):
        """Unregister interaction plugins on extension shutdown."""
        get_instance().unregister_plugins(self._PLUGINS)

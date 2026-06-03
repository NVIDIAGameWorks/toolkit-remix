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

__all__ = ["LightManipulatorExtension"]

import carb
import omni.ext

try:
    from omni.kit.viewport.menubar.display import get_instance as _get_display_menubar_instance

    from .viewport_menu import (
        CUSTOM_MANIPULATORS_CATEGORY,
        CUSTOM_MANIPULATORS_SECTION,
        build_collection_item,
    )
except ImportError:
    carb.log_info(
        "[lightspeed.ui_scene.light_manipulator] omni.kit.viewport.menubar.display not available; "
        "Light Manipulator settings will not appear in the viewport Display dropdown."
    )
    _get_display_menubar_instance = None
    CUSTOM_MANIPULATORS_CATEGORY = None
    CUSTOM_MANIPULATORS_SECTION = None
    build_collection_item = None


class LightManipulatorExtension(omni.ext.IExt):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._custom_manipulators_item = None

    def on_startup(self, ext_id):
        carb.log_info("[lightspeed.ui_scene.light_manipulator] Lightspeed Light Manipulators startup")
        if _get_display_menubar_instance is None:
            return
        display_inst = _get_display_menubar_instance()
        if display_inst is not None:
            self._custom_manipulators_item = build_collection_item()
            display_inst.register_custom_category_item(
                CUSTOM_MANIPULATORS_CATEGORY,
                self._custom_manipulators_item,
                CUSTOM_MANIPULATORS_SECTION,
            )

    def on_shutdown(self):
        carb.log_info("[lightspeed.ui_scene.light_manipulator] Lightspeed Light Manipulators shutdown")
        if self._custom_manipulators_item is not None and _get_display_menubar_instance is not None:
            display_inst = _get_display_menubar_instance()
            if display_inst is not None:
                display_inst.deregister_custom_category_item(
                    CUSTOM_MANIPULATORS_CATEGORY, self._custom_manipulators_item
                )
            self._custom_manipulators_item = None

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

import asyncio

import omni.ext
import omni.kit.menu.utils as omni_utils
import omni.usd
from lightspeed.asset_capture_localizer.window import get_instance
from omni.kit.menu.utils import MenuItemDescription


class AssetCaptureLocalizerMenuExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        self.__create_save_menu()

    def __create_save_menu(self):
        self._tools_manager_menus = [
            MenuItemDescription(
                name="Toggle asset capture localizer window",
                onclick_fn=self.__clicked,
                glyph="none.svg",
            )
        ]
        omni_utils.add_menu_items(self._tools_manager_menus, "Utils")

    def on_shutdown(self):
        omni_utils.remove_menu_items(self._tools_manager_menus, "Utils")

    @omni.usd.handle_exception
    async def _show(self):
        get_instance().toggle_window()

    def __clicked(self):
        asyncio.ensure_future(self._show())

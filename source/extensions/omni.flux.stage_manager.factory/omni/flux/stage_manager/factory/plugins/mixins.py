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

import abc

import omni.kit.context_menu


class StageManagerMenuMixin(abc.ABC):
    """
    A mixin for stage manager plugins that adds the ability to register a menu to the stage manager.
    """

    _menu_subscriptions: list = []

    def __init_subclass__(cls, *args, **kwargs):
        super().__init_subclass__(*args, **kwargs)
        # Ensure each subclass gets its own subscription list
        cls._menu_subscriptions = []

    @classmethod
    def register_menu(cls):
        """
        Register the menu to omni.kit.context_menu
        """
        cls._menu_subscriptions.clear()
        for payload, group, name in cls._get_menu_items():
            cls._menu_subscriptions.append(omni.kit.context_menu.add_menu(payload, group, name))

    @classmethod
    def unregister_menu(cls):
        """
        Unregister the menu from omni.kit.context_menu
        """
        for sub in cls._menu_subscriptions:
            sub.release()
        cls._menu_subscriptions.clear()

    @classmethod
    @abc.abstractmethod
    def _get_menu_items(cls) -> list[tuple[dict, str, str]]:
        pass

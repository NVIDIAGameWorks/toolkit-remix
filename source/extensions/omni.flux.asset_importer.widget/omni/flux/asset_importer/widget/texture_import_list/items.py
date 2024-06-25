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

from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common.omni_url import OmniUrl as _OmniUrl

from ..common.items import ImportItem as _ImportItem


class TextureImportItem(_ImportItem):
    def __init__(self, url: _OmniUrl, texture_type: TextureTypes = TextureTypes.OTHER):
        super().__init__(url)

        self._default_attr = {
            "_texture_type": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._texture_type = texture_type

        # copy because if the type is wrong, we re-create/re-set the previous values, which will delete the current
        # event itself that is running.
        self.__item_texture_type_changed = _Event(copy=True)

    @property
    def texture_type(self) -> TextureTypes:
        return self._texture_type

    @texture_type.setter
    def texture_type(self, val) -> None:
        self._texture_type = val
        self.__item_texture_type_changed()

    def subscribe_item_texture_type_changed(self, func):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__item_texture_type_changed, func)

    def __repr__(self):
        return f"[{self.texture_type.name}] {self.path}"

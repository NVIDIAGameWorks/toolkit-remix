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

from typing import Any
from collections.abc import Callable

import carb
import carb.tokens
from omni import ui
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.common.omni_url import OmniUrl as _OmniUrl


class ImportItem(ui.AbstractItem):
    def __init__(self, url: _OmniUrl):
        super().__init__()

        self._default_attr = {
            "_path": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._path = url
        self.__item_changed = _Event(copy=True)

    def on_item_changed(self):
        self.__item_changed(self.path)

    def subscribe_item_changed(self, func: Callable[[_OmniUrl], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__item_changed, func)

    @staticmethod
    def is_valid(path: _OmniUrl, show_warning: bool = True) -> tuple[bool, str]:
        path = carb.tokens.get_tokens_interface().resolve(str(path))
        file_url = _OmniUrl(path)
        if not file_url.exists:
            message = f"The input file {file_url} does not exist"
            if show_warning:
                carb.log_warn(message)
            return False, message
        return True, f"{file_url} is ok"

    @property
    def path(self) -> _OmniUrl:
        return self._path

    @property
    def value_model(self) -> ui.SimpleStringModel:
        return ui.SimpleStringModel(str(self.path))

    def __repr__(self):
        return str(self.path)

    def destroy(self):
        _reset_default_attrs(self)

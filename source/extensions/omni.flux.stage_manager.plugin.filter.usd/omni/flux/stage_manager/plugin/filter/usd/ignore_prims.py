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

from omni import ui
from omni.flux.stage_manager.factory import StageManagerItem as _StageManagerItem
from omni.flux.utils.common import EventSubscription as _EventSubscription
from pydantic import Field, PrivateAttr

from .base import StageManagerUSDFilterPlugin as _StageManagerUSDFilterPlugin


class IgnorePrimsFilterPlugin(_StageManagerUSDFilterPlugin):
    display_name: str = "Ignore Prims"
    tooltip: str = "Filter out Omniverse prims.\nInput a comma-separated list of prim paths to ignore."

    ignore_prim_paths: set[str] = Field(
        set(),
        description=(
            "A set of prim paths to filter out. The filter will filter out the given prims paths and any children paths"
        ),
    )

    _string_field: ui.StringField = PrivateAttr()
    _value_changed_sub: _EventSubscription | None = PrivateAttr()

    def filter_predicate(self, item: _StageManagerItem) -> bool:
        is_valid = True
        for ignore_prim_path in self.ignore_prim_paths:
            if item.data.GetPath().HasPrefix(ignore_prim_path):
                is_valid = False
                break
        return is_valid

    def build_ui(self):  # noqa PLW0221
        with ui.HStack(spacing=ui.Pixel(8)):
            ui.Label(self.display_name, width=0)
            self._string_field = ui.StringField(width=ui.Pixel(300), height=ui.Pixel(24))

        self._string_field.model.set_value(",".join(self.ignore_prim_paths))
        self._value_changed_sub = self._string_field.model.subscribe_end_edit_fn(self._on_ignore_value_changed)

    def _on_ignore_value_changed(self, model: ui.AbstractValueModel):
        self.ignore_prim_paths = {p.strip() for p in model.as_string.split(",")}
        self._filter_items_changed()

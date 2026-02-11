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

__all__ = ("USDFloatSliderField",)

import omni.ui as ui
from omni.flux.property_widget_builder.delegates.float_value.slider import FloatSliderField

from ..items import USDAttributeItem as _USDAttributeItem


class USDFloatSliderField(FloatSliderField):
    """
    A FloatSliderField that will attempt to adjust it's min/max range using USD attribute metadata.
    """

    def adjust_min_max_range(self, item: _USDAttributeItem):
        """
        Attempts to adjust the sliders min/max range by inspecting the USD metadata.
        """
        # NOTE: We want to prefer *any* metadata values over the provided defaults.

        min_value = None
        max_value = None

        for attribute_path in item._attribute_paths:  # noqa: SLF001
            prim = item._stage.GetPrimAtPath(attribute_path.GetPrimPath())  # noqa: SLF001
            if prim.HasAttribute(attribute_path.name):
                attr = prim.GetAttribute(attribute_path.name)
                custom = attr.GetMetadata("customData")
                if custom is not None:
                    min_max_range = custom.get("range")
                    if min_max_range is not None:
                        meta_min_value = min_max_range.get("min")
                        if isinstance(meta_min_value, (int, float)):
                            if min_value is None:
                                min_value = meta_min_value
                            else:
                                min_value = min(min_value, meta_min_value)
                        meta_max_value = min_max_range.get("max")
                        if isinstance(meta_max_value, (int, float)):
                            if max_value is None:
                                max_value = meta_max_value
                            else:
                                max_value = max(max_value, meta_max_value)

        if min_value is not None:
            self.min_value = min_value
        if max_value is not None:
            self.max_value = max_value
        assert self.min_value < self.max_value, "Min value must be less than max value"

    def build_ui(self, item) -> list[ui.Widget]:
        self.adjust_min_max_range(item)
        return super().build_ui(item)

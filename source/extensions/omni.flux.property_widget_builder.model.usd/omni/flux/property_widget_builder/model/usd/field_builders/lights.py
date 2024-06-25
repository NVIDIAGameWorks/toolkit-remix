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

__all__ = ("LIGHT_FIELD_BUILDERS",)

from omni.flux.property_widget_builder.delegates.float_value.slider import FloatSliderField

from .base import USDBuilderList

LIGHT_FIELD_BUILDERS = USDBuilderList()


LIGHT_FIELD_BUILDERS.append_builder_by_attr_name("inputs:colorTemperature", FloatSliderField(2500.0, 8500.0))
LIGHT_FIELD_BUILDERS.append_builder_by_attr_name("inputs:exposure", FloatSliderField(0.0, 10.0))
LIGHT_FIELD_BUILDERS.append_builder_by_attr_name("inputs:intensity", FloatSliderField(0.0, 65000.0))
LIGHT_FIELD_BUILDERS.append_builder_by_attr_name("inputs:radius", FloatSliderField(0.0, 65000.0))
LIGHT_FIELD_BUILDERS.append_builder_by_attr_name("inputs:shaping:cone:angle", FloatSliderField(0.0, 360.0))
LIGHT_FIELD_BUILDERS.append_builder_by_attr_name("inputs:shaping:cone:softness", FloatSliderField(0.0, 10.0))
LIGHT_FIELD_BUILDERS.append_builder_by_attr_name("inputs:shaping:focus", FloatSliderField(0.0, 10.0))

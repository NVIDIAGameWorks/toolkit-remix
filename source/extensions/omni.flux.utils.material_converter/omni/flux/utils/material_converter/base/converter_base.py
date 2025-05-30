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

from typing import List

from omni.flux.utils.material_converter.utils import MaterialConverterUtils as _MaterialConverterUtils
from pxr import Sdr, Usd
from pydantic import BaseModel, ConfigDict, field_validator

from .attribute_base import AttributeBase


class ConverterBase(BaseModel):
    input_material_prim: Usd.Prim
    output_mdl_subidentifier: str
    attributes: List[AttributeBase]

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @field_validator("input_material_prim", mode="before")
    @classmethod
    def input_material_prim_valid(cls, v):
        if not v.IsValid():
            raise ValueError(f"Prim '{v.GetPath()}' is invalid")
        return v

    @field_validator("output_mdl_subidentifier", mode="before")
    @classmethod
    def output_mdl_valid(cls, v):
        library_subidentifiers = [u.stem for u in _MaterialConverterUtils.get_material_library_shader_urls()]
        if v not in library_subidentifiers:
            # check if this is not just a regular USD node like UsdPreviewSurface
            sdr_registry = Sdr.Registry()
            if v not in sdr_registry.GetNodeNames():
                raise ValueError(
                    f"The subidentifier ({v}) does not exist in the material library. If using non-default shaders, "
                    f"add your shader path to the following setting "
                    f"'{_MaterialConverterUtils.MATERIAL_LIBRARY_SETTING_PATH}'. Currently available shaders are: "
                    f"{', '.join(library_subidentifiers) or 'None'}"
                )
        return v

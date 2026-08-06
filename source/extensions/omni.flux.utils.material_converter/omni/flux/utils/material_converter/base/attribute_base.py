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

from collections.abc import Callable
from typing import Any

from pxr import Sdf, Usd
from pydantic import BaseModel, ConfigDict, Field


def _translate(input_attr_value: Any, input_attr: Usd.Attribute) -> tuple[Sdf.ValueTypeName, Any]:
    """
    Default translate_fn Implementation that returns the input attribute type and value unchanged.

    Args:
        input_attr_value: The input attribute value.
        input_attr: The input attribute.

    Returns:
        The input attribute type and value.
    """
    return input_attr.GetTypeName(), input_attr_value


class AttributeBase(BaseModel):
    """Represent an attribute mapping between input and output shaders."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Attribute name used on the input shader
    input_attr_name: str
    # Attribute name used on the output shader
    output_attr_name: str
    # Explicit type used when creating the output attribute from a default value
    output_attr_type: Sdf.ValueTypeName | None = None
    # Value used when the input attribute does not exist
    output_default_value: Any | None = None
    # Function used to translate the input attribute into the output type and value
    translate_fn: Callable[[Any, Usd.Attribute], tuple[Sdf.ValueTypeName, Any]] = Field(default=_translate)
    # tell if the attribute is a real attribute that exists by default, or if this is a fake one that was created
    fake_attribute: bool = False

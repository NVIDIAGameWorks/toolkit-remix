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

from typing import Any, Callable, Optional, Tuple

from pxr import Sdf, Usd
from pydantic import BaseModel, Field


def _translate(input_attr_value: Any, input_attr: Usd.Attribute) -> Any:
    """
    Allows translating the input value to produce the output value

    Args:
        input_attr_value: The input attribute value
        input_attr: The input attribute

    Returns:
        The translated value used to update the output attribute
    """
    return input_attr_value


def _translate_alt(
    input_attr_type: Sdf.ValueTypeNames, input_attr_value: Any, input_attr: Usd.Attribute
) -> Tuple[Sdf.ValueTypeNames, Any]:
    """
    Allows translating the input type and value to produce the output type and value when we need to create
    attributes in the output material.

    Args:
        input_attr_type: The input attribute type
        input_attr_value: The input attribute value
        input_attr: The input attribute

    Returns:
        The translated type and value used to create the output attribute
    """
    return input_attr_type, input_attr_value


class AttributeBase(BaseModel):
    """Represents 1 attribute to translate"""

    # Attribute name used on the input shader
    input_attr_name: str
    # Attribute name used on the output shader
    output_attr_name: str
    # If set, this value will be used to create the attribute on the output shader when it doesn't exist on the input
    output_default_value: Optional[Any] = None
    # Function used to translate the value of the input shader to the value of the output shader
    translate_fn: Callable[[Any, Usd.Attribute], Any] = Field(default=_translate)
    # tell if the attribute is a real attribute that exists by default, or if this is a fake one that was created
    fake_attribute: bool = False
    # Function used to translate the value of the input shader to the value of the output shader when we need to
    # create the attribute in the output material first.
    translate_alt_fn: Callable[
        [Optional[Sdf.ValueTypeNames], Any, Optional[Usd.Attribute]], Tuple[Optional[Sdf.ValueTypeNames], Any]
    ] = Field(default=_translate_alt)

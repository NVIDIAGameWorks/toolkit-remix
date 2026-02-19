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

from . import mapping as _mapping

__all__ = [
    "ComboboxField",
    "DisableAllListenersBlock",
    "FileTexturePicker",
    "USDAttrListItem",
    "USDAttributeDef",
    "USDAttributeItem",
    "USDAttributeItemStub",
    "USDAttributeXformItem",
    "USDAttributeXformItemStub",
    "USDBuilderList",
    "USDDelegate",
    "USDFloatSliderField",
    "USDIntSliderField",
    "USDMetadataListItem",
    "USDModel",
    "USDPropertyWidget",
    "USDPropertyWidgetExtension",
    "USDRelationshipItem",
    "VirtualUSDAttrListItem",
    "VirtualUSDAttributeItem",
    "get_usd_listener_instance",
    "utils",
]


from . import utils
from .delegate import USDDelegate
from .extension import USDPropertyWidgetExtension, get_usd_listener_instance
from .field_builders import USDBuilderList
from .item_delegates import ComboboxField, FileTexturePicker, USDFloatSliderField, USDIntSliderField
from .items import (
    USDAttributeDef,
    USDAttributeItem,
    USDAttributeItemStub,
    USDAttributeXformItem,
    USDAttributeXformItemStub,
    USDAttrListItem,
    USDMetadataListItem,
    USDRelationshipItem,
    VirtualUSDAttributeItem,
    VirtualUSDAttrListItem,
)
from .listener import DisableAllListenersBlock
from .model import USDModel
from .setup_ui import USDPropertyWidget


def _vdir(obj):
    return [x for x in dir(obj) if not x.startswith("__")]


__all__.extend(dir(_mapping))

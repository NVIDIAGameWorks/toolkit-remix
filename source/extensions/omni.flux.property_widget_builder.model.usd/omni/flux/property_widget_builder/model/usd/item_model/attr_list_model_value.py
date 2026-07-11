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

import omni.kit.commands
from pxr import Sdf, Usd

from .base_list_model_value import UsdListModelBaseValueModel as _UsdListModelBaseValueModel


class UsdListModelAttrValueModel(_UsdListModelBaseValueModel):
    """Represent an attribute that has multiple value choices like enums"""

    def _set_attribute_value(self, attr: Usd.Attribute, new_value: str, target_layer: Sdf.Layer | None = None) -> bool:
        attribute_path = str(attr.GetPath())
        if self._use_index_in_usd:
            new_value = self._list_options.index(new_value)

        if target_layer is None:
            target_layer = self._get_target_layer(attr)
        omni.kit.commands.execute(
            "ChangeProperty",
            prop_path=attribute_path,
            value=new_value,
            target_layer=target_layer,
            prev=None,
            usd_context_name=self._context_name,
        )
        return True

    def _get_attribute_value(self, attr) -> str:
        if self._use_index_in_usd:
            value: int = attr.Get()
            return self._list_options[int(value)]
        return attr.Get()


class VirtualUsdListModelAttrValueModel(UsdListModelAttrValueModel):
    _is_virtual = True

    def __init__(
        self,
        context_name: str,
        attribute_paths: list[Sdf.Path],
        default_value: str,
        options: list[str],
        read_only: bool = False,
        value_type_name: Sdf.ValueTypeName | None = None,
        metadata: dict | None = None,
        metadata_key: str | None = None,
        create_callback: Callable[[Usd.Attribute, Any], None] | None = None,
        tooltip_display_name: str | None = None,
    ):
        if metadata is None and value_type_name is not None:
            metadata = {Sdf.PrimSpec.TypeNameKey: str(value_type_name)}

        super().__init__(
            context_name=context_name,
            attribute_paths=attribute_paths,
            default_value=default_value,
            options=options,
            read_only=read_only,
            value_type_name=value_type_name,
            metadata=metadata,
            metadata_key=metadata_key,
            tooltip_display_name=tooltip_display_name,
        )
        self._create_callback = create_callback

    def get_attributes_raw_value(self, element_current_idx: int) -> Any | None:
        attr = self._attributes[element_current_idx]
        if isinstance(attr, Usd.Attribute) and attr.IsValid() and not attr.IsHidden():
            raw_value = attr.Get()
            if raw_value is not None:
                return raw_value
        return self._default_value

    @property
    def metadata(self):
        return self._metadata

    def _create_and_set_attribute_value(self, attr: Usd.Attribute, new_value: str) -> bool:
        # If it's the default value, no need to create anything
        if new_value == self._default_value:
            return False

        index = self._list_options.index(new_value)
        # If a create_callback is set, use that
        if self._create_callback:
            self._create_callback(attr, index)
        # Otherwise use the default creation
        else:
            path = attr.GetPath()
            if not path.IsPropertyPath():
                return False
            prim = self._stage.GetPrimAtPath(path.GetPrimPath())
            omni.kit.commands.execute(
                "CreateUsdAttributeCommand",
                prim=prim,
                attr_name=path.name,
                attr_type=self._value_type_name,
                attr_value=index,
            )
        return True

    def _set_attribute_value(self, attr: Usd.Attribute, new_value: str, target_layer: Sdf.Layer | None = None) -> bool:
        if attr:
            return super()._set_attribute_value(attr, new_value, target_layer)
        return self._create_and_set_attribute_value(attr, new_value)

    def _get_attribute_value(self, attr) -> str | None:
        value: int = attr.Get()
        if value is not None:
            return self._list_options[int(value)]
        return value

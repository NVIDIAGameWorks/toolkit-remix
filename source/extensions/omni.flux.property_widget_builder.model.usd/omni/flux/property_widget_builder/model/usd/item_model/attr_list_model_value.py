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

from typing import Any, Callable

import omni.kit.commands
import omni.kit.undo
import omni.usd
from pxr import Sdf, Usd

from .base_list_model_value import UsdListModelBaseValueModel as _UsdListModelBaseValueModel


class UsdListModelAttrValueModel(_UsdListModelBaseValueModel):
    """Represent an attribute that has multiple value choices like enums"""

    def _set_attribute_value(self, attr, new_value: str):
        attribute_path = str(attr.GetPath())
        if self._use_index_in_usd:
            new_value = self._list_options.index(new_value)

        # OM-75480: For props inside session layer, it will always change specs
        # in the session layer to avoid shadowing. Why it needs to be def is that
        # session layer is used for several runtime data for now as built-in cameras,
        # MDL material params, and etc. Not all of them create runtime prims inside
        # session layer. For those that are not defined inside session layer, we should
        # avoid leaving delta inside other sublayers as they are shadowed and useless after
        # stage close.
        target_layer, _ = omni.usd.find_spec_on_session_or_its_sublayers(
            self._stage, attr.GetPath().GetPrimPath(), lambda spec: spec.specifier == Sdf.SpecifierDef
        )
        if not target_layer:
            target_layer = self._stage.GetEditTarget().GetLayer()
        with omni.kit.undo.group():
            omni.kit.commands.execute(
                "ChangeProperty",
                prop_path=attribute_path,
                value=new_value,
                target_layer=target_layer,
                prev=None,
                usd_context_name=self._context_name,
            )

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
        type_name: str = None,
        metadata: dict = None,
        metadata_key: str | None = None,
        create_callback: Callable[[Usd.Attribute, Any], None] | None = None,
    ):
        self._metadata = metadata
        super().__init__(
            context_name=context_name,
            attribute_paths=attribute_paths,
            default_value=default_value,
            options=options,
            read_only=read_only,
            type_name=type_name,
            metadata_key=metadata_key,
        )
        if not self._metadata:
            self._metadata = {Sdf.ValueTypeNames: self._type_name}
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

    def _create_and_set_attribute_value(self, attr, new_value):
        # If it's the default value, no need to create anything
        if new_value == self._default_value:
            return

        index = self._list_options.index(new_value)
        # If a create_callback is set, use that
        if self._create_callback:
            self._create_callback(attr, index)
        # Otherwise use the default creation
        else:
            path = attr.GetPath()
            if not path.IsPropertyPath():
                return
            prim = self._stage.GetPrimAtPath(path.GetPrimPath())
            omni.kit.commands.execute(
                "CreateUsdAttributeCommand",
                prim=prim,
                attr_name=path.name,
                attr_type=self._type_name,
                attr_value=index,
            )

    def _set_attribute_value(self, attr, new_value):
        if attr:
            super()._set_attribute_value(attr, new_value)
        else:
            self._create_and_set_attribute_value(attr, new_value)

    def _get_attribute_value(self, attr) -> str | None:
        value: int = attr.Get()
        if value is not None:
            return self._list_options[int(value)]
        return value

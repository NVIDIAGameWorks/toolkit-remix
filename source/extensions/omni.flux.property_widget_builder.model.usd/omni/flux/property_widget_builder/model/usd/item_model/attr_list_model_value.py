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

import omni.kit.commands
import omni.kit.undo
import omni.usd
from pxr import Sdf

from .base_list_model_value import UsdListModelBaseValueModel as _UsdListModelBaseValueModel


class UsdListModelAttrValueModel(_UsdListModelBaseValueModel):
    """Represent an attribute that has multiple value choices like enums"""

    def _set_attribute_value(self, attr, new_value: str):
        attribute_path = str(attr.GetPath())
        index = self._list_options.index(new_value)

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
                value=index,
                target_layer=target_layer,
                prev=None,
                usd_context_name=self._context_name,
            )

    def _get_attribute_value(self, attr) -> str:
        value: int = attr.Get()
        return self._list_options[int(value)]

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

from ..utils import get_default_attribute_value as _get_default_attribute_value
from .base_list_model_value import UsdListModelBaseValueModel as _UsdListModelBaseValueModel


class UsdAttributeMetadataValueModel(_UsdListModelBaseValueModel):
    """Represent metadata of an attribute"""

    @property
    def is_default(self):
        """If the value model has the default USD value"""
        for attribute in self.attributes:
            default_value = _get_default_attribute_value(attribute)
            if default_value is None:
                continue
            # colorSpace dropdown
            if attribute.GetMetadata("colorSpace") is not None and self.get_value() != "auto":
                return False
            # Attempt to find the value in the list
            if (
                isinstance(default_value, int)
                and [c.model.as_string for c in self.get_item_children()].index(self.get_value()) != default_value
            ):
                return False
        return True

    def reset_default_value(self):
        """Reset the model's value back to the USD default"""
        for attribute in self.attributes:
            default_value = _get_default_attribute_value(attribute)
            if default_value is None:
                continue
            # colorSpace dropdown
            if attribute.GetMetadata("colorSpace") is not None:
                # "auto" is the default value for colorSpace
                self.set_value([c.model.as_string for c in self.get_item_children()].index("auto"))
            elif isinstance(default_value, int):
                self.set_value(default_value)

    def _set_attribute_value(self, attr, new_value: str):
        with omni.kit.undo.group():
            omni.kit.commands.execute(
                "ChangeMetadata",
                object_paths=[attr.GetPath()],
                key=self._key,
                value=new_value,
                usd_context_name=self._context_name,
            )

    def _get_attribute_value(self, attr) -> str:
        value = self.metadata.get(self._key, self._default_value)
        return value

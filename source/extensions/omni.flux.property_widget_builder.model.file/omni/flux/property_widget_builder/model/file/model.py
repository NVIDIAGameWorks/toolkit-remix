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

from omni.flux.property_widget_builder.widget import Model as _Model
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs


class FileModel(_Model):
    """Basic list model"""

    def __init__(self, path: str):
        """
        Model that will show a list of attribute(s) of a file

        Args:
            path: the path of the file
        """
        super().__init__()
        self._path = path

    @property
    def path(self) -> str:
        return self._path

    @property
    def default_attrs(self):
        result = super().default_attrs
        result.update({"_path": None})
        return result

    def destroy(self):
        _reset_default_attrs(self)
        super().destroy()

# noqa PLC0302
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

__all__ = ["FeatureFlag"]

from omni.flux.utils.common import reset_default_attrs


class FeatureFlag:
    def __init__(self, key: str, settings_data: dict):
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        if "value" not in settings_data:
            raise ValueError("Expected feature flag value but got no data.")

        self._key = key
        self._value = settings_data.get("value") or False
        self._display_name = settings_data.get("display_name") or key
        self._tooltip = settings_data.get("tooltip") or ""

    @property
    def default_attr(self) -> dict[str, None]:
        return {
            "_key": None,
            "_value": None,
            "_display_name": None,
            "_tooltip": None,
        }

    @property
    def key(self) -> str:
        return self._key

    @property
    def value(self) -> bool:
        return bool(self._value)

    @property
    def display_name(self) -> str:
        return self._display_name

    @property
    def tooltip(self) -> str:
        return self._tooltip

    def destroy(self):
        reset_default_attrs(self)

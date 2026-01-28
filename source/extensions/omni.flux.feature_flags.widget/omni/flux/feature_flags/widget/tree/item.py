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

__all__ = ["FeatureFlagItem"]

from omni import ui
from omni.flux.feature_flags.core import FeatureFlag
from omni.flux.utils.common import reset_default_attrs


class FeatureFlagItem(ui.AbstractItem):
    def __init__(self, feature_flag: FeatureFlag):
        super().__init__()

        for attr, val in self.default_attr.items():
            setattr(self, attr, val)

        self._feature_flag = feature_flag

    @property
    def default_attr(self) -> dict[str, None]:
        return {
            "_feature_flag": None,
        }

    @property
    def key(self) -> str:
        """
        Returns:
            The key used to identify the feature flag in the settings.
        """
        return self._feature_flag.key

    @property
    def value(self) -> bool:
        """
        Returns:
            Whether the feature flag is enabled or not.
        """
        return bool(self._feature_flag.value)

    @property
    def display_name(self) -> str:
        """
        Returns:
            The display name of the feature flag.
        """
        return self._feature_flag.display_name

    @property
    def tooltip(self) -> str:
        """
        Returns:
            The tooltip for the feature flag.
        """
        return self._feature_flag.tooltip

    def destroy(self):
        reset_default_attrs(self)

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

__all__ = ["FeatureFlagModel"]

import carb
from omni import ui
from omni.flux.feature_flags.core import FeatureFlagsCore
from omni.flux.utils.common import reset_default_attrs

from .item import FeatureFlagItem


class FeatureFlagModel(ui.AbstractItemModel):
    FEATURE_FLAGS_WIDGET_HEADERS = "/exts/omni.flux.feature_flags.widget/tree/headers"

    def __init__(self):
        super().__init__()

        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._feature_flags_core = FeatureFlagsCore()

        self._items = []
        self._feature_flags_changed_subs = []

    @property
    def default_attr(self) -> dict[str, None]:
        return {
            "_feature_flags_core": None,
            "_items": None,
            "_feature_flags_changed_subs": None,
        }

    @classmethod
    @property
    def headers(cls) -> dict[int, str]:
        settings_headers = carb.settings.get_settings().get(cls.FEATURE_FLAGS_WIDGET_HEADERS)
        return dict(enumerate(settings_headers)) if settings_headers else {0: "", 1: "Feature Flag"}

    def enable_listeners(self, value: bool):
        """
        Enables or disables listeners for feature flags changes.

        If listeners are enabled, the model will be refreshed.

        Args:
            value: Enable or disable listeners.
        """
        if value:
            self._feature_flags_changed_subs = self._feature_flags_core.subscribe_feature_flags_changed(
                lambda *_: self.refresh()
            )
            self.refresh()
        elif self._feature_flags_changed_subs:
            self._feature_flags_core.unsubscribe_feature_flags_changed(self._feature_flags_changed_subs)
            self._feature_flags_changed_subs = None

    def refresh(self):
        """
        Fetch and update the model with all the available feature flags.
        """
        self._items = [FeatureFlagItem(feature_flag) for feature_flag in self._feature_flags_core.get_all_flags()]
        self._item_changed(None)

    def get_item_children(self, item: FeatureFlagItem | None):
        if item is None:
            return self._items
        return []

    def get_item_value_model_count(self, item: FeatureFlagItem | None):
        return len(self.headers.keys())

    def set_enabled(self, item: FeatureFlagItem, value: bool):
        """
        Enable or disable a feature flag.

        Args:
            item: The feature flag item to enable or disable.
            value: True to enable, False to disable.
        """
        self._feature_flags_core.set_enabled(item.key, value)

    def set_enabled_all(self, value: bool):
        """
        Enable or disable all feature flags.

        Args:
            value: True to enable, False to disable.
        """
        self._feature_flags_core.set_enabled_all(value)

    def destroy(self):
        if self._feature_flags_changed_subs:
            self._feature_flags_core.unsubscribe_feature_flags_changed(self._feature_flags_changed_subs)
        reset_default_attrs(self)

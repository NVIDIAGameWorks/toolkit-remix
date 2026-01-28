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

__all__ = ["FeatureFlagsCore"]

import contextlib

import carb

from .items import FeatureFlag


class FeatureFlagsCore:
    _PERSISTENT_PREFIX = "/persistent"
    _FEATURE_FLAGS_SETTING = "/exts/omni.flux.feature_flags.core/flags"

    def __init__(self):
        self._settings = carb.settings.get_settings()

    def get_all_flags(self) -> list[FeatureFlag]:
        """
        Get all the feature flags defined in the `/exts/omni.flux.feature_flags.core/flags` settings.

        This method will also clean up any residual persistent feature flag setting after transient definitions are
        removed.

        Returns:
            A list of FeatureFlag objects for every feature flag defined in the settings.
        """
        feature_flags = self._settings.get(self._FEATURE_FLAGS_SETTING) or {}

        # If some persistent settings exist, merge them with the current feature flags.
        persistent_feature_flags = self._settings.get(f"{self._PERSISTENT_PREFIX}{self._FEATURE_FLAGS_SETTING}") or {}

        self._cleanup_persistent_settings(feature_flags, persistent_feature_flags)
        self._lazy_update_settings(feature_flags, persistent_feature_flags)

        return [FeatureFlag(key, data) for key, data in feature_flags.items()]

    def get_flag(self, feature_flag_key: str) -> FeatureFlag:
        """
        Get a feature flag object, given its key

        Args:
            feature_flag_key: The key used in the settings to identify the feature flag

        Raises:
            ValueError: If the feature flag with the given key is not found in the settings.

        Returns:
            A FeatureFlag object of the feature flag requested
        """
        feature_flag = None
        feature_flags = self.get_all_flags()

        for flag in feature_flags:
            if flag.key == feature_flag_key:
                feature_flag = flag
                break

        if feature_flag is None:
            raise ValueError(f"Feature flag '{feature_flag_key}' not found.")

        return feature_flag

    def set_enabled_all(self, value: bool):
        """
        Set all the available feature flags' values to the given value.

        Args:
            value: Whether the feature flags should be enabled or disabled.
        """
        for feature_flag in self.get_all_flags():
            self.set_enabled(feature_flag.key, value)

    def set_enabled(self, feature_flag_key: str, value: bool):
        """
        Set the requested feature flag's value to the given value.

        Args:
            feature_flag_key: The key used in the settings to identify the feature flag
            value: Whether the feature flag should be enabled or disabled.
        """
        self._settings.set_bool(
            f"{self._PERSISTENT_PREFIX}{self._FEATURE_FLAGS_SETTING}/{feature_flag_key}/value", value
        )

    def is_enabled(self, feature_flag_key: str) -> bool:
        """
        Whether a requested feature flag is enabled or not.

        Args:
            feature_flag_key: The key used in the settings to identify the feature flag

        Raises:
            ValueError: If the feature flag with the given key is not found in the settings.

        Returns:
            True if a feature flag is enabled, False otherwise.
        """
        return self.get_flag(feature_flag_key).value

    def subscribe_feature_flags_changed(self, callback: callable) -> list[carb.settings.SubscriptionId]:
        """
        Subscribe to changes to any of the feature flags' values.

        Args:
            callback: The callback function to be called when a feature flag's value changes.

        Returns:
            A list of subscription IDs to use when unsubscribing.
        """
        subscriptions = []
        for feature_flag in self.get_all_flags():
            subscriptions.append(
                self._settings.subscribe_to_node_change_events(
                    f"{self._PERSISTENT_PREFIX}{self._FEATURE_FLAGS_SETTING}/{feature_flag.key}/value", callback
                )
            )
            subscriptions.append(
                self._settings.subscribe_to_node_change_events(
                    f"{self._FEATURE_FLAGS_SETTING}/{feature_flag.key}/value", callback
                )
            )
        return subscriptions

    def unsubscribe_feature_flags_changed(self, subscription_ids: list[carb.settings.SubscriptionId]):
        """
        Unsubscribe from the `feature_flags_changed` events.

        Args:
            subscription_ids: A list of subscription IDs to unsubscribe from
        """
        for subscription_id in subscription_ids:
            self._settings.unsubscribe_to_change_events(subscription_id)

    @contextlib.contextmanager
    def feature_flags_changed(self, callback: callable) -> list[carb.settings.SubscriptionId]:
        """
        A context manager to subscribe and unsubscribe from the `feature_flags_changed` events automatically.

        Since the subscription will be cleaned up automatically when the context manager exits, this is not viable for
        long-running code, but can be useful in short-lived scripts.

        Args:
            callback: The callback to executed when the event is triggered.

        Returns:
            A list of subscription IDs created when subscribing to the events.
        """
        subscriptions = self.subscribe_feature_flags_changed(callback)

        try:
            yield subscriptions
        finally:
            self.unsubscribe_feature_flags_changed(subscriptions)

    def _cleanup_persistent_settings(self, transient: dict, persistent: dict):
        """
        Cleanup the residual persistent settings after transient definitions are removed in-place.

        Args:
            transient: The dictionary of transient settings
            persistent: The dictionary of persistent settings
        """
        for key in persistent.copy():
            if key not in transient:
                del persistent[key]

    def _lazy_update_settings(self, original: dict, updated: dict):
        """
        Lazily update the settings' dictionary in-place.

        Args:
            original: The dictionary to modify
            updated: The dictionary containing the updates
        """
        for key, value in updated.items():
            if isinstance(value, dict) and key in original and isinstance(original[key], dict):
                self._lazy_update_settings(original[key], value)
            else:
                original[key] = value

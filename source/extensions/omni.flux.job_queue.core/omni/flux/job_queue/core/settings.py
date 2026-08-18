"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

from __future__ import annotations

__all__ = [
    "AUTO_APPLY_SETTING_PATH",
    "JOB_QUEUE_SETTINGS_ROOT",
    "SCHEDULER_ENABLED_SETTING_PATH",
    "TIMESTAMP_MODE_SETTING_PATH",
    "JobQueueSettings",
]

import carb.settings

from .enums import TimestampMode

JOB_QUEUE_SETTINGS_ROOT = "/exts/omni.flux.job_queue.core"


def _persistent_key(key: str) -> str:
    """Prefix one extension setting with Kit's persistent namespace.

    Args:
        key: Absolute extension setting path.

    Returns:
        Persistent setting path.
    """
    return f"/persistent{key}"


AUTO_APPLY_SETTING_PATH = _persistent_key(f"{JOB_QUEUE_SETTINGS_ROOT}/auto_apply")
SCHEDULER_ENABLED_SETTING_PATH = _persistent_key(f"{JOB_QUEUE_SETTINGS_ROOT}/scheduler_enabled")
TIMESTAMP_MODE_SETTING_PATH = _persistent_key(f"{JOB_QUEUE_SETTINGS_ROOT}/timestamp_mode")


class JobQueueSettings:
    """Settings interface for shared job queue behavior and display preferences."""

    @property
    def timestamp_mode(self) -> TimestampMode:
        """Return the current timestamp display mode.

        Returns:
            Persisted mode, defaulting to relative timestamps.
        """
        value = carb.settings.get_settings().get(TIMESTAMP_MODE_SETTING_PATH)
        for mode in TimestampMode:
            if mode.value == value:
                return mode
        return TimestampMode.RELATIVE

    def set_timestamp_mode(self, value: TimestampMode) -> None:
        """Persist the timestamp display mode.

        Args:
            value: New timestamp display mode.
        """
        carb.settings.get_settings().set(TIMESTAMP_MODE_SETTING_PATH, value.value)

    @property
    def auto_apply(self) -> bool:
        """Return whether completed jobs follow automatic Apply policy.

        Returns:
            Persisted preference, or True when no preference exists.
        """
        value = carb.settings.get_settings().get(AUTO_APPLY_SETTING_PATH)
        return True if value is None else bool(value)

    def set_auto_apply(self, value: bool) -> None:
        """Persist whether completed jobs follow automatic Apply policy.

        Args:
            value: New automatic Apply preference.
        """
        carb.settings.get_settings().set(AUTO_APPLY_SETTING_PATH, value)

    @property
    def scheduler_enabled(self) -> bool:
        """Return whether owned queue schedulers run, defaulting to True when unset.

        Returns:
            Persisted scheduler preference, or True when no preference exists.
        """
        value = carb.settings.get_settings().get(SCHEDULER_ENABLED_SETTING_PATH)
        return True if value is None else bool(value)

    def set_scheduler_enabled(self, value: bool) -> None:
        """Persist whether owned queue schedulers should run.

        Args:
            value: New scheduler-enabled preference.
        """
        carb.settings.get_settings().set(SCHEDULER_ENABLED_SETTING_PATH, value)

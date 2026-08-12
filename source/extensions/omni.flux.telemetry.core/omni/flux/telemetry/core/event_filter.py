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

from collections.abc import Sequence

__all__ = ["should_filter_event"]


def should_filter_event(
    event: dict,
    owned_module_prefixes: Sequence[str],
    external_exception_module_prefixes: Sequence[str],
    drop_unattributed_events: bool,
) -> bool:
    """Return whether an event has no application-owned origin and should be filtered.

    Args:
        event: The Sentry event payload.
        owned_module_prefixes: Python module roots owned by the application.
        external_exception_module_prefixes: Exception module roots that identify external failures.
        drop_unattributed_events: Whether to filter events without usable origin metadata.

    Returns:
        Whether the event should be filtered.
    """
    if event.get("type") == "transaction" or not owned_module_prefixes:
        return False

    def matches(module: str, prefixes: Sequence[str]) -> bool:
        return any(module == prefix or module.startswith(f"{prefix}.") for prefix in prefixes)

    if "exception" in event:
        exception = event.get("exception")
        values = exception.get("values") if isinstance(exception, dict) else None
        if not isinstance(values, list) or not values:
            return drop_unattributed_events

        has_external_origin = False
        for value in values:
            if not isinstance(value, dict):
                continue

            exception_module = value.get("module")
            if isinstance(exception_module, str) and matches(exception_module, external_exception_module_prefixes):
                has_external_origin = True
                continue

            stacktrace = value.get("stacktrace")
            frames = stacktrace.get("frames") if isinstance(stacktrace, dict) else None
            if not isinstance(frames, list) or not frames:
                continue

            terminal_frame = frames[-1]
            terminal_module = terminal_frame.get("module") if isinstance(terminal_frame, dict) else None
            if not isinstance(terminal_module, str) or not terminal_module:
                continue
            if matches(terminal_module, owned_module_prefixes):
                return False
            has_external_origin = True

        return has_external_origin or drop_unattributed_events

    logger = event.get("logger")
    if isinstance(logger, str) and logger:
        return not matches(logger, owned_module_prefixes)
    return drop_unattributed_events

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

__all__ = ["TelemetryCore"]

import logging
import uuid
from functools import partial
from types import ModuleType
from typing import Any

import carb
import omni.kit.app
import omni.structuredlog
import sentry_sdk
from omni.flux.utils.common import reset_default_attrs
from omni.flux.utils.common.git import get_branch, open_repository
from omni.flux.utils.common.version import get_app_distribution
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration


class TelemetryCore:
    TELEMETRY_SETTINGS = "/exts/omni.flux.telemetry.core"
    SENTRY_SETTINGS = "/exts/omni.flux.telemetry.core/sentry"

    def __init__(self):
        self._default_attr = {
            "_settings": None,
            "_tokens": None,
            "_app": None,
            "_is_enabled": None,
            "_development_mode": None,
            "_remove_pii": None,
            "_set_default_tags": None,
            "_ignore_span_op_prefixes": None,
            "_ignore_span_name_prefixes": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._settings = carb.settings.get_settings()
        self._tokens = carb.tokens.get_tokens_interface()
        self._app = omni.kit.app.get_app()

        self._is_enabled = self._settings.get(f"{self.TELEMETRY_SETTINGS}/enabled")
        self._development_mode = self._settings.get(f"{self.TELEMETRY_SETTINGS}/development_mode")
        self._remove_pii = self._settings.get(f"{self.TELEMETRY_SETTINGS}/remove_pii")
        self._set_default_tags = self._settings.get(f"{self.TELEMETRY_SETTINGS}/set_default_tags")
        self._ignore_span_op_prefixes = self._settings.get(f"{self.TELEMETRY_SETTINGS}/ignore_span_op_prefixes") or []
        self._ignore_span_name_prefixes = (
            self._settings.get(f"{self.TELEMETRY_SETTINGS}/ignore_span_name_prefixes") or []
        )

        if not self._is_enabled:
            return

        if self._initialize_sentry():
            self._set_tags()

    @property
    def sentry_sdk(self) -> ModuleType:
        """
        Shortcut to the sentry_sdk module.
        This is useful to use sentry_sdk directly without having to import the pip archive in multiple extensions.

        Returns:
            The `sentry_sdk` module
        """
        return sentry_sdk

    def _initialize_sentry(self) -> bool:
        # Assume that the app is in production if the git branch is main or if no git branch is found
        repo = open_repository()
        try:
            git_branch = get_branch(repo)
        finally:
            if repo is not None:
                repo.free()

        is_production = (git_branch is None) or (git_branch == "main")

        if not is_production and not self._development_mode:
            return False

        settings = self._resolve_settings(self.SENTRY_SETTINGS)

        # Override the environment
        settings["dist"] = get_app_distribution()
        settings["environment"] = "production" if is_production else "development"
        settings["release"] = f"{self._app.get_app_filename()}@{self._app.get_app_version()}"
        settings["auto_enabling_integrations"] = False

        # Set up integrations
        settings["integrations"] = [
            LoggingIntegration(level=logging.ERROR, event_level=logging.ERROR),
            StarletteIntegration(
                transaction_style="url",
                failed_request_status_codes={422, *range(500, 600)},
            ),
            FastApiIntegration(
                transaction_style="url",
                failed_request_status_codes={422, *range(500, 600)},
            ),
        ]

        # Set up traces sampler to modify the default rate
        settings["traces_sampler"] = partial(self._traces_sampler, default_rate=settings.get("traces_sample_rate", 1.0))

        # Set up error event processing for PII removal if enabled
        settings["before_send"] = partial(self._before_send, app_root_path=settings.get("project_root", ""))

        # Set up transaction processing to add HTTP method and remove PII if enabled
        settings["before_send_transaction"] = partial(
            self._before_send_transaction, app_root_path=settings.get("project_root", "")
        )

        sentry_sdk.init(**settings)

        return True

    def _set_tags(self):
        if not self._set_default_tags:
            return

        sentry_sdk.set_tag("app.name", self._app.get_app_name())
        sentry_sdk.set_tag("app.version", self._app.get_app_version())
        sentry_sdk.set_tag("app.environment", self._app.get_app_environment())
        sentry_sdk.set_tag("app.kit_version", self._app.get_kit_version())

        structlog_settings = omni.structuredlog.IStructuredLogSettings()
        if structlog_settings:
            sentry_sdk.set_tag("session_id", str(structlog_settings.session_id))

        data = self._settings.get("/crashreporter/data")
        if not data:
            data = {}

        user_id = data.get("userId")
        if user_id:
            sentry_sdk.set_user({"id": user_id})

    def _resolve_settings(self, key: str) -> dict[str, Any]:
        resolved_settings = {}

        for entry in self._settings.get(key) or {}:
            setting = self._settings.get(f"{key}/{entry}")
            if not setting:
                continue

            if isinstance(setting, dict):
                resolved_settings[entry] = self._resolve_settings(f"{key}/{entry}")
            elif isinstance(setting, list):
                resolved_settings[entry] = [
                    self._tokens.resolve(item) if isinstance(item, str) else item for item in setting
                ]
            elif isinstance(setting, str):
                resolved_settings[entry] = self._tokens.resolve(setting)
            else:
                resolved_settings[entry] = setting

        return resolved_settings

    def _traces_sampler(self, sampling_context: dict, default_rate: float) -> float:
        # Check for custom sample rate
        sample_rate_override = sampling_context.get("sample_rate_override")
        if sample_rate_override is not None:
            return sample_rate_override

        # Check if this is a middleware.starlette span and ignore it
        transaction_context = sampling_context.get("transaction_context", {})
        op = transaction_context.get("op", "")
        name = transaction_context.get("name", "")
        # Ignore if op or name is in the ignore list
        for prefix in self._ignore_span_op_prefixes:
            if op.startswith(prefix):
                return 0.0
        for prefix in self._ignore_span_name_prefixes:
            if name.startswith(prefix):
                return 0.0

        # Default rate
        return default_rate

    def _before_send(self, event: dict, hint: dict, app_root_path: str) -> dict | None:
        """Tries our best to remove PII data from sentry events.

        We replace userId by the sessionId (unique integer per whole session) and replace any paths we find in the
            message or stack trace with their last part of the path, e.g: /home/foo/bar.py becomes bar.py

        Args:
            event (dict): The event that we filter
            hint (dict): Not used but part of the API
            app_root_path (str or None): the root path of the app. Everything before this is considered PII

        Returns:
            dict: The filtered event.
        """
        # Filter out RemixMetrics info-level events
        if event.get("level") == "info" and event.get("message") == "RemixMetrics":
            return None

        if not self._remove_pii:
            return event

        event.pop("server_name", "")
        filter_func = partial(self._filter_path_from_string, app_root_path=app_root_path)
        if event.get("logentry", {}).get("message", ""):
            event["logentry"]["message"] = filter_func(event["logentry"]["message"])

        if event.get("logentry", {}).get("formatted", ""):
            event["logentry"]["formatted"] = filter_func(event["logentry"]["formatted"])

        if event.get("extra", {}).get("filename", ""):
            event["extra"]["filename"] = filter_func(event["extra"]["filename"])

        if event.get("extra", {}).get("sys.argv", []):
            new_argv = []
            for arg in event["extra"]["sys.argv"]:
                new_argv.append(filter_func(arg))
            event["extra"]["sys.argv"] = new_argv

        if event.get("breadcrumbs", {}).get("values", []):
            for value in event["breadcrumbs"]["values"]:
                value["message"] = filter_func(value["message"])

        # Replace the user info with a UUID that is unique to a machine
        event["user"] = {"id": self._get_machine_id()}

        return event

    def _before_send_transaction(self, event: dict, hint: dict, app_root_path: str) -> dict | None:
        """Process transaction events by optionally removing PII and adding HTTP method.

        Args:
            event: The transaction event
            hint: Additional information about the event

        Returns:
            The processed event or None if filtered out
        """
        # First, remove PII if enabled
        event = self._before_send(event, hint, app_root_path)
        if event is None:
            return None

        # Then add HTTP method
        request = event.get("request", {})
        method = request.get("method")
        if method:
            # Add method as a tag for easy filtering in Sentry UI
            if "tags" not in event:
                event["tags"] = {}
            event["tags"]["http.method"] = method

        return event

    def _filter_path_from_string(self, input_str: str, app_root_path: str) -> str:
        """If there's a path on the string we get rid of everything up to the root path."""
        all_lines = []
        for line in input_str.split("\n"):
            line = line.replace("\\", "/")
            if line.startswith("--"):
                words_in_line = line.split("=")
            else:
                words_in_line = line.split(" ")
            new_line = []
            for word in words_in_line:
                if not word.startswith("--") and word.count("/") > 1:
                    if app_root_path and app_root_path in word:
                        # split on the root path, and only save everything after that.
                        word = word.split(app_root_path)[-1]
                    else:
                        last_idx = word.rfind("/")
                        word = word[last_idx:]
                new_line.append(word)

            if line.startswith("--"):
                all_lines.append("=".join(new_line))
            else:
                all_lines.append(" ".join(new_line))

        return "\n".join(all_lines)

    def _get_machine_id(self):
        """Return an identifier that is unique to the machine this is being run on, without any PII"""
        # Use the machine's MAC address as a seed to generate a deterministic UUID uuid.getnode() returns the MAC
        # address as a 48-bit integer
        machine_identifier = str(uuid.getnode())

        # Create a custom namespace specific to this extension.
        # This ensures UUIDs are unique to this application and can't be correlated with UUIDs generated by other
        # systems using the same MAC address.
        namespace = uuid.uuid5(uuid.NAMESPACE_DNS, "omni.flux.telemetry.core")

        # Generate the machine ID using our custom namespace
        return uuid.uuid5(namespace, machine_identifier).hex

    def destroy(self):
        client = sentry_sdk.Hub.current.client
        if client is not None:
            client.close(timeout=2.0)

        reset_default_attrs(self)

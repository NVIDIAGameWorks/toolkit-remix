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

import omni.kit.test

from omni.flux.telemetry.core.event_filter import should_filter_event


class TestSentryEventFilter(omni.kit.test.AsyncTestCase):
    def test_should_filter_event_without_owned_roots_keeps_event(self):
        # Arrange
        event = {"exception": {"values": [{"stacktrace": {"frames": [{"module": "starlette.routing"}]}}]}}

        # Act
        result = should_filter_event(event, (), ("pxr",), True)

        # Assert
        self.assertFalse(result)

    def test_should_filter_event_transaction_keeps_event(self):
        # Arrange
        event = {"type": "transaction"}

        # Act
        result = should_filter_event(event, ("omni.flux",), ("pxr",), True)

        # Assert
        self.assertFalse(result)

    def test_should_filter_event_with_external_exception_module_and_owned_caller_filters_event(self):
        # Arrange
        event = {
            "exception": {
                "values": [
                    {
                        "module": "pxr.Tf",
                        "stacktrace": {"frames": [{"module": "app.layer_manager.core"}]},
                    }
                ]
            }
        }

        # Act
        result = should_filter_event(event, ("omni.flux", "app"), ("pxr",), True)

        # Assert
        self.assertTrue(result)

    def test_should_filter_event_with_owned_terminal_in_chained_exception_keeps_event(self):
        # Arrange
        event = {
            "exception": {
                "values": [
                    {"type": "OSError"},
                    {
                        "type": "OSError",
                        "stacktrace": {
                            "frames": [
                                {"module": "asyncio.events"},
                                {"module": "app.recent_projects.core"},
                            ]
                        },
                    },
                ]
            }
        }

        # Act
        result = should_filter_event(event, ("omni.flux", "app"), ("pxr",), True)

        # Assert
        self.assertFalse(result)

    def test_should_filter_event_with_external_terminal_after_owned_caller_filters_event(self):
        # Arrange
        event = {
            "exception": {
                "values": [
                    {
                        "stacktrace": {
                            "frames": [
                                {"module": "app.mcp.core"},
                                {"module": "uvicorn.server"},
                            ]
                        }
                    }
                ]
            }
        }

        # Act
        result = should_filter_event(event, ("omni.flux", "app"), ("pxr",), True)

        # Assert
        self.assertTrue(result)

    def test_should_filter_event_with_external_and_owned_exception_values_keeps_event(self):
        # Arrange
        event = {
            "exception": {
                "values": [
                    {"module": "pxr.Tf", "stacktrace": {"frames": [{"module": "pxr.Tf"}]}},
                    {"stacktrace": {"frames": [{"module": "omni.flux.service.factory"}]}},
                ]
            }
        }

        # Act
        result = should_filter_event(event, ("omni.flux", "app"), ("pxr",), True)

        # Assert
        self.assertFalse(result)

    def test_should_filter_event_with_unattributed_exception_and_drop_enabled_filters_event(self):
        # Arrange
        event = {"exception": {"values": [{"type": "UnicodeDecodeError"}]}}

        # Act
        result = should_filter_event(event, ("omni.flux", "app"), ("pxr",), True)

        # Assert
        self.assertTrue(result)

    def test_should_filter_event_with_unattributed_exception_and_drop_disabled_keeps_event(self):
        # Arrange
        event = {"exception": {"values": [{"type": "UnicodeDecodeError"}]}}

        # Act
        result = should_filter_event(event, ("omni.flux", "app"), ("pxr",), False)

        # Assert
        self.assertFalse(result)

    def test_should_filter_event_with_malformed_exception_and_drop_enabled_filters_event(self):
        test_cases = (
            ("none_exception", {"exception": None}),
            ("empty_values", {"exception": {"values": []}}),
            ("invalid_value", {"exception": {"values": [None]}}),
            ("frame_without_module", {"exception": {"values": [{"stacktrace": {"frames": [{}]}}]}}),
        )

        for name, malformed_event in test_cases:
            with self.subTest(name=name):
                # Arrange
                event = malformed_event

                # Act
                result = should_filter_event(event, ("omni.flux", "app"), ("pxr",), True)

                # Assert
                self.assertTrue(result)

    def test_should_filter_event_with_owned_logger_keeps_message(self):
        # Arrange
        event = {"logger": "omni.flux.service"}

        # Act
        result = should_filter_event(event, ("omni.flux", "app"), ("pxr",), True)

        # Assert
        self.assertFalse(result)

    def test_should_filter_event_with_external_logger_filters_message(self):
        # Arrange
        event = {"logger": "starlette.routing"}

        # Act
        result = should_filter_event(event, ("omni.flux", "app"), ("pxr",), True)

        # Assert
        self.assertTrue(result)

    def test_should_filter_event_without_logger_and_drop_enabled_filters_message(self):
        # Arrange
        event = {}

        # Act
        result = should_filter_event(event, ("omni.flux", "app"), ("pxr",), True)

        # Assert
        self.assertTrue(result)

    def test_should_filter_event_with_handled_owned_exception_keeps_event(self):
        # Arrange
        event = {
            "exception": {
                "values": [
                    {
                        "mechanism": {"handled": True},
                        "stacktrace": {"frames": [{"module": "app.scatter"}]},
                    }
                ]
            }
        }

        # Act
        result = should_filter_event(event, ("omni.flux", "app"), ("pxr",), True)

        # Assert
        self.assertFalse(result)

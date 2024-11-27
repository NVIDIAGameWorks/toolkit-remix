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

import random
import string
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import omni.kit.test
import sentry_sdk
from lightspeed.sentry_manager.core import (
    ELAPSED_TIME_METRIC_TYPE,
    METRICS_MESSAGE_TOPIC,
    TIMING_METRIC_TYPE,
    get_instance,
)
from lightspeed.trex.utils.common.user_utils import get_user_key


def random_string(length=20):
    chars = [random.choice(string.printable) for _ in range(length)]
    return "".join(chars)


class TestSentryManager(omni.kit.test.AsyncTestCase):
    def test_get_instance(self):
        # Act
        mgr = get_instance()

        # Assert
        self.assertIsNotNone(mgr)
        self.assertIsInstance(mgr.start_time, float)

    def test_app_closing(self):
        # Arrange
        sentry_mgr = get_instance()
        with patch.object(sentry_mgr, "post_metric") as mock_metric:
            # Act
            sentry_mgr.app_closing()

        # Assert
        mock_metric.assert_called_once()
        args, kwargs = mock_metric.call_args
        self.assertEqual(args[0], ELAPSED_TIME_METRIC_TYPE)
        post_event_value = kwargs["value"]
        post_event_tags = kwargs["tags"]
        # Since this test should take much less than 1 second, the value for the time should be 0.
        self.assertEqual(post_event_value, 0)
        self.assertIsNone(post_event_tags)

    def test_post_metric(self):
        # Arrange
        fake_event_type = random_string()
        fake_value = random.randrange(100)
        key_count = random.randrange(1, 10)
        fake_tags = {}
        for _ in range(key_count):
            fake_tags[random_string()] = random_string()
        mock_scope = MagicMock()
        key = get_user_key()

        with (
            patch.object(sentry_sdk, "push_scope", autospec=True, return_value=mock_scope),
            patch.object(sentry_sdk, "set_tag") as mock_tag,
            patch.object(sentry_sdk, "capture_message") as mock_capture,
        ):
            # Act
            get_instance().post_metric(fake_event_type, fake_value, fake_tags)

        # Assert
        mock_tag.assert_called_once_with("user_key", key)
        mock_capture.assert_called_once_with(METRICS_MESSAGE_TOPIC)

    def test_timeit(self):
        # Arrange
        manager = get_instance()

        @manager.timeit
        def dummy_func(duration):
            time.sleep(duration)

        # Pick a duration of under a half-second
        duration = random.random() * 0.5
        with patch.object(manager, "post_metric") as mock_metric:
            # Act
            dummy_func(duration)

        # Assert
        args, kwargs = mock_metric.call_args
        self.assertEqual(args[0], TIMING_METRIC_TYPE)
        elapsed = kwargs["value"]
        # The times should be very close, but not the same
        self.assertLess(abs(elapsed - duration), 0.005)
        tags = kwargs["tags"]
        pth = Path(__file__)
        self.assert_(tags["module"].endswith(pth.stem))
        self.assertEqual(tags["name"], "dummy_func")

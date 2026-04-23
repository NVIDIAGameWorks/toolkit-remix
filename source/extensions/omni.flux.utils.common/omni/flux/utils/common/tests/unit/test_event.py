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

import gc

import omni.kit.test
from omni.flux.utils.common import event as _event


class TestEvent(omni.kit.test.AsyncTestCase):
    async def test_event_calls_all_subscribers_and_returns_their_results(self):
        # Arrange
        event = _event.Event()

        def callback_one():
            return "one"

        def callback_two():
            return "two"

        event.update({callback_one, callback_two})

        # Act
        result = event()

        # Assert
        self.assertCountEqual(["one", "two"], result)

    async def test_event_with_copy_allows_subscriber_mutation_without_affecting_current_dispatch(self):
        # Arrange
        event = _event.Event(copy=True)
        calls = []

        def callback():
            calls.append("callback")
            event.clear()
            event.add(lambda: "late")
            return "callback-result"

        event.add(callback)

        # Act
        result = event()

        # Assert
        self.assertEqual(["callback"], calls)
        self.assertEqual(["callback-result"], result)
        self.assertEqual(1, len(event))

    async def test_event_repr_wraps_the_underlying_set_representation(self):
        # Arrange
        event = _event.Event()

        # Act
        result = repr(event)

        # Assert
        self.assertEqual("Event(Event())", result)

    async def test_event_subscription_unregisters_callback_when_subscription_is_destroyed(self):
        # Arrange
        event = _event.Event()

        def callback():
            return None

        subscription = _event.EventSubscription(event, callback)
        self.assertIn(callback, event)

        # Act
        del subscription
        gc.collect()

        # Assert
        self.assertNotIn(callback, event)

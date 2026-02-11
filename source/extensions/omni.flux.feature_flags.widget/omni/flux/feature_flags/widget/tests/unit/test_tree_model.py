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

from unittest.mock import Mock, call, patch

from omni.flux.feature_flags.core import FeatureFlag, FeatureFlagsCore
from omni.flux.feature_flags.widget.tree import FeatureFlagModel
from omni.kit.test import AsyncTestCase


class TestFeatureFlagModel(AsyncTestCase):
    async def setUp(self):
        self.model = FeatureFlagModel()

    # After running each test
    async def tearDown(self):
        self.model = None

    async def test_enable_listeners_should_subscribe_and_refresh(self):
        # Arrange
        with patch.object(FeatureFlagModel, "refresh") as refresh_mock:
            # Act
            self.model.enable_listeners(True)

        # Assert
        self.assertIsNotNone(self.model._feature_flags_changed_subs)
        self.assertEqual(refresh_mock.call_count, 1)

    async def test_disable_listeners_should_delete_subscription(self):
        # Arrange
        sub = Mock()
        self.model._feature_flags_changed_subs = [sub]

        with patch.object(FeatureFlagsCore, "unsubscribe_feature_flags_changed") as unsubscribe_mock:
            # Act
            self.model.enable_listeners(False)

        # Assert
        self.assertEqual(unsubscribe_mock.call_count, 1)
        self.assertEqual(unsubscribe_mock.call_args, call([sub]))

        self.assertIsNone(self.model._feature_flags_changed_subs)

    async def test_refresh_should_get_all_flags_and_trigger_item_changed(self):
        # Arrange
        with (
            patch.object(FeatureFlagModel, "_item_changed") as item_changed_mock,
            patch.object(FeatureFlagsCore, "get_all_flags") as get_flags_mock,
        ):
            get_flags_mock.return_value = [
                FeatureFlag("test_enabled", {"value": True}),
                FeatureFlag("test_disabled", {"value": False}),
            ]

            # Act
            self.model.refresh()

        # Assert
        self.assertEqual(len(self.model._items), 2)

        self.assertEqual(self.model._items[0].key, "test_enabled")
        self.assertEqual(self.model._items[0].value, True)

        self.assertEqual(self.model._items[1].key, "test_disabled")
        self.assertEqual(self.model._items[1].value, False)

        self.assertEqual(get_flags_mock.call_count, 1)

        self.assertEqual(item_changed_mock.call_count, 1)
        self.assertEqual(item_changed_mock.call_args, call(None))

    async def test_get_item_children_no_item_should_return_items(self):
        # Arrange
        item_mocks = [Mock(), Mock(), Mock()]
        self.model._items = item_mocks

        # Act
        items = self.model.get_item_children(None)

        # Assert
        self.assertListEqual(items, item_mocks)

    async def test_get_item_children_item_should_return_empty_list(self):
        # Arrange
        item_mocks = [Mock(), Mock(), Mock()]
        self.model._items = item_mocks

        # Act
        items = self.model.get_item_children(item_mocks[0])

        # Assert
        self.assertListEqual(items, [])

    async def test_get_item_value_model_count_should_return_len_of_header_dict(self):
        for item in [None, Mock()]:
            with self.subTest(title=f"item_{item}"):
                # Arrange
                pass

                # Act
                count = self.model.get_item_value_model_count(item)

                # Assert
                self.assertEqual(count, len(FeatureFlagModel.headers.keys()))

    async def test_set_enabled_should_call_core_set_enabled(self):
        # Arrange
        item = Mock()
        value = False

        with patch.object(FeatureFlagsCore, "set_enabled") as get_flags_mock:
            # Act
            self.model.set_enabled(item, value)

        # Assert
        self.assertEqual(get_flags_mock.call_count, 1)
        self.assertEqual(get_flags_mock.call_args, call(item.key, value))

    async def test_set_enabled_all_should_call_core_set_enabled_all(self):
        # Arrange
        value = False

        with patch.object(FeatureFlagsCore, "set_enabled_all") as get_flags_mock:
            # Act
            self.model.set_enabled_all(value)

        # Assert
        self.assertEqual(get_flags_mock.call_count, 1)
        self.assertEqual(get_flags_mock.call_args, call(value))

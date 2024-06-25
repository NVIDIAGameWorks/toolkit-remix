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

import omni.kit.test
from omni.flux.wizard.widget import WizardModel, WizardPage


class TestWizardModel(omni.kit.test.AsyncTestCase):
    # Before running each test
    async def setUp(self):
        pass

    # After running each test
    async def tearDown(self):
        pass

    async def test_get_active_item_return_active_item(self):
        # Arrange
        item = WizardPage()
        model = WizardModel(Mock())

        # Act
        model._active_item = item  # noqa PLW0212

        # Assert
        self.assertEqual(item, model.get_active_item())

    async def test_reset_active_item_sets_root_item_as_active_item_and_triggers_event(self):
        # Arrange
        item_1 = WizardPage()
        item_2 = WizardPage()

        with patch.object(WizardModel, "on_active_item_changed") as mock:
            model = WizardModel(item_1)
            model._active_item = item_2  # noqa PLW0212

            # Act
            model.reset_active_item()

        # Assert
        self.assertEqual(1, mock.call_count)
        self.assertEqual(item_1, model._active_item)  # noqa PLW0212

    async def test_go_next_has_next_sets_item_next_as_active_item_and_triggers_active_items_changed_event(self):
        # Arrange
        item_1 = WizardPage()
        item_2 = WizardPage(next_page=item_1)

        with patch.object(WizardModel, "on_active_item_changed") as mock:
            model = WizardModel(item_2)

            # Act
            model.go_next()

        # Assert
        self.assertEqual(1, mock.call_count)
        self.assertEqual(item_1, model._active_item)  # noqa PLW0212

    async def test_go_next_has_no_next_triggers_items_completed_event(self):
        # Arrange
        item_1 = WizardPage()

        with patch.object(WizardModel, "on_items_completed") as mock:
            model = WizardModel(item_1)

            # Act
            model.go_next()

        # Assert
        self.assertEqual(1, mock.call_count)
        self.assertEqual(item_1, model._active_item)  # noqa PLW0212

    async def test_go_previous_sets_item_previous_as_active_item_and_triggers_event(self):
        # Arrange
        item_1 = WizardPage()
        item_2 = WizardPage(previous_page=item_1)

        with patch.object(WizardModel, "on_active_item_changed") as mock:
            model = WizardModel(item_2)

            # Act
            model.go_previous()

        # Assert
        self.assertEqual(1, mock.call_count)
        self.assertEqual(item_1, model._active_item)  # noqa PLW0212

    async def test_on_active_item_changed_sets_request_fns(self):
        # Arrange
        item = WizardPage()
        model = WizardModel(item)

        with (
            patch.object(WizardPage, "set_request_next_fn") as next_fn_mock,
            patch.object(WizardPage, "set_request_previous_fn") as previous_fn_mock,
            patch.object(WizardModel, "go_next") as go_next_mock,
            patch.object(WizardModel, "go_previous") as go_previous_mock,
        ):
            # Act
            model.on_active_item_changed()

        # Assert
        self.assertEqual(1, next_fn_mock.call_count)
        self.assertEqual(1, previous_fn_mock.call_count)

        self.assertEqual(call(go_next_mock), next_fn_mock.call_args)
        self.assertEqual(call(go_previous_mock), previous_fn_mock.call_args)

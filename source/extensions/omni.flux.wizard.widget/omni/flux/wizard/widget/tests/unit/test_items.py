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

from unittest.mock import Mock, patch

import omni.kit.test
from omni.flux.wizard.widget import WizardPage


class TestWizardPage(omni.kit.test.AsyncTestCase):
    # Before running each test
    async def setUp(self):
        pass

    # After running each test
    async def tearDown(self):
        pass

    async def test_previous_returns_previous(self):
        # Arrange
        item_1 = WizardPage(previous_page=None)
        item_2 = WizardPage(previous_page=item_1)

        # Act
        pass

        # Assert
        self.assertEqual(None, item_1.previous_page)
        self.assertEqual(item_1, item_2.previous_page)

    async def test_next_returns_next(self):
        # Arrange
        item_1 = WizardPage(next_page=None)
        item_2 = WizardPage(next_page=item_1)

        # Act
        pass

        # Assert
        self.assertEqual(None, item_1.next_page)
        self.assertEqual(item_1, item_2.next_page)

    async def test_next_setter_sets_next(self):
        # Arrange
        item_1 = WizardPage(next_page=None)
        item_2 = WizardPage(next_page=item_1)

        # Act
        item_1.next_page = item_2
        item_2.next_page = None

        # Assert
        self.assertEqual(item_2, item_1.next_page)
        self.assertEqual(None, item_2.next_page)

    async def test_previous_text_returns_previous_text(self):
        # Arrange
        previous_text = "Test"

        item_1 = WizardPage()
        item_2 = WizardPage(previous_text=previous_text)

        # Act
        pass

        # Assert
        self.assertEqual("Previous", item_1.previous_text)
        self.assertEqual(previous_text, item_2.previous_text)

    async def test_next_text_returns_next_text(self):
        # Arrange
        next_text = "Test"

        item_1 = WizardPage()
        item_2 = WizardPage(next_text=next_text)

        # Act
        pass

        # Assert
        self.assertEqual("Next", item_1.next_text)
        self.assertEqual(next_text, item_2.next_text)

    async def test_done_text_returns_done_text(self):
        # Arrange
        done_text = "Test"

        item_1 = WizardPage()
        item_2 = WizardPage(done_text=done_text)

        # Act
        pass

        # Assert
        self.assertEqual("Done", item_1.done_text)
        self.assertEqual(done_text, item_2.done_text)

    async def test_blocked_returns_blocked(self):
        # Arrange
        blocked = True

        item_1 = WizardPage()
        item_2 = WizardPage(blocked=blocked)

        # Act
        pass

        # Assert
        self.assertEqual(False, item_1.blocked)
        self.assertEqual(True, item_2.blocked)

    async def test_blocked_setter_value_changed_triggers_event(self):
        await self.__run_test_blocked_setter_triggers_event(True)

    async def test_blocked_setter_value_same_does_not_trigger_event(self):
        await self.__run_test_blocked_setter_triggers_event(False)

    async def test_hide_navigation_returns_hide_navigation(self):
        # Arrange
        hide_navigation = True

        item_1 = WizardPage()
        item_2 = WizardPage(hide_navigation=hide_navigation)

        # Act
        pass

        # Assert
        self.assertEqual(False, item_1.hide_navigation)
        self.assertEqual(True, item_2.hide_navigation)

    async def test_payload_returns_payload_with_all_previous_payload(self):
        # Arrange
        item_1 = WizardPage(previous_page=None)
        item_2 = WizardPage(previous_page=item_1)
        item_3 = WizardPage(previous_page=item_2)

        item_1_payload = {"1": "Test"}
        item_2_payload = {"2": "Test"}
        item_3_payload = {"3": "Test"}

        item_1.payload = item_1_payload
        item_2.payload = item_2_payload
        item_3.payload = item_3_payload

        # Act
        pass

        # Assert
        self.assertEqual(item_1_payload, item_1.payload)

        item_2_final_payload = item_2_payload.copy()
        item_2_final_payload.update(item_1_payload)
        self.assertEqual(item_2_final_payload, item_2.payload)

        item_3_final_payload = item_3_payload.copy()
        item_3_final_payload.update(item_2_payload)
        item_3_final_payload.update(item_1_payload)
        self.assertEqual(item_3_final_payload, item_3.payload)

    async def test_payload_setter_updates_dictionary(self):
        # Arrange
        payload = {"Test": "Test"}
        payload_modified = {"Test": "Modified"}
        payload_added = {"Other": "Test"}

        item_1 = WizardPage()
        item_1.payload = payload

        item_2 = WizardPage()
        item_2.payload = payload

        # Act
        item_1.payload = payload_modified
        item_2.payload = payload_added

        # Assert
        self.assertEqual(payload_modified, item_1.payload)

        final_payload_added = payload.copy()
        final_payload_added.update(payload_added)
        self.assertEqual(final_payload_added, item_2.payload)

    async def test_set_request_next_fn_sets_request_next_fn(self):
        # Arrange
        item = WizardPage()
        mock = Mock()

        # Act
        item.set_request_next_fn(mock)

        # Assert
        self.assertEqual(mock, item._request_next_fn)  # noqa PLW0212

    async def test_request_next_no_fn_set_raises(self):
        # Arrange
        item = WizardPage()

        # Act
        with self.assertRaises(NotImplementedError) as cm:
            item.request_next()

        # Assert
        self.assertEqual("The request_next function must be set before it's called", str(cm.exception))

    async def test_request_next_fn_set_calls_fn(self):
        # Arrange
        item = WizardPage()
        mock = Mock()
        item._request_next_fn = mock  # noqa PLW0212

        # Act
        item.request_next()

        # Assert
        self.assertEqual(1, mock.call_count)

    async def test_set_request_previous_fn_sets_request_previous_fn(self):
        # Arrange
        item = WizardPage()
        mock = Mock()

        # Act
        item.set_request_previous_fn(mock)

        # Assert
        self.assertEqual(mock, item._request_previous_fn)  # noqa PLW0212

    async def test_request_previous_no_fn_set_raises(self):
        # Arrange
        item = WizardPage()

        # Act
        with self.assertRaises(NotImplementedError) as cm:
            item.request_previous()

        # Assert
        self.assertEqual("The request_previous function must be set before it's called", str(cm.exception))

    async def test_request_previous_fn_set_calls_fn(self):
        # Arrange
        item = WizardPage()
        mock = Mock()
        item._request_previous_fn = mock  # noqa PLW0212

        # Act
        item.request_previous()

        # Assert
        self.assertEqual(1, mock.call_count)

    async def __run_test_blocked_setter_triggers_event(self, value_changed: bool):

        # Arrange
        blocked = True
        new_value = not blocked if value_changed else blocked
        item = WizardPage(blocked=blocked)

        # Act
        with patch.object(WizardPage, "on_blocked_changed") as mock:
            item.blocked = new_value

        # Assert
        self.assertEqual(new_value, item.blocked)
        self.assertEqual(1 if value_changed else 0, mock.call_count)

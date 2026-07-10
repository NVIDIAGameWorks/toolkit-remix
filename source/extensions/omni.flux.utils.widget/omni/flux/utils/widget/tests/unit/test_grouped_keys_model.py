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

from omni.flux.utils.widget import InMemoryGroupedKeysModel

__all__ = ["TestInMemoryGroupedKeysModel"]


class TestInMemoryGroupedKeysModel(omni.kit.test.AsyncTestCase):
    async def test_commit_payload_stores_a_copy(self):
        # Arrange
        model = InMemoryGroupedKeysModel(group_ids=["gradient"])
        payload = {"times": [0.0], "values": [(1.0, 0.0, 0.0, 1.0)]}

        # Act
        model.commit_payload("gradient", payload)
        payload["times"].append(1.0)
        stored = model.get_payload("gradient")

        # Assert
        self.assertEqual(stored["times"], [0.0])

    async def test_get_payload_returns_a_copy(self):
        # Arrange
        model = InMemoryGroupedKeysModel(payloads={"curve": {"times": [0.0], "values": [1.0]}})

        # Act
        payload = model.get_payload("curve")
        payload["values"].append(2.0)

        # Assert
        self.assertEqual(model.get_payload("curve")["values"], [1.0])

    async def test_subscribe_receives_external_change_group_id(self):
        # Arrange
        model = InMemoryGroupedKeysModel(group_ids=["curve"])
        notifications: list[str] = []
        subscription = model.subscribe(notifications.append)

        # Act
        model.simulate_external_change("curve", {"times": [0.0], "values": [1.0]})

        # Assert
        self.assertEqual(notifications, ["curve"])
        del subscription

    async def test_begin_and_end_edit_are_noops(self):
        # Arrange
        model = InMemoryGroupedKeysModel(group_ids=["curve"])

        # Act / Assert
        model.begin_edit("curve")
        model.end_edit("curve")

    async def test_display_name_falls_back_to_group_id(self):
        # Arrange
        model = InMemoryGroupedKeysModel(group_ids=["curve"])

        # Act / Assert
        self.assertEqual(model.get_display_name("curve"), "curve")

    async def test_display_name_uses_mapping(self):
        # Arrange
        model = InMemoryGroupedKeysModel(group_ids=["curve"], display_names={"curve": "Opacity"})

        # Act / Assert
        self.assertEqual(model.get_display_name("curve"), "Opacity")

    async def test_group_ids_preserve_input_order(self):
        # Arrange
        model = InMemoryGroupedKeysModel(group_ids=["z", "x", "y"])

        # Act / Assert
        self.assertEqual(model.group_ids, ["z", "x", "y"])

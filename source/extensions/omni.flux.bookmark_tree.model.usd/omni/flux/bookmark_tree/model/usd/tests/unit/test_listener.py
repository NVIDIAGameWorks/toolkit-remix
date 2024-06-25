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
import omni.usd
from omni.flux.bookmark_tree.model.usd import USDListener, get_usd_listener_instance
from omni.kit.test_suite.helpers import wait_stage_loading


class TestListener(omni.kit.test.AsyncTestCase):

    # Before running each test
    async def setUp(self):
        await omni.usd.get_context().new_stage_async()
        self.stage = omni.usd.get_context().get_stage()

    # After running each test
    async def tearDown(self):
        await wait_stage_loading()
        if omni.usd.get_context().get_stage():
            await omni.usd.get_context().close_stage_async()
        self.stage = None

    async def test_refresh_all_should_refresh_all_models(self):
        # Arrange
        mock_models = {Mock(), Mock(), Mock(), Mock()}

        listener = get_usd_listener_instance()
        listener._models = mock_models  # noqa PLW0212

        # Act
        listener.refresh_all()

        # Assert
        for mock in mock_models:
            self.assertEqual(1, mock.refresh.call_count)

    async def test_add_model_existing_stage_should_store_model(self):
        await self.__run_test_add_model(True)

    async def test_add_model_new_stage_should_store_model_and_call_enable_listener_for_stage(self):
        await self.__run_test_add_model(False)

    async def test_remove_model_stage_used_should_remove_model(self):
        await self.__run_test_remove_model(True)

    async def test_remove_model_no_stage_used_should_remove_model_and_call_disable_listener_for_stage(self):
        await self.__run_test_remove_model(False)

    async def __run_test_add_model(self, use_existing_stage: bool):
        # Arrange
        new_stage = Mock()
        existing_stage = Mock()

        new_mock = Mock()
        new_mock.stage = existing_stage if use_existing_stage else new_stage

        existing_mock = Mock()
        existing_mock.stage = existing_stage

        listener = get_usd_listener_instance()
        listener._models = {existing_mock}  # noqa PLW0212

        # Act
        with patch.object(USDListener, "_enable_listener") as enable_listener_mock:
            listener.add_model(new_mock)

        # Assert
        self.assertEqual(0 if use_existing_stage else 1, enable_listener_mock.call_count)
        if not use_existing_stage:
            self.assertEqual(call(new_stage), enable_listener_mock.call_args)

        self.assertEqual(2, len(listener._models))  # noqa PLW0212
        self.assertSetEqual({existing_mock, new_mock}, listener._models)  # noqa PLW0212

    async def __run_test_remove_model(self, used_stage: bool):
        # Arrange
        to_remove_stage = Mock()
        existing_stage = Mock()

        to_remove_mock = Mock()
        to_remove_mock.stage = existing_stage if used_stage else to_remove_stage

        existing_mock = Mock()
        existing_mock.stage = existing_stage

        listener = get_usd_listener_instance()
        listener._models = {existing_mock, to_remove_mock}  # noqa PLW0212

        # Act
        with patch.object(USDListener, "_disable_listener") as disable_listener_mock:
            listener.remove_model(to_remove_mock)

        # Assert
        self.assertEqual(0 if used_stage else 1, disable_listener_mock.call_count)
        if not used_stage:
            self.assertEqual(call(to_remove_stage), disable_listener_mock.call_args)

        self.assertEqual(1, len(listener._models))  # noqa PLW0212
        self.assertSetEqual({existing_mock}, listener._models)  # noqa PLW0212

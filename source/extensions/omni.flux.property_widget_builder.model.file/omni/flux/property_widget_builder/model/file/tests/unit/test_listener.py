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

from types import SimpleNamespace
from unittest.mock import Mock, patch

import omni.kit.test
from omni.flux.property_widget_builder.model.file import listener as _listener_module
from omni.flux.property_widget_builder.model.file.listener import FileListener


class TestFileListener(omni.kit.test.AsyncTestCase):
    async def test_add_model_registers_interaction_listener(self):
        # Arrange
        listener = FileListener()
        model = SimpleNamespace(path="omniverse://test.usda")
        subscription = Mock()

        # Act
        with (
            patch.object(listener, "_enable_listener"),
            patch.object(
                _listener_module,
                "_register_interaction_end_listener",
                return_value=subscription,
            ) as register_mock,
        ):
            listener.add_model(model)

        # Assert
        register_mock.assert_called_once_with(listener._on_interaction_finished)
        self.assertIs(listener._interaction_listener, subscription)

    async def test_file_change_during_interaction_defers_refresh(self):
        # Arrange
        listener = FileListener()
        model = SimpleNamespace(path="omniverse://test.usda", refresh=Mock())
        listener._models = [model]

        with patch.object(_listener_module, "_is_any_interaction_active", return_value=True):
            # Act
            listener._on_file_changed(model.path)

        # Assert
        self.assertEqual({model.path: None}, listener._pending_paths)
        model.refresh.assert_not_called()

    async def test_interaction_end_flushes_pending_file_change_once(self):
        # Arrange
        listener = FileListener()
        model = SimpleNamespace(path="omniverse://test.usda", refresh=Mock())
        listener._models = [model]
        listener._pending_paths[model.path] = None

        with patch.object(_listener_module, "_is_any_interaction_active", return_value=False):
            # Act
            listener._on_interaction_finished(Mock())

        # Assert
        self.assertEqual({}, listener._pending_paths)
        model.refresh.assert_called_once_with()

    async def test_file_change_without_interaction_refreshes_immediately(self):
        # Arrange
        listener = FileListener()
        model = SimpleNamespace(path="omniverse://test.usda", refresh=Mock())

        # Act
        with (
            patch.object(listener, "_enable_listener"),
            patch.object(_listener_module, "_is_any_interaction_active", return_value=False),
        ):
            listener.add_model(model)
            listener._on_file_changed(model.path)

        # Assert
        model.refresh.assert_called_once_with()

    async def test_add_model_reuses_existing_file_listener_for_same_path(self):
        # Arrange
        listener = FileListener()
        model_1 = SimpleNamespace(path="omniverse://test.usda")
        model_2 = SimpleNamespace(path="omniverse://test.usda")

        # Act
        with (
            patch.object(listener, "_enable_listener") as enable_listener_mock,
            patch.object(listener, "_enable_interaction_listener"),
        ):
            listener.add_model(model_1)
            listener.add_model(model_2)

        # Assert
        enable_listener_mock.assert_called_once_with(model_1.path)
        self.assertEqual([model_1, model_2], listener._models)

    async def test_remove_model_keeps_file_listener_until_last_model_for_path_is_removed(self):
        # Arrange
        listener = FileListener()
        model_1 = SimpleNamespace(path="omniverse://test.usda")
        model_2 = SimpleNamespace(path="omniverse://test.usda")
        listener._models = [model_1, model_2]
        listener._pending_paths[model_1.path] = None

        # Act
        with (
            patch.object(listener, "_disable_listener") as disable_listener_mock,
            patch.object(listener, "_disable_interaction_listener") as disable_interaction_listener_mock,
        ):
            listener.remove_model(model_1)

        # Assert
        disable_listener_mock.assert_not_called()
        disable_interaction_listener_mock.assert_not_called()
        self.assertEqual([model_2], listener._models)
        self.assertEqual({model_1.path: None}, listener._pending_paths)

    async def test_remove_model_disables_file_and_interaction_listeners_for_last_model(self):
        # Arrange
        listener = FileListener()
        model = SimpleNamespace(path="omniverse://test.usda")
        listener._models = [model]
        listener._pending_paths[model.path] = None

        # Act
        with (
            patch.object(listener, "_disable_listener") as disable_listener_mock,
            patch.object(listener, "_disable_interaction_listener") as disable_interaction_listener_mock,
        ):
            listener.remove_model(model)

        # Assert
        disable_listener_mock.assert_called_once_with(model.path)
        disable_interaction_listener_mock.assert_called_once_with()
        self.assertEqual([], listener._models)
        self.assertEqual({}, listener._pending_paths)

    async def test_interaction_end_keeps_pending_paths_when_another_interaction_is_active(self):
        # Arrange
        listener = FileListener()
        model = SimpleNamespace(path="omniverse://test.usda", refresh=Mock())
        listener._models = [model]
        listener._pending_paths[model.path] = None

        with patch.object(_listener_module, "_is_any_interaction_active", return_value=True):
            # Act
            listener._on_interaction_finished(Mock())

        # Assert
        self.assertEqual({model.path: None}, listener._pending_paths)
        model.refresh.assert_not_called()

    async def test_refresh_path_only_refreshes_matching_models(self):
        # Arrange
        listener = FileListener()
        matching_model = SimpleNamespace(path="omniverse://matching.usda", refresh=Mock())
        other_model = SimpleNamespace(path="omniverse://other.usda", refresh=Mock())
        listener._models = [matching_model, other_model]

        # Act
        listener._refresh_path(matching_model.path)

        # Assert
        matching_model.refresh.assert_called_once_with()
        other_model.refresh.assert_not_called()

    async def test_destroy_cancels_file_listeners_and_revokes_interaction_listener(self):
        # Arrange
        listener = FileListener()
        listener._listeners = {
            "omniverse://first.usda": Mock(),
            "omniverse://second.usda": Mock(),
        }
        listener._interaction_listener = Mock()
        file_listeners = tuple(listener._listeners.values())
        interaction_listener = listener._interaction_listener

        # Act
        listener.destroy()

        # Assert
        for file_listener in file_listeners:
            file_listener.cancel.assert_called_once_with()
        interaction_listener.Revoke.assert_called_once_with()
        self.assertIsNone(listener._listeners)

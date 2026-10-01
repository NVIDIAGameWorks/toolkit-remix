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

import asyncio
from contextlib import suppress
from types import SimpleNamespace
from unittest.mock import Mock, patch

import omni.client
import omni.kit.test
from omni.flux.property_widget_builder.model.file import listener as _listener_module
from omni.flux.property_widget_builder.model.file.items import FileAttributeItem
from omni.flux.property_widget_builder.model.file.listener import FileListener
from omni.flux.property_widget_builder.model.file.model import FileModel


class TestFileListener(omni.kit.test.AsyncTestCase):
    async def test_first_poll_of_initialized_model_does_not_rebuild_rows_or_notify_unchanged_values(self):
        """Keep initialized rows and value notifications unchanged on the first poll."""
        # Arrange
        path = "omniverse://server/file.usda"
        entry = self._create_entry()
        listener = FileListener()
        with patch.object(omni.client, "stat", return_value=(omni.client.Result.OK, entry)):
            model = FileModel(path)
            item = FileAttributeItem(path, "size")
            model.set_items([item])
            listener._models = [model]
            with (
                patch.object(model, "_item_changed") as item_changed_mock,
                patch.object(item.value_models[0], "_value_changed") as value_changed_mock,
            ):
                # Act
                await self._poll_file(listener, path, [(omni.client.Result.OK, entry)])

        # Assert
        item_changed_mock.assert_not_called()
        value_changed_mock.assert_not_called()

    async def test_changed_file_attribute_updates_value_without_rebuilding_rows(self):
        """Notify a changed attribute value without rebuilding its property row."""
        # Arrange
        path = "omniverse://server/file.usda"
        entry = self._create_entry()
        with patch.object(omni.client, "stat", return_value=(omni.client.Result.OK, entry)):
            model = FileModel(path)
            item = FileAttributeItem(path, "size")
            model.set_items([item])
        listener = FileListener()
        listener._models = [model]
        entry.size = 256

        # Act
        with (
            patch.object(omni.client, "stat", return_value=(omni.client.Result.OK, entry)),
            patch.object(model, "_item_changed") as item_changed_mock,
            patch.object(item.value_models[0], "_value_changed") as value_changed_mock,
        ):
            listener._refresh_path(path)

        # Assert
        self.assertEqual(256, item.value_models[0].get_value())
        value_changed_mock.assert_called_once_with()
        item_changed_mock.assert_not_called()

    async def test_polling_unchanged_file_refreshes_model_only_once(self):
        """Refresh once across repeated polls with unchanged metadata."""
        # Arrange
        path = "omniverse://server/file.usda"
        listener = FileListener()
        model = SimpleNamespace(path=path, refresh_values=Mock())
        listener._models = [model]
        stat_results = [(omni.client.Result.OK, self._create_entry()) for _ in range(3)]

        # Act
        await self._poll_file(listener, path, stat_results)

        # Assert
        self.assertEqual(1, model.refresh_values.call_count)

    async def test_polling_unreadable_then_readable_file_refreshes_model_again(self):
        """Refresh recovered readable metadata after an unreadable poll clears the cache."""
        # Arrange
        path = "omniverse://server/file.usda"
        entry = self._create_entry()
        listener = FileListener()
        model = SimpleNamespace(path=path, refresh_values=Mock())
        listener._models = [model]
        stat_results = [
            (omni.client.Result.OK, entry),
            (omni.client.Result.OK, SimpleNamespace(flags=0)),
            (omni.client.Result.OK, entry),
        ]

        # Act
        await self._poll_file(listener, path, stat_results)

        # Assert
        self.assertEqual(2, model.refresh_values.call_count)

    async def test_polling_changed_comment_refreshes_model_again(self):
        """Refresh again when a later poll reports a changed comment."""
        # Arrange
        path = "omniverse://server/file.usda"
        entry = self._create_entry()
        listener = FileListener()
        model = SimpleNamespace(path=path, refresh_values=Mock())
        listener._models = [model]
        stat_results = [
            (omni.client.Result.OK, entry),
            (omni.client.Result.OK, entry),
            (omni.client.Result.OK, self._create_entry(comment="after")),
        ]

        # Act
        await self._poll_file(listener, path, stat_results)

        # Assert
        self.assertEqual(2, model.refresh_values.call_count)

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
        model = SimpleNamespace(path="omniverse://test.usda", refresh_values=Mock())
        listener._models = [model]

        with patch.object(_listener_module, "_is_any_interaction_active", return_value=True):
            # Act
            listener._on_file_changed(model.path)

        # Assert
        self.assertEqual({model.path: None}, listener._pending_paths)
        model.refresh_values.assert_not_called()

    async def test_interaction_end_flushes_pending_file_change_once(self):
        # Arrange
        listener = FileListener()
        model = SimpleNamespace(path="omniverse://test.usda", refresh_values=Mock())
        listener._models = [model]
        listener._pending_paths[model.path] = None

        with patch.object(_listener_module, "_is_any_interaction_active", return_value=False):
            # Act
            listener._on_interaction_finished(Mock())

        # Assert
        self.assertEqual({}, listener._pending_paths)
        model.refresh_values.assert_called_once_with()

    async def test_file_change_without_interaction_refreshes_immediately(self):
        # Arrange
        listener = FileListener()
        model = SimpleNamespace(path="omniverse://test.usda", refresh_values=Mock())

        # Act
        with (
            patch.object(listener, "_enable_listener"),
            patch.object(_listener_module, "_is_any_interaction_active", return_value=False),
        ):
            listener.add_model(model)
            listener._on_file_changed(model.path)

        # Assert
        model.refresh_values.assert_called_once_with()

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
        listener._entry_states[model_1.path] = ("snapshot",)
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
        self.assertEqual({model_1.path: ("snapshot",)}, listener._entry_states)
        self.assertEqual({model_1.path: None}, listener._pending_paths)

    async def test_remove_model_disables_file_and_interaction_listeners_for_last_model(self):
        # Arrange
        listener = FileListener()
        model = SimpleNamespace(path="omniverse://test.usda")
        listener._models = [model]
        listener._entry_states[model.path] = ("snapshot",)
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
        self.assertEqual({}, listener._entry_states)
        self.assertEqual({}, listener._pending_paths)

    async def test_interaction_end_keeps_pending_paths_when_another_interaction_is_active(self):
        # Arrange
        listener = FileListener()
        model = SimpleNamespace(path="omniverse://test.usda", refresh_values=Mock())
        listener._models = [model]
        listener._pending_paths[model.path] = None

        with patch.object(_listener_module, "_is_any_interaction_active", return_value=True):
            # Act
            listener._on_interaction_finished(Mock())

        # Assert
        self.assertEqual({model.path: None}, listener._pending_paths)
        model.refresh_values.assert_not_called()

    async def test_refresh_path_only_refreshes_matching_models(self):
        # Arrange
        listener = FileListener()
        matching_model = SimpleNamespace(path="omniverse://matching.usda", refresh_values=Mock())
        other_model = SimpleNamespace(path="omniverse://other.usda", refresh_values=Mock())
        listener._models = [matching_model, other_model]

        # Act
        listener._refresh_path(matching_model.path)

        # Assert
        matching_model.refresh_values.assert_called_once_with()
        other_model.refresh_values.assert_not_called()

    async def test_destroy_cancels_file_listeners_and_revokes_interaction_listener(self):
        # Arrange
        listener = FileListener()
        listener._listeners = {
            "omniverse://first.usda": Mock(),
            "omniverse://second.usda": Mock(),
        }
        listener._interaction_listener = Mock()
        listener._entry_states["omniverse://first.usda"] = ("snapshot",)
        file_listeners = tuple(listener._listeners.values())
        interaction_listener = listener._interaction_listener

        # Act
        listener.destroy()

        # Assert
        for file_listener in file_listeners:
            file_listener.cancel.assert_called_once_with()
        interaction_listener.Revoke.assert_called_once_with()
        self.assertIsNone(listener._listeners)
        self.assertEqual({}, listener._entry_states)

    @staticmethod
    def _create_entry(comment: str = "before") -> SimpleNamespace:
        """Create controlled readable metadata for a polling scenario."""
        return SimpleNamespace(
            access=None,
            comment=comment,
            created_by=None,
            created_time=None,
            deleted_by=None,
            deleted_time=None,
            flags=omni.client.ItemFlags.READABLE_FILE,
            hash=None,
            locked_by=None,
            modified_by=None,
            modified_time=None,
            relative_path=None,
            size=128,
            version=None,
        )

    async def _poll_file(self, listener: FileListener, path: str, stat_results: list[tuple]):
        """Poll controlled stat results and cancel the listener after the last result."""
        polls_complete = asyncio.Event()
        results = iter(enumerate(stat_results, start=1))

        async def stat_async(_path):
            """Return the next controlled result and signal the final poll."""
            poll_count, result = next(results)
            if poll_count == len(stat_results):
                polls_complete.set()
            return result

        with (
            patch.object(omni.client, "stat_async", side_effect=stat_async),
            patch.object(_listener_module, "_is_any_interaction_active", return_value=False),
        ):
            task = asyncio.create_task(listener._FileListener__async_listener(path))
            try:
                await asyncio.wait_for(polls_complete.wait(), timeout=10)
            finally:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

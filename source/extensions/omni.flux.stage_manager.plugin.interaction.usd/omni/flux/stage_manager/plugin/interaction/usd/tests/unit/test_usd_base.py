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
import threading
from types import SimpleNamespace
from unittest import mock

import carb
import omni.kit.app
from omni.kit.test import AsyncTestCase
from omni.flux.stage_manager.factory import StageManagerItem
from omni.flux.stage_manager.factory.plugins.filter_plugin import StageManagerFilterPlugin as _StageManagerFilterPlugin
from omni.flux.stage_manager.factory.plugins.interaction_plugin import (
    StageManagerInteractionPlugin as _StageManagerInteractionPlugin,
)
from omni.flux.stage_manager.plugin.interaction.usd.base.usd_base import (
    RefreshRule as _RefreshRule,
    StageManagerUSDInteractionPlugin as _StageManagerUSDInteractionPlugin,
    USDEventFilteringRules as _USDEventFilteringRules,
)
from pydantic import Field
from pxr import Sdf


class _TestInteractionPlugin(_StageManagerUSDInteractionPlugin):
    pass


class _TestFilterPlugin(_StageManagerFilterPlugin):
    display_name: str = Field(default="Test Filter", exclude=True)
    tooltip: str = Field(default="", exclude=True)
    filter_value: str = Field(default="All")

    def filter_predicate(self, item: StageManagerItem) -> bool:
        return True

    def build_ui(self, *args, **kwargs):
        pass


def _make_tree_item(path: str):
    """Return a proxy containing a data-backed canonical tree item."""
    original_item = SimpleNamespace(path=path, data=object())
    return mock.Mock(original_tree_item=original_item)


class TestStageManagerUSDInteractionPlugin(AsyncTestCase):
    async def test_update_context_items_should_set_context_name_before_factory_refresh(self):
        # Arrange
        plugin = self._make_plugin()
        plugin._is_active = True
        call_order = []

        async def _update_context_items():
            call_order.append("factory_refresh")

        # Act
        with (
            mock.patch.object(plugin, "_set_context_name", side_effect=lambda: call_order.append("set_context_name")),
            mock.patch.object(
                _StageManagerInteractionPlugin,
                "_update_context_items",
                side_effect=_update_context_items,
            ),
        ):
            await plugin._update_context_items()

        # Assert
        self.assertEqual(["set_context_name", "factory_refresh"], call_order)

    async def test_get_refresh_expand_filtered_roots_uses_explicit_filter_active_state(self):
        # Arrange
        cases = (
            ("active primary", [_TestFilterPlugin(enabled=True, filter_active=True)], [], True),
            (
                "inactive modified primary",
                [_TestFilterPlugin(enabled=True, filter_active=False, filter_value="Specific")],
                [],
                False,
            ),
            ("disabled active primary", [_TestFilterPlugin(enabled=False, filter_active=True)], [], False),
            ("active additional", [], [_TestFilterPlugin(enabled=False, filter_active=True)], True),
        )
        plugins = []
        for _, filters, additional_filters, _ in cases:
            plugin = self._make_plugin()
            plugin.filters = filters
            plugin.additional_filters = additional_filters
            plugins.append(plugin)

        # Act
        results = [plugin._get_refresh_expand_filtered_roots() for plugin in plugins]

        # Assert
        for (title, _, _, expected), result in zip(cases, results):
            with self.subTest(title=title):
                self.assertEqual(expected, result)

    def _make_plugin(self):
        return _TestInteractionPlugin.model_construct(
            tree=mock.MagicMock(),
            filters=[],
            context_filters=[],
            internal_context_filters=[],
            columns=[],
            additional_filters=[],
            compatible_filters=[],
            compatible_widgets=[],
            compatible_trees=[],
            filtering_rules=_USDEventFilteringRules(),
        )

    def _set_delayed_selection_tree_widget(self, plugin: _StageManagerUSDInteractionPlugin):
        class _TreeWidget:
            def __init__(self):
                self.selection = []

            async def set_selection_async(self, items):
                self.selection = list(items)

                async def _emit_selection_changed_later():
                    await omni.kit.app.get_app().next_update_async()
                    plugin._on_selection_changed(items)

                asyncio.ensure_future(_emit_selection_changed_later())

        plugin._tree_widget = _TreeWidget()

    def _make_notice(
        self,
        changed_info_only_paths: list[Sdf.Path] | None = None,
        resynced_paths: list[Sdf.Path] | None = None,
    ):
        notice = mock.MagicMock()
        notice.GetChangedInfoOnlyPaths.return_value = changed_info_only_paths or []
        notice.GetResyncedPaths.return_value = resynced_paths or []
        notice.GetChangedFields.return_value = []
        return notice

    async def test_item_change_reapplies_current_usd_selection_without_expansion_state_handshake(self):
        # Arrange
        plugin = self._make_plugin()
        model = plugin.tree.model

        with (
            mock.patch.object(_StageManagerInteractionPlugin, "_on_item_changed"),
            mock.patch.object(plugin, "_update_tree_selection", return_value=None) as update_tree_selection,
            mock.patch.object(plugin, "_should_expand_filtered_items") as should_expand_filtered_items,
            mock.patch("omni.kit.app.get_app") as get_app,
        ):
            get_app.return_value.next_update_async = mock.AsyncMock()

            # Act
            await plugin._on_item_changed_async(model, None)

        # Assert
        get_app.return_value.next_update_async.assert_awaited_once_with()
        update_tree_selection.assert_called_once_with()
        should_expand_filtered_items.assert_not_called()

    async def test_on_item_changed_async_waits_for_selection_sync(self):
        # Arrange
        plugin = self._make_plugin()
        model = plugin.tree.model
        selection_started = asyncio.Event()
        release_selection = asyncio.Event()

        async def _update_selection():
            selection_started.set()
            await release_selection.wait()

        selection_task = asyncio.ensure_future(_update_selection())

        with (
            mock.patch.object(_StageManagerInteractionPlugin, "_on_item_changed"),
            mock.patch.object(plugin, "_update_tree_selection", return_value=selection_task),
            mock.patch("omni.kit.app.get_app") as get_app,
        ):
            get_app.return_value.next_update_async = mock.AsyncMock()

            # Act
            item_changed_task = asyncio.ensure_future(plugin._on_item_changed_async(model, None))
            await selection_started.wait()
            was_pending = not item_changed_task.done()
            release_selection.set()
            await item_changed_task

        # Assert
        self.assertTrue(was_pending)

    async def test_item_changed_background_failure_is_logged_and_remains_awaitable(self):
        # Arrange
        plugin = self._make_plugin()
        error = RuntimeError("item change failed")

        with (
            mock.patch.object(plugin, "_on_item_changed_async", mock.AsyncMock(side_effect=error)),
            mock.patch.object(carb, "log_error") as log_error,
        ):
            # Act
            plugin._on_item_changed(plugin.tree.model, None)
            with self.assertRaises(RuntimeError):
                await plugin._items_changed_task
            await asyncio.sleep(0)

        # Assert
        log_error.assert_called_once()

    async def test_on_hidden_cancels_selection_tasks_before_destroying_tree_widget(self):
        # Arrange
        plugin = self._make_plugin()
        call_order = []
        plugin._tree_selection_task = mock.Mock(
            cancel=mock.Mock(side_effect=lambda: call_order.append("tree_selection_cancelled"))
        )
        plugin._items_changed_task = mock.Mock(
            cancel=mock.Mock(side_effect=lambda: call_order.append("item_change_cancelled"))
        )
        plugin._tree_widget = mock.Mock(destroy=mock.Mock(side_effect=lambda: call_order.append("widget_destroyed")))

        # Act
        plugin.on_hidden()

        # Assert
        self.assertEqual(
            ["tree_selection_cancelled", "item_change_cancelled", "widget_destroyed"],
            call_order,
        )
        self.assertIsNone(plugin._tree_selection_task)
        self.assertIsNone(plugin._items_changed_task)

    async def test_set_active_false_cancels_selection_tasks(self):
        # Arrange
        plugin = self._make_plugin()
        plugin._is_active = True
        plugin._tree_selection_task = asyncio.ensure_future(asyncio.Event().wait())
        plugin._items_changed_task = asyncio.ensure_future(asyncio.Event().wait())
        tree_selection_task = plugin._tree_selection_task
        items_changed_task = plugin._items_changed_task

        # Act
        plugin.set_active(False)

        # Assert
        self.assertGreater(tree_selection_task.cancelling(), 0)
        self.assertGreater(items_changed_task.cancelling(), 0)
        self.assertIsNone(plugin._tree_selection_task)
        self.assertIsNone(plugin._items_changed_task)

    async def test_update_tree_selection_clears_stale_tree_selection_when_usd_selection_has_no_matching_items(self):
        # Arrange
        plugin = self._make_plugin()
        plugin.synchronize_selection = True
        plugin._is_active = True
        plugin._context_name = ""
        plugin._tree_selection_task = SimpleNamespace(cancelled=lambda: False)

        stale_item = _make_tree_item("/World/Mesh")
        plugin.tree.model.selection = [stale_item]
        plugin.tree.model.find_items_async = mock.AsyncMock(
            side_effect=AssertionError("Selection synchronization must use the path lookup cache")
        )

        class _TreeWidget:
            def __init__(self):
                self.selection = [stale_item]

            async def set_selection_async(self, items):
                self.selection = list(items)
                plugin._on_selection_changed(items)

        plugin._tree_widget = _TreeWidget()

        with (
            mock.patch.object(plugin, "_get_selection", return_value=["/World/Light"]),
            mock.patch("omni.usd.get_context") as get_context,
        ):
            selection_mock = mock.MagicMock()
            context_mock = mock.MagicMock(get_selection=mock.MagicMock(return_value=selection_mock))
            get_context.return_value = context_mock

            # Act
            await plugin._update_tree_selection_async()

            # Assert
            self.assertEqual(plugin._tree_widget.selection, [])
            self.assertEqual(plugin.tree.model.selection, [])
            selection_mock.set_selected_prim_paths.assert_not_called()

    async def test_update_tree_selection_clears_stale_tree_selection_when_usd_selection_is_empty(self):
        # Arrange
        plugin = self._make_plugin()
        plugin.synchronize_selection = True
        plugin._is_active = True
        plugin._context_name = ""
        plugin._tree_selection_task = SimpleNamespace(cancelled=lambda: False)

        stale_item = _make_tree_item("/World/Mesh")
        plugin.tree.model.selection = [stale_item]
        plugin.tree.model.find_items_async = mock.AsyncMock()

        class _TreeWidget:
            def __init__(self):
                self.selection = [stale_item]

            async def set_selection_async(self, items):
                self.selection = list(items)
                plugin._on_selection_changed(items)

        plugin._tree_widget = _TreeWidget()

        with (
            mock.patch.object(plugin, "_get_selection", return_value=[]),
            mock.patch("omni.usd.get_context") as get_context,
        ):
            selection_mock = mock.MagicMock()
            context_mock = mock.MagicMock(get_selection=mock.MagicMock(return_value=selection_mock))
            get_context.return_value = context_mock

            # Act
            await plugin._update_tree_selection_async()

            # Assert
            self.assertEqual(plugin._tree_widget.selection, [])
            plugin.tree.model.find_items_async.assert_not_called()
            self.assertEqual(plugin.tree.model.selection, [])
            selection_mock.set_selected_prim_paths.assert_not_called()

    async def test_update_tree_selection_selects_all_matching_items_for_duplicate_paths(self):
        # Arrange
        plugin = self._make_plugin()
        plugin.synchronize_selection = True
        plugin._is_active = True
        plugin._context_name = ""
        plugin._tree_selection_task = SimpleNamespace(cancelled=lambda: False)

        item_a = _make_tree_item("/World/Shared")
        item_b = _make_tree_item("/World/Shared")

        class _TreeModel:
            def __init__(self):
                self.selection = []

            def get_items_by_path(self, path):
                return [item_a, item_b] if path == "/World/Shared" else []

            async def find_items_async(self, _predicate):
                raise AssertionError("Path lookup should handle duplicate tree rows")

        class _TreeWidget:
            def __init__(self):
                self.selection = []

            async def set_selection_async(self, items):
                self.selection = list(items)

        plugin.tree.model = _TreeModel()
        plugin._tree_widget = _TreeWidget()

        with mock.patch.object(plugin, "_get_selection", return_value=["/World/Shared"]):
            # Act
            await plugin._update_tree_selection_async()

        # Assert
        self.assertEqual([item_a, item_b], plugin._tree_widget.selection)
        self.assertEqual([item_a, item_b], plugin.tree.model.selection)

    async def test_update_tree_selection_preserves_path_order_while_retaining_hidden_selection(self):
        # Arrange
        plugin = self._make_plugin()
        plugin.synchronize_selection = True
        plugin._is_active = True
        plugin._tree_selection_task = SimpleNamespace(cancelled=lambda: False)
        b_visible = _make_tree_item("/World/B")
        a_visible = _make_tree_item("/World/A")
        a_hidden = _make_tree_item("/World/A")
        plugin.tree.model.selection = [a_visible, a_hidden]
        plugin.tree.model.get_items_by_path.side_effect = lambda path: {
            "/World/B": [b_visible],
            "/World/A": [a_visible],
        }.get(path, [])
        plugin._tree_widget = SimpleNamespace(selection=[], set_selection_async=mock.AsyncMock())

        with mock.patch.object(plugin, "_get_selection", return_value=["/World/B", "/World/A"]):
            # Act
            await plugin._update_tree_selection_async()

        # Assert
        plugin._tree_widget.set_selection_async.assert_awaited_once_with([b_visible, a_visible, a_hidden])
        self.assertEqual([b_visible, a_visible, a_hidden], plugin.tree.model.selection)

    async def test_update_tree_selection_when_selection_changes_during_framing_applies_latest_selection(self):
        # Arrange
        plugin = self._make_plugin()
        plugin.synchronize_selection = True
        plugin._is_active = True
        item_a = _make_tree_item("/World/A")
        item_b = _make_tree_item("/World/B")
        selection = ["/World/A"]
        first_selection_started = asyncio.Event()
        release_first_selection = asyncio.Event()
        plugin.tree.model.selection = []
        plugin.tree.model.get_items_by_path.side_effect = lambda path: {
            "/World/A": [item_a],
            "/World/B": [item_b],
        }.get(path, [])
        tree_widget = SimpleNamespace(selection=[], call_count=0)

        async def _set_selection_async(items):
            tree_widget.call_count += 1
            if tree_widget.call_count == 1:
                first_selection_started.set()
                await release_first_selection.wait()
            tree_widget.selection = list(items)

        tree_widget.set_selection_async = _set_selection_async
        plugin._tree_widget = tree_widget

        with mock.patch.object(plugin, "_get_selection", side_effect=lambda: list(selection)):
            # Act
            selection_task = plugin._update_tree_selection()
            await first_selection_started.wait()
            selection[:] = ["/World/B"]
            plugin._update_tree_selection()
            release_first_selection.set()
            await selection_task

        # Assert
        self.assertEqual([item_b], plugin._tree_widget.selection)
        self.assertEqual([item_b], plugin.tree.model.selection)
        self.assertEqual(2, plugin._tree_widget.call_count)

    async def test_set_tree_widget_selection_skips_unchanged_membership(self):
        # Arrange
        plugin = self._make_plugin()
        item_a = _make_tree_item("/World/A")
        item_b = _make_tree_item("/World/B")
        plugin._tree_widget = SimpleNamespace(
            selection=[item_b, item_a],
            set_selection_async=mock.AsyncMock(),
        )

        # Act
        await plugin._set_tree_widget_selection_async([item_a, item_b])

        # Assert
        plugin._tree_widget.set_selection_async.assert_not_awaited()
        self.assertEqual([item_a, item_b], plugin.tree.model.selection)
        self.assertIsNone(plugin._programmatic_tree_selection_paths)

    async def test_set_tree_widget_selection_frames_changed_membership_once(self):
        # Arrange
        plugin = self._make_plugin()
        item_a = _make_tree_item("/World/A")
        item_b = _make_tree_item("/World/B")
        plugin._tree_widget = SimpleNamespace(
            selection=[item_a],
            set_selection_async=mock.AsyncMock(),
        )

        # Act
        await plugin._set_tree_widget_selection_async([item_a, item_b])

        # Assert
        plugin._tree_widget.set_selection_async.assert_awaited_once_with([item_a, item_b])
        self.assertEqual([item_a, item_b], plugin.tree.model.selection)
        self.assertEqual(("/World/A", "/World/B"), plugin._programmatic_tree_selection_paths)

    async def test_tree_item_paths_use_cached_paths_and_exclude_virtual_rows(self):
        # Arrange
        original_item = SimpleNamespace(
            path="/World/Cube",
            data=SimpleNamespace(GetPath=mock.Mock(side_effect=AssertionError("Live USD data must not be read"))),
        )
        item = SimpleNamespace(original_tree_item=original_item)
        virtual_item = SimpleNamespace(original_tree_item=SimpleNamespace(path="/Virtual/Materials", data=None))

        # Act
        paths = _StageManagerUSDInteractionPlugin._get_tree_item_paths([virtual_item, item])

        # Assert
        self.assertEqual(("/World/Cube",), paths)

    async def test_update_nickname_items_matches_canonical_data_and_notifies_proxy(self):
        # Arrange
        plugin = self._make_plugin()
        prim = mock.Mock()
        prim.GetPath.return_value = Sdf.Path("/World/Cube")
        original_item = SimpleNamespace(data=prim)
        proxy_item = SimpleNamespace(original_tree_item=original_item)
        plugin.tree.model.find_items.side_effect = lambda predicate: [proxy_item] if predicate(proxy_item) else []

        with mock.patch(
            "omni.flux.stage_manager.plugin.interaction.usd.base.usd_base._get_proto_from_prim",
            return_value=prim,
        ):
            # Act
            plugin._update_nickname_items({Sdf.Path("/World/Cube")})

        # Assert
        plugin.tree.model.notify_item_changed.assert_called_once_with(proxy_item)

    async def test_delayed_programmatic_empty_tree_selection_does_not_clear_usd_selection(self):
        # Arrange
        plugin = self._make_plugin()
        plugin.synchronize_selection = True
        plugin._context_name = ""
        self._set_delayed_selection_tree_widget(plugin)

        with (
            mock.patch.object(plugin, "_get_selection", return_value=["/World/Light"]),
            mock.patch("omni.usd.get_context") as get_context,
        ):
            selection_mock = mock.MagicMock()
            context_mock = mock.MagicMock(get_selection=mock.MagicMock(return_value=selection_mock))
            get_context.return_value = context_mock

            # Act
            await plugin._set_tree_widget_selection_async([])
            await omni.kit.app.get_app().next_update_async()
            await omni.kit.app.get_app().next_update_async()

            # Assert
            self.assertEqual(plugin._tree_widget.selection, [])
            selection_mock.set_selected_prim_paths.assert_not_called()

    async def test_delayed_programmatic_empty_tree_selection_does_not_override_interleaved_user_selection(self):
        # Arrange
        plugin = self._make_plugin()
        plugin.synchronize_selection = True
        plugin._context_name = ""
        user_item = _make_tree_item("/World/Mesh")
        self._set_delayed_selection_tree_widget(plugin)

        with (
            mock.patch.object(plugin, "_get_selection", return_value=["/World/Light"]),
            mock.patch("omni.usd.get_context") as get_context,
        ):
            selection_mock = mock.MagicMock()
            context_mock = mock.MagicMock(get_selection=mock.MagicMock(return_value=selection_mock))
            get_context.return_value = context_mock

            # Act
            await plugin._set_tree_widget_selection_async([])
            plugin._on_selection_changed([user_item])
            await omni.kit.app.get_app().next_update_async()
            await omni.kit.app.get_app().next_update_async()

            # Assert
            self.assertEqual(plugin._tree_widget.selection, [])
            self.assertEqual(selection_mock.set_selected_prim_paths.call_args_list, [mock.call(["/World/Mesh"])])

    async def test_user_empty_tree_selection_clears_usd_selection(self):
        # Arrange
        plugin = self._make_plugin()
        plugin._selection_update_lock = False
        plugin.synchronize_selection = True
        plugin._ignore_selection_update = False
        plugin._context_name = ""

        with (
            mock.patch.object(_StageManagerInteractionPlugin, "_on_selection_changed", autospec=True) as super_sel,
            mock.patch.object(plugin, "_get_selection", return_value=["/World/Light"]),
            mock.patch("omni.usd.get_context") as get_context,
        ):
            selection_mock = mock.MagicMock()
            context_mock = mock.MagicMock(get_selection=mock.MagicMock(return_value=selection_mock))
            get_context.return_value = context_mock

            # Act
            plugin._on_selection_changed([])

            # Assert
            super_sel.assert_called_once()
            selection_mock.set_selected_prim_paths.assert_called_once_with([])

    async def test_empty_tree_selection_during_refresh_does_not_clear_matching_usd_selection(self):
        # Arrange
        plugin = self._make_plugin()
        plugin._selection_update_lock = False
        plugin.synchronize_selection = True
        plugin._ignore_selection_update = False
        plugin._context_name = ""
        plugin._model_refresh_task = SimpleNamespace(done=lambda: False)
        selected_item = _make_tree_item("/World/Mesh")
        plugin.tree.model.selection = [selected_item]

        with (
            mock.patch.object(plugin, "_get_selection", return_value=["/World/Mesh"]),
            mock.patch("omni.usd.get_context") as get_context,
        ):
            selection_mock = mock.MagicMock()
            context_mock = mock.MagicMock(get_selection=mock.MagicMock(return_value=selection_mock))
            get_context.return_value = context_mock

            # Act
            plugin._on_selection_changed([])

            # Assert
            self.assertEqual(plugin.tree.model.selection, [selected_item])
            selection_mock.set_selected_prim_paths.assert_not_called()

    async def test_empty_tree_selection_during_refresh_clears_when_usd_selection_is_empty(self):
        # Arrange
        plugin = self._make_plugin()
        plugin._selection_update_lock = False
        plugin.synchronize_selection = True
        plugin._ignore_selection_update = False
        plugin._context_name = ""
        plugin._model_refresh_task = SimpleNamespace(done=lambda: False)
        selected_item = _make_tree_item("/World/Mesh")
        plugin.tree.model.selection = [selected_item]

        with (
            mock.patch.object(plugin, "_get_selection", return_value=[]),
            mock.patch("omni.usd.get_context") as get_context,
        ):
            selection_mock = mock.MagicMock()
            context_mock = mock.MagicMock(get_selection=mock.MagicMock(return_value=selection_mock))
            get_context.return_value = context_mock

            # Act
            plugin._on_selection_changed([])

            # Assert
            self.assertEqual(plugin.tree.model.selection, [])
            selection_mock.set_selected_prim_paths.assert_not_called()

    async def test_on_selection_changed_does_not_write_back_for_order_only_difference(self):
        # Arrange
        plugin = self._make_plugin()
        plugin._selection_update_lock = False
        plugin.synchronize_selection = True
        plugin._ignore_selection_update = False
        plugin._context_name = ""

        items = [
            _make_tree_item("/World/B"),
            _make_tree_item("/World/A"),
        ]

        with (
            mock.patch.object(_StageManagerInteractionPlugin, "_on_selection_changed", autospec=True) as super_sel,
            mock.patch.object(plugin, "_get_selection", return_value=["/World/A", "/World/B"]),
            mock.patch("omni.usd.get_context") as get_context,
        ):
            selection_mock = mock.MagicMock()
            context_mock = mock.MagicMock(get_selection=mock.MagicMock(return_value=selection_mock))
            get_context.return_value = context_mock

            # Act
            plugin._on_selection_changed(items)

            # Assert
            super_sel.assert_called_once()
            selection_mock.set_selected_prim_paths.assert_not_called()

    async def test_on_selection_changed_writes_back_when_selected_set_changes(self):
        # Arrange
        plugin = self._make_plugin()
        plugin._selection_update_lock = False
        plugin.synchronize_selection = True
        plugin._ignore_selection_update = False
        plugin._context_name = ""

        items = [
            _make_tree_item("/World/A"),
            _make_tree_item("/World/C"),
        ]

        with (
            mock.patch.object(_StageManagerInteractionPlugin, "_on_selection_changed", autospec=True) as super_sel,
            mock.patch.object(plugin, "_get_selection", return_value=["/World/A", "/World/B"]),
            mock.patch("omni.usd.get_context") as get_context,
        ):
            selection_mock = mock.MagicMock()
            context_mock = mock.MagicMock(get_selection=mock.MagicMock(return_value=selection_mock))
            get_context.return_value = context_mock

            # Act
            plugin._on_selection_changed(items)

            # Assert
            super_sel.assert_called_once()
            selection_mock.set_selected_prim_paths.assert_called_once_with(["/World/A", "/World/C"])

    async def test_property_resync_dirties_widgets_without_refreshing_context_items(self):
        # Arrange
        plugin = self._make_plugin()
        notice = self._make_notice(resynced_paths=[Sdf.Path("/World/Cube.doubleSided")])

        with mock.patch.object(plugin, "_queue_update") as queue_update:
            # Act
            plugin._on_usd_event_occurred(notice)

            # Assert
            queue_update.assert_called_once_with(update_context_items=False)

    async def test_gradient_primvar_change_dirties_widgets_without_refreshing_context_items(self):
        # Arrange
        plugin = self._make_plugin()
        notice = self._make_notice(
            changed_info_only_paths=[
                Sdf.Path("/World/Cube.primvars:color:times"),
                Sdf.Path("/World/Cube.primvars:color:values"),
            ]
        )

        with mock.patch.object(plugin, "_queue_update") as queue_update:
            # Act
            plugin._on_usd_event_occurred(notice)

            # Assert
            queue_update.assert_called_once_with(update_context_items=False)

    async def test_prim_resync_during_context_refresh_cancels_worker_and_queues_replacement(self):
        """Replace an in-flight stage read when a prim resync changes the tree's source data.

        Prim resyncs can change tree membership and grouping. When one arrives during context collection, the active
        worker must be cancelled and a full replacement refresh queued so its stale result cannot become the final
        published tree.
        """
        # Arrange
        plugin = self._make_plugin()
        plugin._context_refresh_cancel_event = threading.Event()
        stale_cancel_event = plugin._context_refresh_cancel_event
        plugin._update_queue = asyncio.Queue()
        plugin._update_items_task = mock.Mock()
        plugin._update_items_task.done.return_value = False
        notice = self._make_notice(resynced_paths=[Sdf.Path("/World/Cube")])

        # Act
        plugin._on_usd_event_occurred(notice)

        # Assert
        self.assertTrue(stale_cancel_event.is_set())
        self.assertIsNot(plugin._context_refresh_cancel_event, stale_cancel_event)
        self.assertFalse(plugin._context_refresh_cancel_event.is_set())
        self.assertTrue(plugin._update_queue.get_nowait())

    async def test_ignored_xform_change_during_context_refresh_does_not_queue_replacement(self):
        """Keep an in-flight refresh when an Xform edit cannot affect Stage Manager tree data.

        Transform edits change viewport placement but not Stage Manager membership, grouping, filtering, or labels.
        They must remain excluded from refresh scheduling even while context collection is active, avoiding repeated
        cancellation and full-tree reconstruction during interactive transforms.
        """
        # Arrange
        plugin = self._make_plugin()
        plugin.filtering_rules.ignore_xform_events = True
        plugin._context_refresh_cancel_event = threading.Event()
        notice = self._make_notice(changed_info_only_paths=[Sdf.Path("/World/Cube.xformOp:translate")])

        with mock.patch.object(plugin, "_queue_update") as queue_update:
            # Act
            plugin._on_usd_event_occurred(notice)

            # Assert
            self.assertFalse(plugin._context_refresh_cancel_event.is_set())
            queue_update.assert_not_called()

    async def test_prim_named_nickname_resync_refreshes_context_items(self):
        # Arrange
        plugin = self._make_plugin()
        notice = self._make_notice(resynced_paths=[Sdf.Path("/World/nickname")])

        with mock.patch.object(plugin, "_queue_update") as queue_update:
            # Act
            plugin._on_usd_event_occurred(notice)

            # Assert
            queue_update.assert_called_once_with(update_context_items=True)

    async def test_force_refresh_property_resync_matching_property_name_refreshes_context_items(self):
        # Arrange
        plugin = self._make_plugin()
        plugin.filtering_rules.force_refresh_rules = [_RefreshRule(start="remix_category:")]
        notice = self._make_notice(resynced_paths=[Sdf.Path("/World/Cube.remix_category:test")])

        with mock.patch.object(plugin, "_queue_update") as queue_update:
            # Act
            plugin._on_usd_event_occurred(notice)

            # Assert
            queue_update.assert_called_once_with(update_context_items=True)

    async def test_force_refresh_info_only_collection_property_refreshes_context_items(self):
        # Arrange
        plugin = self._make_plugin()
        plugin.filtering_rules.force_refresh_rules = [_RefreshRule(start="collection:", end=":includes", use_name=True)]
        notice = self._make_notice(changed_info_only_paths=[Sdf.Path("/CustomTags.collection:RenderTag:includes")])

        with mock.patch.object(plugin, "_queue_update") as queue_update:
            # Act
            plugin._on_usd_event_occurred(notice)

            # Assert
            queue_update.assert_called_once_with(update_context_items=True)

    async def test_force_refresh_collection_property_resync_refreshes_context_items(self):
        # Arrange
        plugin = self._make_plugin()
        plugin.filtering_rules.force_refresh_rules = [_RefreshRule(start="collection:", use_name=True)]
        notice = self._make_notice(resynced_paths=[Sdf.Path("/CustomTags.collection:RenderTag")])

        with mock.patch.object(plugin, "_queue_update") as queue_update:
            # Act
            plugin._on_usd_event_occurred(notice)

            # Assert
            queue_update.assert_called_once_with(update_context_items=True)

    async def test_force_refresh_visibility_property_resync_refreshes_context_items(self):
        # Arrange
        plugin = self._make_plugin()
        plugin.filtering_rules.force_refresh_rules = [_RefreshRule(start="visibility", use_name=True)]
        notice = self._make_notice(resynced_paths=[Sdf.Path("/World/Cube.visibility")])

        with mock.patch.object(plugin, "_queue_update") as queue_update:
            # Act
            plugin._on_usd_event_occurred(notice)

            # Assert
            queue_update.assert_called_once_with(update_context_items=True)

    async def test_force_refresh_property_resync_does_not_evaluate_prim_path_name(self):
        # Arrange
        plugin = self._make_plugin()
        plugin.filtering_rules.force_refresh_rules = [_RefreshRule(end="Cube", use_name=True)]
        notice = self._make_notice(resynced_paths=[Sdf.Path("/World/Cube.displayColor")])

        with mock.patch.object(plugin, "_queue_update") as queue_update:
            # Act
            plugin._on_usd_event_occurred(notice)

            # Assert
            queue_update.assert_called_once_with(update_context_items=False)

    async def test_property_only_paths_do_not_force_refresh_from_prim_path_name(self):
        # Arrange
        plugin = self._make_plugin()
        plugin.filtering_rules.force_refresh_rules = [_RefreshRule(end="Special", use_name=True)]
        notice = self._make_notice(
            changed_info_only_paths=[Sdf.Path("/World/Special.displayName")],
            resynced_paths=[Sdf.Path("/World/Special.doubleSided")],
        )

        with mock.patch.object(plugin, "_queue_update") as queue_update:
            # Act
            plugin._on_usd_event_occurred(notice)

            # Assert
            queue_update.assert_called_once_with(update_context_items=False)

    async def test_prim_info_only_path_refreshes_context_items(self):
        # Arrange
        plugin = self._make_plugin()
        notice = self._make_notice(changed_info_only_paths=[Sdf.Path("/World/Cube")])

        with mock.patch.object(plugin, "_queue_update") as queue_update:
            # Act
            plugin._on_usd_event_occurred(notice)

            # Assert
            queue_update.assert_called_once_with(update_context_items=True)

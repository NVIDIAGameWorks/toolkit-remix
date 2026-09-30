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

from unittest.mock import AsyncMock, Mock, PropertyMock

from omni.kit.test import AsyncTestCase

from ...selection_tree.model import ItemInstance, ItemPrim
from ...setup_ui import SetupUI

__all__ = ["TestSetupUI"]


class TestSetupUI(AsyncTestCase):
    """Verify ordered bulk selection without repeated full-row scans."""

    async def test_synchronize_selection_repeated_paths_preserves_rows_with_bounded_reads(self):
        """Keep distinct rows and raw instance prefixes without rescanning rows per selected path."""
        # Arrange
        prim_path = "/World/mesh_0000000000000001/Child"
        prim_rows = [Mock(spec=ItemPrim), Mock(spec=ItemPrim)]
        instance_rows = [Mock(spec=ItemInstance), Mock(spec=ItemInstance)]
        path_reads = []
        for row, path in zip(prim_rows + instance_rows, [prim_path, prim_path, "/World/inst_10", "/World/inst_1"]):
            path_reader = PropertyMock(return_value=path)
            type(row).path = path_reader
            path_reads.append(path_reader)
        widget = SetupUI.__new__(SetupUI)
        widget._context = Mock()
        widget._context.get_selection.return_value.get_selected_prim_paths.return_value = [
            prim_path,
            "/World/inst_10/Mesh",
        ] * 32
        widget._core = Mock()
        widget._core.get_corresponding_prototype_prims_from_path.return_value = []
        widget._tree_model = Mock()
        widget._tree_model.get_all_items_by_type.return_value = {ItemPrim: prim_rows, ItemInstance: instance_rows}
        widget._tree_view = None
        widget._previous_tree_selection = []
        widget._SetupUI__deferred_expand = AsyncMock(return_value=[])

        # Act
        await widget._on_deferred_tree_model_changed()

        # Assert
        widget._SetupUI__deferred_expand.assert_awaited_once_with(instance_rows + prim_rows)
        self.assertLessEqual(sum(reader.call_count for reader in path_reads[:2]), 2 * len(prim_rows))
        self.assertLessEqual(sum(reader.call_count for reader in path_reads[2:]), len(instance_rows))

    async def test_synchronize_selection_changed_during_expansion_does_not_publish(self):
        """Discard obsolete rows and restore refresh flags when selection changes during expansion."""
        # Arrange
        path = "/World/Mesh"
        row = Mock(spec=ItemPrim, path=path)
        widget = SetupUI.__new__(SetupUI)
        widget._context = Mock()
        selected_paths = widget._context.get_selection.return_value.get_selected_prim_paths
        selected_paths.return_value = [path]
        widget._core = Mock()
        widget._core.get_corresponding_prototype_prims_from_path.return_value = [path]
        widget._tree_model = Mock()
        widget._tree_model.get_all_items_by_type.return_value = {ItemPrim: [row]}
        previous_selection = [object()]
        widget._tree_view = Mock(selection=previous_selection)
        widget._previous_tree_selection = []
        widget._ignore_empty_tree_selection_during_refresh = True
        widget._on_tree_selection_changed = Mock()
        widget.scroll_to_item = AsyncMock()
        widget._SetupUI__refresh_delegate_gradients = Mock()

        async def expand(selection):
            selected_paths.return_value = ["/World/Other"]
            return selection

        widget._SetupUI__deferred_expand = AsyncMock(side_effect=expand)

        # Act
        await widget._on_deferred_tree_model_changed()

        # Assert
        widget._SetupUI__deferred_expand.assert_awaited_once_with([row])
        self.assertIs(widget._tree_view.selection, previous_selection)
        widget._on_tree_selection_changed.assert_not_called()
        widget.scroll_to_item.assert_not_awaited()
        self.assertFalse(widget._ignore_select_prototype)
        self.assertFalse(widget._ignore_empty_tree_selection_during_refresh)

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

__all__ = ["TestLightClipboardMenuPlugin"]

from unittest.mock import MagicMock, patch

import omni.kit.test
from omni.flux.utils.common.menus import MenuItem as _MenuItem

from ... import action_light_clipboard
from ...action_light_clipboard import LightClipboardMenuPlugin


class _Core:
    """Record light clipboard validation and actions for one context."""

    copied = None
    pasted = None

    def __init__(self, context_name: str):
        self.context_name = context_name

    def can_copy_light(self, path: str) -> bool:
        """Allow the source path used by the test."""
        return path == "/RootNode/meshes/source/Light"

    def copy_light_to_clipboard(self, path: str) -> bool:
        """Record the copied path and context."""
        type(self).copied = (self.context_name, path)
        return True

    def can_paste_light_from_clipboard(self, path: str) -> bool:
        """Allow the target path used by the test."""
        return path == "/RootNode/meshes/target"

    def paste_light_from_clipboard(self, path: str) -> str:
        """Record the pasted path and context."""
        type(self).pasted = (self.context_name, path)
        return f"{path}/Light"


class TestLightClipboardMenuPlugin(omni.kit.test.AsyncTestCase):
    """Test Stage Manager light clipboard menu behavior."""

    async def setUp(self):
        """Clear action state before each test."""
        _Core.copied = None
        _Core.pasted = None
        LightClipboardMenuPlugin._cores.clear()

    @staticmethod
    def _payload(path: str) -> dict:
        """Build a valid Stage Manager right-click payload."""
        prim = MagicMock()
        prim.IsValid.return_value = True
        prim.GetPath.return_value = path
        prim.GetTypeName.return_value = "Xform"
        prim.GetAppliedSchemas.return_value = []
        return {"context_name": "test", "right_clicked_item": MagicMock(data=prim)}

    async def test_get_menu_items_returns_copy_and_paste_actions(self):
        """The plugin registers both clipboard actions followed by a separator."""
        # Arrange
        expected_names = ["Copy Light", "Paste Light", _MenuItem.DYNAMIC_SPLITTER.value]

        # Act
        menu_items = LightClipboardMenuPlugin._get_menu_items()

        # Assert
        self.assertEqual([item[0]["name"] for item in menu_items], expected_names)

    async def test_actions_with_same_context_reuse_core(self):
        """Menu validation and clicks share one core for their USD context."""
        # Arrange
        payload = self._payload("/RootNode/meshes/source/Light")
        core = _Core("test")

        # Act
        with patch.object(action_light_clipboard, "_AssetReplacementsCore", return_value=core) as core_class:
            LightClipboardMenuPlugin._can_copy_light(payload)
            LightClipboardMenuPlugin._copy_light(payload)

        # Assert
        core_class.assert_called_once_with("test")

    async def test_unregister_menu_destroys_cached_cores(self):
        """Unregistering the menu releases its context-bound cores."""
        # Arrange
        core = MagicMock()
        LightClipboardMenuPlugin._cores = {"test": core}

        # Act
        LightClipboardMenuPlugin.unregister_menu()

        # Assert
        core.destroy.assert_called_once_with()
        self.assertEqual(LightClipboardMenuPlugin._cores, {})

    async def test_can_copy_light_with_added_light_returns_true(self):
        """Copy Light is enabled for an added light."""
        # Arrange
        payload = self._payload("/RootNode/meshes/source/Light")

        # Act
        with patch.object(action_light_clipboard, "_AssetReplacementsCore", _Core):
            enabled = LightClipboardMenuPlugin._can_copy_light(payload)

        # Assert
        self.assertTrue(enabled)

    async def test_copy_light_with_added_light_copies_exact_right_clicked_path(self):
        """Copy Light forwards the exact right-clicked path to the shared core."""
        # Arrange
        payload = self._payload("/RootNode/meshes/source/Light")

        # Act
        with patch.object(action_light_clipboard, "_AssetReplacementsCore", _Core):
            LightClipboardMenuPlugin._copy_light(payload)

        # Assert
        self.assertEqual(_Core.copied, ("test", "/RootNode/meshes/source/Light"))

    async def test_can_paste_light_with_valid_mesh_returns_true(self):
        """Paste Light is enabled when the shared core accepts the right-clicked mesh."""
        # Arrange
        payload = self._payload("/RootNode/meshes/target")

        # Act
        with patch.object(action_light_clipboard, "_AssetReplacementsCore", _Core):
            enabled = LightClipboardMenuPlugin._can_paste_light(payload)

        # Assert
        self.assertTrue(enabled)

    async def test_paste_light_with_valid_mesh_pastes_to_exact_right_clicked_path(self):
        """Paste Light forwards the exact right-clicked mesh path to the shared core."""
        # Arrange
        payload = self._payload("/RootNode/meshes/target")

        # Act
        with patch.object(action_light_clipboard, "_AssetReplacementsCore", _Core):
            LightClipboardMenuPlugin._paste_light(payload)

        # Assert
        self.assertEqual(_Core.pasted, ("test", "/RootNode/meshes/target"))

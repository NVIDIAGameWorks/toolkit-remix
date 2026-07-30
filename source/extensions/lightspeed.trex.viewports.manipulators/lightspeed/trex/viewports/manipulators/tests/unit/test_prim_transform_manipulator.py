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

from unittest.mock import patch

from lightspeed.trex.contexts.setup import Contexts as _TrexContexts
from lightspeed.trex.viewports.manipulators.custom_manipulator.prim_transform_manipulator import (
    PrimTransformManipulator,
)
from omni.kit.manipulator.prim.core.prim_transform_manipulator import (
    PrimTransformManipulator as _BasePrimTransformManipulator,
)
from omni.kit.test import AsyncTestCase


class _Core:
    def __init__(self, transformable):
        self.transformable = transformable
        self.filtered_selection = None

    def filter_transformable_prims(self, selection):
        self.filtered_selection = selection
        return self.transformable

    def destroy(self):
        pass


class _Model:
    def __init__(self):
        self.redirects = []
        self.selections = []

    def set_path_redirect(self, paths):
        self.redirects.append(paths)

    def on_selection_changed(self, selection):
        self.selections.append(selection)


class TestPrimTransformManipulator(AsyncTestCase):
    def _manipulator(self, context_name, transformable):
        manipulator = PrimTransformManipulator.__new__(PrimTransformManipulator)
        manipulator._PrimTransformManipulator__context_name = context_name
        manipulator._core = _Core(transformable)
        manipulator._model = _Model()
        manipulator.destroy = lambda: None
        return manipulator

    async def test_stagecraft_invalid_selection_does_not_rebuild_base_model(self):
        # Arrange
        manipulator = self._manipulator(_TrexContexts.STAGE_CRAFT.value, [])
        selection = ["/RootNode/meshes/mesh_1D5BEF743BE54A65/mesh"]

        with patch.object(_BasePrimTransformManipulator, "on_selection_changed", return_value=True) as mock_base:
            # Act
            result = manipulator.on_selection_changed(None, selection)

        # Assert
        self.assertFalse(result)
        mock_base.assert_not_called()
        self.assertEqual([[]], manipulator._model.redirects)
        self.assertEqual([[]], manipulator._model.selections)

    async def test_stagecraft_valid_selection_keeps_base_handler_for_pivot_behavior(self):
        # Arrange
        transformable = ["/RootNode/lights/light_1"]
        manipulator = self._manipulator(_TrexContexts.STAGE_CRAFT.value, transformable)
        selection = ["/RootNode/lights/light_1"]

        with patch.object(_BasePrimTransformManipulator, "on_selection_changed", return_value=True) as mock_base:
            # Act
            result = manipulator.on_selection_changed(None, selection)

        # Assert
        self.assertTrue(result)
        mock_base.assert_called_once_with(None, selection)
        self.assertEqual([transformable], manipulator._model.redirects)
        self.assertEqual([], manipulator._model.selections)

    async def test_non_stagecraft_delegates_to_base_handler(self):
        # Arrange
        manipulator = self._manipulator("other_context", [])
        selection = ["/World/Mesh"]

        with patch.object(_BasePrimTransformManipulator, "on_selection_changed", return_value=True) as mock_base:
            # Act
            result = manipulator.on_selection_changed(None, selection)

        # Assert
        self.assertTrue(result)
        mock_base.assert_called_once_with(None, selection)
        self.assertIsNone(manipulator._core.filtered_selection)
        self.assertEqual([], manipulator._model.redirects)

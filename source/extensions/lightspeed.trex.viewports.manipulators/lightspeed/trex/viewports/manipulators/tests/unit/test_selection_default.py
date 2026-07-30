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

from unittest.mock import Mock, patch

from omni.kit.manipulator.selection import SelectionMode
from omni.kit.test import AsyncTestCase

from lightspeed.trex.viewports.manipulators.global_selection import GlobalSelection
from lightspeed.trex.viewports.manipulators.selection_default import SelectionDefault

from .test_global_selection import _ViewportApi


class _SelectionViewportApi(_ViewportApi):
    resolution = (100, 100)

    def map_ndc_to_texture_pixel(self, ndc_pos):
        return (int(ndc_pos[0] * 100), int(ndc_pos[1] * 100)), self


class _SelectionModel:
    def __init__(self, ndc_rect=None, mode=None):
        self.ndc_rect = ndc_rect or []
        self.mode = mode or []

    def get_item(self, name):
        return name

    def get_as_floats(self, name):
        if name == "ndc_rect":
            return self.ndc_rect
        return []

    def get_as_ints(self, name):
        if name == "mode":
            return self.mode
        return []


class _SelectionManipulator:
    def __init__(self):
        self.model = Mock()
        self.model.subscribe_item_changed_fn.return_value = object()
        self.visible = True


class TestSelectionDefault(AsyncTestCase):
    async def setUp(self):
        self._selection_manipulator_patcher = patch(
            "lightspeed.trex.viewports.manipulators.selection_default.SelectionManipulator",
            _SelectionManipulator,
        )
        self._selection_manipulator_patcher.start()

    async def tearDown(self):
        self._selection_manipulator_patcher.stop()

    @staticmethod
    def _selection_rect_model():
        return _SelectionModel([0.1, 0.9, 0.1, 0.9], [SelectionMode.REPLACE])

    async def test_empty_release_without_selection_state_preserves_existing_selection(self):
        # Arrange
        viewport_api = _SelectionViewportApi()
        viewport_api.usd_context.selection.selected_paths = ["/World/Light"]
        selection = SelectionDefault(viewport_api)

        # Act
        selection._model_changed(_SelectionModel(), "ndc_rect")

        # Assert
        self.assertEqual(["/World/Light"], viewport_api.usd_context.selection.selected_paths)
        selection.destroy()

    async def test_empty_release_after_outside_viewport_selection_clears_existing_selection(self):
        # Arrange
        viewport_api = _SelectionViewportApi()
        viewport_api.usd_context.selection.selected_paths = ["/World/Light"]
        selection = SelectionDefault(viewport_api)

        # Act
        selection._model_changed(_SelectionModel([2.0, 2.0, 3.0, 3.0], [SelectionMode.REPLACE]), "ndc_rect")
        selection._model_changed(_SelectionModel(), "ndc_rect")

        # Assert
        self.assertEqual([], viewport_api.usd_context.selection.selected_paths)
        selection.destroy()

    async def test_release_after_manipulator_changes_selection_does_not_request_prim_pick(self):
        # Arrange
        viewport_api = _SelectionViewportApi()
        viewport_api.usd_context.selection.selected_paths = ["/World/Mesh"]
        selection = SelectionDefault(viewport_api)
        global_selection = GlobalSelection()

        with patch(
            "lightspeed.trex.viewports.manipulators.selection_default.GlobalSelection.get_instance",
            return_value=global_selection,
        ):
            selection._model_changed(self._selection_rect_model(), "ndc_rect")
            viewport_api.usd_context.selection.selected_paths = ["/World/Light"]
            with patch.object(global_selection, "add_prim_selection") as mock_add_prim_selection:
                # Act
                selection._model_changed(_SelectionModel(), "ndc_rect")

        # Assert
        mock_add_prim_selection.assert_not_called()
        self.assertEqual(["/World/Light"], viewport_api.usd_context.selection.selected_paths)
        selection.destroy()

    async def test_release_after_same_light_manipulator_click_does_not_request_prim_pick(self):
        # Arrange
        viewport_api = _SelectionViewportApi()
        viewport_api.usd_context.selection.selected_paths = ["/World/Light"]
        selection = SelectionDefault(viewport_api)
        global_selection = GlobalSelection()

        with patch(
            "lightspeed.trex.viewports.manipulators.selection_default.GlobalSelection.get_instance",
            return_value=global_selection,
        ):
            selection._model_changed(self._selection_rect_model(), "ndc_rect")
            global_selection.add_manipulator_selection(viewport_api, (10, 90), 100.0, "/World/Light")
            with patch.object(global_selection, "add_prim_selection") as mock_add_prim_selection:
                # Act
                selection._model_changed(_SelectionModel(), "ndc_rect")

        # Assert
        mock_add_prim_selection.assert_not_called()
        self.assertEqual(["/World/Light"], viewport_api.usd_context.selection.selected_paths)
        selection.destroy()

    async def test_late_selection_start_after_light_manipulator_click_does_not_request_prim_pick(self):
        # Arrange
        viewport_api = _SelectionViewportApi()
        viewport_api.usd_context.selection.selected_paths = ["/World/Light"]
        selection = SelectionDefault(viewport_api)
        global_selection = GlobalSelection()

        with patch(
            "lightspeed.trex.viewports.manipulators.selection_default.GlobalSelection.get_instance",
            return_value=global_selection,
        ):
            global_selection.add_manipulator_selection(viewport_api, (10, 90), 100.0, "/World/Light")
            selection._model_changed(self._selection_rect_model(), "ndc_rect")
            with patch.object(global_selection, "add_prim_selection") as mock_add_prim_selection:
                # Act
                selection._model_changed(_SelectionModel(), "ndc_rect")

        # Assert
        mock_add_prim_selection.assert_not_called()
        self.assertEqual(["/World/Light"], viewport_api.usd_context.selection.selected_paths)
        selection.destroy()

    async def test_duplicate_release_after_light_manipulator_click_does_not_request_prim_pick(self):
        # Arrange
        viewport_api = _SelectionViewportApi()
        viewport_api.usd_context.selection.selected_paths = ["/World/Light"]
        selection = SelectionDefault(viewport_api)
        global_selection = GlobalSelection()

        with patch(
            "lightspeed.trex.viewports.manipulators.selection_default.GlobalSelection.get_instance",
            return_value=global_selection,
        ):
            global_selection.add_manipulator_selection(viewport_api, (10, 90), 100.0, "/World/Light")
            with patch.object(global_selection, "add_prim_selection") as mock_add_prim_selection:
                # Act
                selection._model_changed(self._selection_rect_model(), "ndc_rect")
                selection._model_changed(_SelectionModel(), "ndc_rect")
                selection._model_changed(self._selection_rect_model(), "ndc_rect")
                selection._model_changed(_SelectionModel(), "ndc_rect")

        # Assert
        mock_add_prim_selection.assert_not_called()
        self.assertEqual(["/World/Light"], viewport_api.usd_context.selection.selected_paths)
        selection.destroy()

    async def test_different_click_after_light_manipulator_click_can_request_prim_pick(self):
        # Arrange
        viewport_api = _SelectionViewportApi()
        viewport_api.usd_context.selection.selected_paths = ["/World/Light"]
        selection = SelectionDefault(viewport_api)
        global_selection = GlobalSelection()

        with patch(
            "lightspeed.trex.viewports.manipulators.selection_default.GlobalSelection.get_instance",
            return_value=global_selection,
        ):
            global_selection.add_manipulator_selection(viewport_api, (10, 90), 100.0, "/World/Light")
            selection._model_changed(self._selection_rect_model(), "ndc_rect")
            selection._model_changed(_SelectionModel(), "ndc_rect")
            with patch.object(global_selection, "add_prim_selection") as mock_add_prim_selection:
                # Act
                selection._model_changed(_SelectionModel([0.2, 0.8, 0.2, 0.8], [SelectionMode.REPLACE]), "ndc_rect")
                selection._model_changed(_SelectionModel(), "ndc_rect")

        # Assert
        mock_add_prim_selection.assert_called_once()
        selection.destroy()

    async def test_release_without_intervening_selection_change_requests_prim_pick(self):
        # Arrange
        viewport_api = _SelectionViewportApi()
        viewport_api.usd_context.selection.selected_paths = ["/World/Light"]
        selection = SelectionDefault(viewport_api)
        global_selection = GlobalSelection()

        with patch(
            "lightspeed.trex.viewports.manipulators.selection_default.GlobalSelection.get_instance",
            return_value=global_selection,
        ):
            selection._model_changed(self._selection_rect_model(), "ndc_rect")
            with patch.object(global_selection, "add_prim_selection") as mock_add_prim_selection:
                # Act
                selection._model_changed(_SelectionModel(), "ndc_rect")

        # Assert
        mock_add_prim_selection.assert_called_once()
        selection.destroy()

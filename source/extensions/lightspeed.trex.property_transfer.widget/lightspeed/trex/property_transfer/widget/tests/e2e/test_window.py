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

from unittest import mock

import omni.kit.test
import omni.usd
from carb.input import KeyboardInput
from lightspeed.layer_manager.core import LayerManagerCore, LayerType
from lightspeed.trex.property_transfer.widget import PropertyTransferWindow
from omni import ui
from omni.flux.utils.widget.resources import get_test_data
from omni.kit import ui_test
from omni.kit.usd.layers import LayerUtils
from pxr import Sdf


class TestPropertyTransferWindow(omni.kit.test.AsyncTestCase):
    _WINDOW_TITLE = "Transfer Modification to Layer"
    _DEFINITION_WINDOW_TITLE = "Transfer Definition to Layer"
    _TRANSFER_WINDOW_TITLES = (_WINDOW_TITLE, _DEFINITION_WINDOW_TITLE)

    async def setUp(self):
        await omni.usd.get_context().open_stage_async(get_test_data("usd/project_example/combined.usda"))
        self._stage = omni.usd.get_context().get_stage()
        self._layer_manager = LayerManagerCore()
        self._source_layer = self._layer_manager.get_layer_of_type(LayerType.replacement)
        self.assertIsNotNone(self._source_layer)
        self._target_layer = self._get_layer_relative_to_source("transfer_workflow_target.usda")
        self.assertIsNotNone(self._target_layer)
        self._locked_target_layer = self._get_layer_relative_to_source(
            "transfer_workflow_second_particle_overrides.usda"
        )
        self.assertIsNotNone(self._locked_target_layer)
        self._window = None

    async def tearDown(self):
        try:
            if self._window:
                self._window.destroy()
                self._window = None
        finally:
            for title in self._TRANSFER_WINDOW_TITLES:
                transfer_window = ui.Workspace.get_window(title)
                if transfer_window:
                    transfer_window.destroy()
            await ui_test.human_delay(human_delay_speed=4)
            if omni.usd.get_context().get_stage():
                await omni.usd.get_context().close_stage_async()

    def _get_layer_relative_to_source(self, layer_name: str) -> Sdf.Layer:
        layer = Sdf.Layer.FindRelativeToLayer(self._source_layer, layer_name)
        self.assertIsNotNone(layer)
        return layer

    def _get_source_property_spec(self, property_path: str):
        spec = self._source_layer.GetPropertyAtPath(Sdf.Path(property_path))
        self.assertIsNotNone(spec)
        return spec

    @staticmethod
    def _find_visible_widgets(selector: str):
        return [
            widget
            for widget in ui_test.find_all(selector)
            if widget.widget.visible and widget.widget.computed_width > 0 and widget.widget.computed_height > 0
        ]

    @classmethod
    def _find_visible_frame(cls, *, tooltip: str):
        frames = cls._find_visible_widgets(f"{TestPropertyTransferWindow._WINDOW_TITLE}//Frame/**/Frame[*]")
        for frame in frames:
            if frame.widget.tooltip == tooltip:
                return frame
        return None

    @classmethod
    def _find_visible_labels(cls, *, text: str):
        labels = cls._find_visible_widgets(f"{TestPropertyTransferWindow._WINDOW_TITLE}//Frame/**/Label[*]")
        return [label for label in labels if label.widget.text == text]

    @classmethod
    def _find_visible_label(cls, *, text: str):
        labels = cls._find_visible_labels(text=text)
        return labels[0] if labels else None

    @classmethod
    def _find_visible_layer_label(cls, *, layer_name: str):
        labels = cls._find_visible_widgets(f"{TestPropertyTransferWindow._WINDOW_TITLE}//Frame/**/Label[*]")
        for label in labels:
            if label.widget.text == layer_name or label.widget.text.endswith(layer_name):
                return label
        return None

    async def test_destroy_closes_modal_window(self):
        source_spec = self._get_source_property_spec(
            "/RootNode/meshes/mesh_FEE1DEADF00D0001/TransferWorkflowLight.inputs:intensity"
        )

        # Open the modal through the same public window path used by callers.
        self._window = PropertyTransferWindow("", [source_spec], display_name="Test Value")

        await ui_test.human_delay(human_delay_speed=8)

        self.assertIsNotNone(ui.Workspace.get_window(self._WINDOW_TITLE))

        # Destroy the modal and verify the workspace no longer owns the window.
        self._window.destroy()
        await ui_test.human_delay(human_delay_speed=8)

        self.assertIsNone(self._window._delegate)
        self.assertIsNone(self._window._tree)
        self.assertIsNone(ui.Workspace.get_window(self._WINDOW_TITLE))
        self._window = None

    async def test_layer_selection_controls_transfer_button_enabled_state(self):
        source_spec = self._get_source_property_spec(
            "/RootNode/meshes/mesh_FEE1DEADF00D0001/TransferWorkflowLight.inputs:intensity"
        )

        # Show the modal with one valid target and one invalid root row.
        self._window = PropertyTransferWindow("", [source_spec], display_name="Test Value")

        await ui_test.human_delay(human_delay_speed=8)
        transfer_button = ui_test.find(
            f"{self._WINDOW_TITLE}//Frame/**/Button[*].identifier=='property_transfer_confirm'"
        )
        root_label = self._find_visible_label(text="Root Layer")
        target_frame = self._find_visible_frame(tooltip=self._target_layer.identifier)

        self.assertIsNotNone(root_label)
        self.assertFalse(transfer_button.widget.enabled)

        # Clicking an invalid layer keeps the transfer action disabled.
        await root_label.click()
        await ui_test.human_delay(human_delay_speed=4)
        self.assertFalse(transfer_button.widget.enabled)

        # Clicking a valid replacement target enables the transfer action.
        await target_frame.click()
        await ui_test.human_delay(human_delay_speed=4)

        self.assertTrue(transfer_button.widget.enabled)

    async def test_invalid_layers_are_unavailable_transfer_targets(self):
        LayerUtils.set_layer_lock_status(self._stage.GetRootLayer(), self._locked_target_layer.identifier, True)
        source_spec = self._get_source_property_spec(
            "/RootNode/meshes/mesh_FEE1DEADF00D0001/TransferWorkflowLight.inputs:intensity"
        )

        # Render a real project layer tree that includes valid, root, capture, and locked rows.
        self._window = PropertyTransferWindow("", [source_spec], display_name="Test Value")

        await ui_test.human_delay(human_delay_speed=8)
        transfer_button = ui_test.find(
            f"{self._WINDOW_TITLE}//Frame/**/Button[*].identifier=='property_transfer_confirm'"
        )
        target_frame = self._find_visible_frame(tooltip=self._target_layer.identifier)
        root_label = self._find_visible_label(text="Root Layer")
        capture_label = self._find_visible_layer_label(layer_name="capture.usda")
        locked_label = self._find_visible_layer_label(layer_name="transfer_workflow_second_particle_overrides.usda")

        self.assertEqual([], self._find_visible_labels(text="Unavailable"))
        self.assertIsNotNone(root_label)
        self.assertIsNotNone(capture_label)
        self.assertIsNotNone(locked_label)

        # Invalid layers explain why they cannot be transfer targets.
        self.assertIn("Select the replacement layer or one of its sublayers.", root_label.widget.tooltip)
        self.assertIn("Select the replacement layer or one of its sublayers.", capture_label.widget.tooltip)
        self.assertIn("Transfer targets must be unlocked.", locked_label.widget.tooltip)

        # Valid target selection works before selecting an invalid row again.
        await target_frame.click()
        await ui_test.human_delay(human_delay_speed=4)
        self.assertTrue(transfer_button.widget.enabled)

        # Selecting the root layer clears the target and disables transfer.
        await root_label.click()
        await ui_test.human_delay(human_delay_speed=4)

        self.assertFalse(transfer_button.widget.enabled)
        self.assertEqual(self._window._selected_target_layer_identifier, "")

    async def test_transfer_button_rechecks_valid_targets_after_layer_state_changes(self):
        source_spec = self._get_source_property_spec(
            "/RootNode/meshes/mesh_FEE1DEADF00D0001/TransferWorkflowLight.inputs:intensity"
        )

        # Start with a selectable target so the button can become enabled.
        self._window = PropertyTransferWindow("", [source_spec], display_name="Test Value")

        await ui_test.human_delay(human_delay_speed=8)
        transfer_button = ui_test.find(
            f"{self._WINDOW_TITLE}//Frame/**/Button[*].identifier=='property_transfer_confirm'"
        )
        root_label = self._find_visible_label(text="Root Layer")
        target_frame = self._find_visible_frame(tooltip=self._target_layer.identifier)

        self.assertIsNotNone(root_label)
        await target_frame.click()
        await ui_test.human_delay(human_delay_speed=4)
        self.assertTrue(transfer_button.widget.enabled)

        # Lock the target layer through the real layer-lock data and verify stale selection is rejected.
        LayerUtils.set_layer_lock_status(self._stage.GetRootLayer(), self._target_layer.identifier, True)
        await root_label.click()
        await ui_test.human_delay(human_delay_speed=4)
        await target_frame.click()
        await ui_test.human_delay(human_delay_speed=4)

        self.assertFalse(transfer_button.widget.enabled)

    async def test_transfer_failure_keeps_modal_open_and_undoes_partial_success(self):
        source_spec = self._get_source_property_spec(
            "/RootNode/meshes/mesh_FEE1DEADF00D0001/TransferWorkflowLight.inputs:intensity"
        )
        second_source_spec = self._get_source_property_spec(
            "/RootNode/meshes/mesh_FEE1DEADF00D0001/mesh/TransferWorkflowLogicGraph/MeshProximity.inputs:target"
        )

        transfer_results = iter([(True, None)])

        def _execute_transfer_command(*_args, **_kwargs):
            return next(transfer_results, (False, None))

        with (
            mock.patch(
                "lightspeed.trex.property_transfer.widget.window.omni.kit.commands.execute",
                side_effect=_execute_transfer_command,
            ) as execute_mock,
            mock.patch("lightspeed.trex.property_transfer.widget.window.omni.kit.undo.undo") as undo_mock,
        ):
            self._window = PropertyTransferWindow("", [source_spec, second_source_spec], display_name="Test Value")
            await ui_test.human_delay(human_delay_speed=8)

            target_frame = self._find_visible_frame(tooltip=self._target_layer.identifier)
            transfer_button = ui_test.find(
                f"{self._WINDOW_TITLE}//Frame/**/Button[*].identifier=='property_transfer_confirm'"
            )

            # Select a valid target, then trigger a grouped transfer where the second command fails.
            await target_frame.click()
            await ui_test.human_delay(human_delay_speed=4)
            await transfer_button.click()
            await ui_test.human_delay(human_delay_speed=4)

        # The modal stays open and the partial command group is undone.
        self.assertTrue(self._window._window.visible)
        self.assertGreaterEqual(execute_mock.call_count, 2)
        undo_mock.assert_called_once_with()

    async def test_enter_confirms_transfer_after_target_selection(self):
        source_spec = self._get_source_property_spec(
            "/RootNode/meshes/mesh_FEE1DEADF00D0001/TransferWorkflowLight.inputs:intensity"
        )

        with mock.patch(
            "lightspeed.trex.property_transfer.widget.window.omni.kit.commands.execute",
            return_value=(True, None),
        ) as execute_mock:
            self._window = PropertyTransferWindow("", [source_spec], display_name="Test Value")
            await ui_test.human_delay(human_delay_speed=8)

            # Select a valid target layer, then confirm with the keyboard like a user.
            target_frame = self._find_visible_frame(tooltip=self._target_layer.identifier)
            await target_frame.click()
            await ui_test.human_delay(human_delay_speed=4)
            await ui_test.emulate_keyboard_press(KeyboardInput.ENTER)
            await ui_test.human_delay(human_delay_speed=4)

        self.assertFalse(self._window._window.visible)
        execute_mock.assert_called_once()

    async def test_double_clicking_target_layer_confirms_transfer(self):
        source_spec = self._get_source_property_spec(
            "/RootNode/meshes/mesh_FEE1DEADF00D0001/TransferWorkflowLight.inputs:intensity"
        )

        with mock.patch(
            "lightspeed.trex.property_transfer.widget.window.omni.kit.commands.execute",
            return_value=(True, None),
        ) as execute_mock:
            self._window = PropertyTransferWindow("", [source_spec], display_name="Test Value")
            await ui_test.human_delay(human_delay_speed=8)

            # Double-click a valid target layer to select it and transfer in one user action.
            target_frame = self._find_visible_frame(tooltip=self._target_layer.identifier)
            await target_frame.double_click()
            await ui_test.human_delay(human_delay_speed=4)

        self.assertFalse(self._window._window.visible)
        execute_mock.assert_called_once()

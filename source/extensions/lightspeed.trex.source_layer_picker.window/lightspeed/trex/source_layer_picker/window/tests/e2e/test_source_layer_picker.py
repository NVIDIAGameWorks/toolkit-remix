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

from pathlib import Path
from unittest.mock import patch

import omni.kit.test
import omni.usd
from lightspeed.layer_manager.core import LayerManagerCore
from omni.flux.utils.common.omni_url import OmniUrl
from omni.flux.utils.common import EventSubscription
from omni.flux.utils.tests.context_managers import open_test_project
from omni.kit import ui_test
from omni.kit.usd.layers import LayerUtils as _LayerUtils

from lightspeed.trex.source_layer_picker.window import SearchableLayerModel
from lightspeed.trex.source_layer_picker.window import SourceLayerPicker
from lightspeed.trex.source_layer_picker.window import SourceLayerPickerDelegate

__all__ = ["TestSourceLayerPickerE2E"]

_CONTEXT_NAME = "lightspeed.layer_manager.core"
_TEST_PROJECT = "usd/full_project/full_project.usda"
_LAYER_MODEL_GET_LAYERS_PATCH = "omni.kit.usd.layers.get_layers"


class _NoopLayerEventStream:
    def create_subscription_to_pop(self, *_args, **_kwargs):
        return object()


class _NoopLayersState:
    def is_layer_locked(self, _identifier: str) -> bool:
        return False

    def is_layer_globally_muted(self, _identifier: str) -> bool:
        return False

    def is_layer_savable(self, _identifier: str) -> bool:
        return True


class _NoopLayers:
    def get_event_stream(self):
        return _NoopLayerEventStream()

    def get_layers_state(self):
        return _NoopLayersState()


def _layer_name(identifier: str) -> str:
    return Path(OmniUrl(identifier).path).name


class TestSourceLayerPickerE2E(omni.kit.test.AsyncTestCase):
    """E2E coverage for SourceLayerPicker against the centralized full-project fixture."""

    async def _wait_for_picker(self, picker: SourceLayerPicker, update_count: int = 20) -> None:
        for _ in range(update_count):
            await ui_test.wait_n_updates(1)
            if picker.is_ready and self._find_layer_label("mod.usda") is not None:
                return
        self.fail("SourceLayerPicker did not build its real layer tree")

    async def _open_picker(
        self,
        selected_ids: set[str] | None = None,
    ) -> tuple[SourceLayerPicker, LayerManagerCore, list[set[str] | None], EventSubscription]:
        layer_manager = LayerManagerCore(_CONTEXT_NAME)
        applied_selections: list[set[str] | None] = []
        selected_state = {"ids": None if selected_ids is None else set(selected_ids)}

        def _record_selected_ids(ids: set[str] | None) -> None:
            applied_selections.append(None if ids is None else set(ids))
            selected_state["ids"] = None if ids is None else set(ids)

        picker = SourceLayerPicker(
            context_name=_CONTEXT_NAME,
            mod_layer_ids=frozenset(layer.identifier for layer in layer_manager.get_replacement_layers()),
            selected_ids=None if selected_state["ids"] is None else set(selected_state["ids"]),
        )
        selected_ids_applied_sub = picker.subscribe_selected_ids_applied(_record_selected_ids)
        with patch(_LAYER_MODEL_GET_LAYERS_PATCH, return_value=_NoopLayers()):
            picker.show()
            await self._wait_for_picker(picker)
        return picker, layer_manager, applied_selections, selected_ids_applied_sub

    @staticmethod
    def _project_layer_names(context_name: str) -> set[str]:
        stage = omni.usd.get_context(context_name).get_stage()
        identifiers = [stage.GetRootLayer().identifier]
        identifiers.extend(
            _LayerUtils.get_all_sublayers(stage, include_session_layers=False, include_anonymous_layers=False)
        )
        return {_layer_name(identifier) for identifier in identifiers}

    @staticmethod
    def _mod_layer_ids(layer_manager: LayerManagerCore) -> frozenset[str]:
        return frozenset(layer.identifier for layer in layer_manager.get_replacement_layers())

    @staticmethod
    def _visible_widgets(selector: str):
        return [widget for widget in ui_test.find_all(selector) if widget.widget.visible]

    def _visible_layer_names(self) -> set[str]:
        return {
            label.widget.text
            for label in self._visible_widgets(
                "Select Source Layers//Frame/**/Label[*].name=='PropertiesPaneSectionTreeItem'"
            )
        }

    def _find_layer_label(self, layer_name: str):
        labels = self._visible_widgets("Select Source Layers//Frame/**/Label[*].name=='PropertiesPaneSectionTreeItem'")
        return next((label for label in labels if label.widget.text == layer_name), None)

    def _layer_label(self, layer_name: str):
        label = self._find_layer_label(layer_name)
        self.assertIsNotNone(label)
        return label

    def _nearest_row_widget(self, selector: str, layer_name: str):
        label = self._layer_label(layer_name)
        widgets = self._visible_widgets(selector)
        self.assertGreater(len(widgets), 0)
        return min(widgets, key=lambda widget: abs(widget.position.y - label.position.y))

    async def test_show_with_full_project_should_build_real_layer_tree(self):
        async with open_test_project(_TEST_PROJECT, _CONTEXT_NAME, context_name=_CONTEXT_NAME):
            picker = None
            layer_manager = None
            try:
                picker, layer_manager, _applied_selections, _selected_ids_applied_sub = await self._open_picker()
                layer_names = self._project_layer_names(_CONTEXT_NAME)
                mod_layer_names = {_layer_name(identifier) for identifier in self._mod_layer_ids(layer_manager)}

                self.assertTrue(picker.visible)
                self.assertIn("full_project.usda", layer_names)
                self.assertIn("mod.usda", layer_names)
                self.assertIn("capture.usda", layer_names)
                self.assertIn("mod.usda", mod_layer_names)
                self.assertNotIn("capture.usda", mod_layer_names)
                visible_layer_names = self._visible_layer_names()
                self.assertIn("mod.usda", visible_layer_names)
                self.assertIn("capture.usda", visible_layer_names)
            finally:
                if picker is not None:
                    picker.destroy()
                if layer_manager is not None:
                    layer_manager.destroy()

    async def test_search_field_should_filter_visible_layer_tree(self):
        async with open_test_project(_TEST_PROJECT, _CONTEXT_NAME, context_name=_CONTEXT_NAME):
            picker = None
            layer_manager = None
            try:
                picker, layer_manager, _applied_selections, _selected_ids_applied_sub = await self._open_picker()
                picker.set_search(" capture ")
                await ui_test.wait_n_updates(2)

                visible_layer_names = self._visible_layer_names()
                self.assertIn("capture.usda", visible_layer_names)
                self.assertIn("mod_capture_baker.usda", visible_layer_names)
                self.assertIn("mod.usda", visible_layer_names)
                self.assertNotIn("sublayer_child_01.usda", visible_layer_names)
            finally:
                if picker is not None:
                    picker.destroy()
                if layer_manager is not None:
                    layer_manager.destroy()

    async def test_refresh_should_keep_layer_tree_visible(self):
        async with open_test_project(_TEST_PROJECT, _CONTEXT_NAME, context_name=_CONTEXT_NAME):
            picker = None
            layer_manager = None
            try:
                picker, layer_manager, _applied_selections, _selected_ids_applied_sub = await self._open_picker()
                visible_layer_names = self._visible_layer_names()

                picker.refresh()
                await ui_test.wait_n_updates(2)

                self.assertEqual(visible_layer_names, self._visible_layer_names())
            finally:
                if picker is not None:
                    picker.destroy()
                if layer_manager is not None:
                    layer_manager.destroy()

    async def test_searchable_layer_model_should_accept_tree_item_keyword(self):
        async with open_test_project(_TEST_PROJECT, _CONTEXT_NAME, context_name=_CONTEXT_NAME):
            model = None
            try:
                with patch(_LAYER_MODEL_GET_LAYERS_PATCH, return_value=_NoopLayers()):
                    model = SearchableLayerModel(context_name=_CONTEXT_NAME)
                    model.enable_listeners(True)
                    await ui_test.wait_n_updates(3)

                    root_items = model.get_item_children(item=None)
                    self.assertGreater(len(root_items), 0)
                    positional_children = model.get_item_children(root_items[0])

                    keyword_children = model.get_item_children(item=root_items[0])

                    self.assertEqual(positional_children, keyword_children)
            finally:
                if model is not None:
                    model.destroy()

    async def test_picker_changes_should_stage_until_select_button_applies(self):
        async with open_test_project(_TEST_PROJECT, _CONTEXT_NAME, context_name=_CONTEXT_NAME):
            picker = None
            layer_manager = None
            try:
                picker, layer_manager, applied_selections, _selected_ids_applied_sub = await self._open_picker()
                deselect_all_label = next(
                    (
                        label
                        for label in ui_test.find_all(
                            "Select Source Layers//Frame/**/Label[*].name=='FilterSectionAction'"
                        )
                        if label.widget.visible and label.widget.text == "Deselect All"
                    ),
                    None,
                )
                self.assertIsNotNone(deselect_all_label)
                await deselect_all_label.click()
                await ui_test.wait_n_updates(2)

                self.assertEqual([], applied_selections)
                self.assertEqual(set(), picker.draft_selected_ids)

                select_button = next(
                    (
                        button
                        for button in ui_test.find_all("Select Source Layers//Frame/**/Button[*]")
                        if button.widget.visible and button.widget.text == "Select"
                    ),
                    None,
                )
                self.assertIsNotNone(select_button)
                await select_button.click()
                await ui_test.wait_n_updates(2)

                self.assertEqual([set()], applied_selections)
                self.assertFalse(picker.visible)
            finally:
                if picker is not None:
                    picker.destroy()
                if layer_manager is not None:
                    layer_manager.destroy()

    async def test_non_mod_checkbox_column_should_not_change_draft_selection(self):
        async with open_test_project(_TEST_PROJECT, _CONTEXT_NAME, context_name=_CONTEXT_NAME):
            picker = None
            layer_manager = None
            try:
                picker, layer_manager, _applied_selections, _selected_ids_applied_sub = await self._open_picker()
                self.assertIsNone(picker.draft_selected_ids)

                checkbox_stack = self._nearest_row_widget(
                    "Select Source Layers//Frame/**/HStack[*].identifier=='source_layer_checkbox_stack'",
                    "capture.usda",
                )
                await checkbox_stack.click()
                await ui_test.wait_n_updates(2)

                self.assertIsNone(picker.draft_selected_ids)
            finally:
                if picker is not None:
                    picker.destroy()
                if layer_manager is not None:
                    layer_manager.destroy()

    async def test_destroy_should_destroy_delegate_and_model(self):
        async with open_test_project(_TEST_PROJECT, _CONTEXT_NAME, context_name=_CONTEXT_NAME):
            picker = None
            layer_manager = None
            try:
                with (
                    patch.object(SourceLayerPickerDelegate, "destroy") as delegate_destroy,
                    patch.object(SearchableLayerModel, "destroy") as model_destroy,
                ):
                    picker, layer_manager, _applied_selections, _selected_ids_applied_sub = await self._open_picker()

                    picker.destroy()

                    delegate_destroy.assert_called_once()
                    model_destroy.assert_called_once()
                    picker = None
            finally:
                if picker is not None:
                    picker.destroy()
                if layer_manager is not None:
                    layer_manager.destroy()

    async def test_delegate_destroy_should_drop_selected_ids_changed_subscribers(self):
        # Arrange
        delegate = SourceLayerPickerDelegate(selected_ids=None, mod_layer_ids=frozenset({"mod.usda"}))
        calls = []
        selected_ids_changed_sub = delegate.subscribe_selected_ids_changed(
            lambda selected_ids: calls.append(selected_ids)
        )

        # Act
        delegate.destroy()
        destroyed_selected_ids = delegate.selected_ids
        destroyed_mod_layer_ids = delegate.mod_layer_ids
        delegate._on_check_changed("mod.usda", False)

        # Assert
        self.assertIsNotNone(selected_ids_changed_sub)
        self.assertEqual([], calls)
        self.assertIsNone(destroyed_selected_ids)
        self.assertEqual(frozenset(), destroyed_mod_layer_ids)
        selected_ids_changed_sub = None

    async def test_branch_expansion_event_should_use_default_refresh_expansion(self):
        async with open_test_project(_TEST_PROJECT, _CONTEXT_NAME, context_name=_CONTEXT_NAME):
            picker = None
            layer_manager = None
            try:
                picker, layer_manager, _applied_selections, _selected_ids_applied_sub = await self._open_picker()
                child_layer_name = "sublayer_child_01.usda"
                self.assertIsNotNone(self._find_layer_label(child_layer_name))

                collapse_widget = self._nearest_row_widget(
                    "Select Source Layers//Frame/**/HStack[*].identifier=='expansion_stack'",
                    "mod.usda",
                )
                await collapse_widget.click()
                await ui_test.wait_n_updates(2)

                self.assertIsNone(self._find_layer_label(child_layer_name))

                picker.refresh()
                await ui_test.wait_n_updates(2)

                self.assertIsNotNone(self._find_layer_label(child_layer_name))
            finally:
                if picker is not None:
                    picker.destroy()
                if layer_manager is not None:
                    layer_manager.destroy()

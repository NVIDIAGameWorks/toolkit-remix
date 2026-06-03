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

import asyncio
import functools
from collections.abc import Callable

import carb
from omni import kit, ui, usd
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.widget.hover import hover_helper as _hover_helper
from omni.flux.utils.widget.scrolling_tree_view import ScrollingTreeWidget as _ScrollingTreeWidget
from omni.kit import undo
from omni.kit.widget.prompt import PromptButtonInfo, PromptManager

from .layer_tree.delegate import LayerDelegate as _LayerDelegate
from .layer_tree.item_model import ItemBase as _ItemBase
from .layer_tree.item_model import LayerItem as _LayerItem
from .layer_tree.model import LayerModel as _LayerModel
from .layer_tree.model import LayerTransferTarget as _LayerTransferTarget


class LayerTreeWidget:
    """
    A widget for displaying and managing USD layer hierarchies.

    This widget provides a tree view of USD layers with support for:
    - Expanding/collapsing layer hierarchies
    - Setting the authoring (edit target) layer
    - Creating, importing, and deleting sublayers
    - Saving, locking, and muting layers
    - Drag-and-drop reordering of sublayers
    - Resizable height via drag manipulator

    The widget uses `ScrollingTreeWidget` internally for scroll handling
    and alternating row backgrounds.

    Args:
        context_name: The USD context name to use (empty string for default)
        model: Optional custom LayerModel instance
        delegate: Optional custom LayerDelegate instance
        project_layer_transfer_fn: Optional callback for transferring a layer into another project layer.
        height: Initial height in pixels (default: 130)
        expansion_default: Default expansion state for items (default: False)
        hide_create_insert_buttons: Whether to hide create/import buttons (default: False)
    """

    _DEFAULT_TREE_FRAME_HEIGHT = 130
    _SIZE_PERCENT_MANIPULATOR_WIDTH = 50

    def __init__(
        self,
        context_name: str = "",
        model: _LayerModel | None = None,
        delegate: _LayerDelegate | None = None,
        project_layer_transfer_fn: Callable[[_LayerItem], None] | None = None,
        height: int | None = None,
        expansion_default: bool = False,
        hide_create_insert_buttons: bool = False,
    ):
        self._default_attr = {
            "_tree_expanded": None,
            "_model": None,
            "_delegate": None,
            "_height": None,
            "_expansion_default": None,
            "_hide_create_insert_buttons": None,
            "_project_layer_transfer_fn": None,
            "_manipulator_frame": None,
            "_loading_frame": None,
            "_manip_frame": None,
            "_slide_placer": None,
            "_slider_manip": None,
            "_layer_tree_widget": None,
            "_sub_on_refresh_started": None,
            "_sub_on_refresh_completed": None,
            "_sub_on_stage_opened": None,
            "_sub_on_edit_target_changed": None,
            "_sub_on_selection_changed": None,
            "_sub_on_item_changed": None,
            "_sub_on_context_menu_shown": None,
            "_sub_on_item_expanded": None,
            "_sub_on_set_authoring_layer": None,
            "_sub_on_item_removed": None,
            "_sub_on_item_saved": None,
            "_sub_on_item_locked": None,
            "_sub_on_item_visible_toggled": None,
            "_sub_on_item_exported": None,
            "_sub_on_item_renamed": None,
            "_sub_on_item_save_layer_as": None,
            "_sub_on_item_merge": None,
            "_sub_on_item_transfer": None,
            "_selection": None,
            "_ignore_selection_updates": None,
            "_refresh_task": None,
            "_create_button": None,
            "_import_button": None,
            "_select_edit_target_on_refresh": None,
            "_edit_target_identifier": None,
            "_visible": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._tree_expanded = {}

        self._model = _LayerModel(context_name) if model is None else model
        self._delegate = (
            _LayerDelegate(project_layer_transfer_enabled=project_layer_transfer_fn is not None)
            if delegate is None
            else delegate
        )
        self._delegate._project_layer_transfer_enabled = project_layer_transfer_fn is not None  # noqa: SLF001
        self._height = self._DEFAULT_TREE_FRAME_HEIGHT if height is None else height
        self._expansion_default = expansion_default
        self._hide_create_insert_buttons = hide_create_insert_buttons
        self._project_layer_transfer_fn = project_layer_transfer_fn

        # Model events
        self._sub_on_refresh_started = self._model.subscribe_refresh_started(
            functools.partial(self._on_model_refresh, True)
        )
        self._sub_on_refresh_completed = self._model.subscribe_refresh_completed(
            functools.partial(self._on_model_refresh, False)
        )
        self._sub_on_stage_opened = self._model.subscribe_stage_opened(self._on_stage_opened)
        self._sub_on_edit_target_changed = self._model.subscribe_edit_target_changed(self._on_edit_target_changed)
        self._sub_on_item_changed = self._model.subscribe_item_changed_fn(self._on_item_changed)

        # Delegate events
        self._sub_on_context_menu_shown = self._delegate.subscribe_context_menu_shown(self._sync_selection_from_tree)
        self._sub_on_item_expanded = self._delegate.subscribe_on_item_expanded(self._on_item_expanded)
        self._sub_on_set_authoring_layer = self._delegate.subscribe_on_set_authoring_layer(
            self._model.set_authoring_layer
        )
        self._sub_on_item_removed = self._delegate.subscribe_on_remove_clicked(self._delete_layers)
        self._sub_on_item_saved = self._delegate.subscribe_on_save_clicked(self._save_layers)
        self._sub_on_item_locked = self._delegate.subscribe_on_lock_clicked(self._set_lock_layers)
        self._sub_on_item_visible_toggled = self._delegate.subscribe_on_visible_clicked(self._set_mute_layers)
        self._sub_on_item_exported = self._delegate.subscribe_on_export_clicked(self._model.export_layer)
        self._sub_on_item_renamed = self._delegate.subscribe_on_rename_clicked(self._model.rename_layer)
        self._sub_on_item_save_layer_as = self._delegate.subscribe_on_save_as_clicked(self._model.save_layer_as)
        self._sub_on_item_merge = self._delegate.subscribe_on_merge_clicked(self._model.merge_layers)
        self._sub_on_item_transfer = self._delegate.subscribe_on_transfer_clicked(self._on_transfer_layer_changes)

        self._selection = set()
        self._ignore_selection_updates = False
        self._refresh_task = None
        self._select_edit_target_on_refresh = False
        self._edit_target_identifier = None
        self._visible = False

        self.__create_ui()
        self._update_button_state()

    def show(self, value: bool):
        """
        Let the widget know if it's visible or not. This will internally enable/disabled the USD listener to reduce the
        amount of resources used by the widget with it's not visible.
        """
        if value == self._visible:
            return
        self._visible = value
        if value:
            self._selection.clear()
            self._edit_target_identifier = None
            self._select_edit_target_on_refresh = True
        self._model.enable_listeners(value)

    def __create_ui(self):
        with ui.VStack():
            self._manipulator_frame = ui.Frame(visible=True)
            with self._manipulator_frame:
                size_manipulator_height = 4
                with ui.ZStack():
                    with ui.VStack():
                        with ui.ZStack(height=ui.Pixel(self._height)):
                            self._layer_tree_widget = _ScrollingTreeWidget(
                                self._model,
                                self._delegate,
                                alternating_rows=False,
                                row_height=self._delegate.row_height,
                                select_all_children=False,
                                frame_selection=False,
                                header_visible=False,
                                drop_between_items=True,
                                columns_resizable=False,
                                column_widths=[ui.Fraction(1)],
                                style_type_name_override="TreeView.Selection",
                                key_pressed_fn=self._on_delete_pressed,
                            )
                            self._sub_on_selection_changed = self._layer_tree_widget.subscribe_selection_changed(
                                self.on_selection_changed
                            )

                            self._loading_frame = ui.ZStack(content_clipping=True, visible=False)
                            with self._loading_frame:
                                ui.Rectangle(name="LoadingBackground", tooltip="Updating stage layer tree")
                                with ui.VStack(spacing=ui.Pixel(4)):
                                    ui.Spacer(width=0)
                                    ui.Image("", name="TimerStatic", height=24)
                                    ui.Label("Updating", name="LoadingLabel", height=0, alignment=ui.Alignment.CENTER)
                                    ui.Spacer(width=0)
                        ui.Line(name="PropertiesPaneSectionTitle")
                        if not self._hide_create_insert_buttons:
                            with ui.HStack():
                                ui.Spacer(width=ui.Pixel(28))
                                self._create_button = ui.Image(
                                    "",
                                    height=ui.Pixel(16),
                                    width=ui.Pixel(16),
                                    mouse_released_fn=lambda x, y, b, m: self._create_layer(b, True),
                                )
                                ui.Spacer(width=ui.Pixel(16))
                                self._import_button = ui.Image(
                                    "",
                                    height=ui.Pixel(16),
                                    width=ui.Pixel(16),
                                    mouse_released_fn=lambda x, y, b, m: self._create_layer(b, False),
                                )
                        ui.Spacer(height=ui.Pixel(8))
                        ui.Spacer(height=size_manipulator_height)

                    with ui.VStack():
                        ui.Spacer()
                        self._manip_frame = ui.Frame(height=size_manipulator_height)
                        with self._manip_frame:
                            self._slide_placer = ui.Placer(
                                draggable=True,
                                height=size_manipulator_height,
                                offset_x_changed_fn=self._on_slide_x_changed,
                                offset_y_changed_fn=functools.partial(
                                    self._on_slide_y_changed,
                                    size_manipulator_height,
                                ),
                            )
                            # Body
                            with self._slide_placer:
                                self._slider_manip = ui.Rectangle(
                                    width=ui.Percent(self._SIZE_PERCENT_MANIPULATOR_WIDTH),
                                    name="PropertiesPaneSectionTreeManipulator",
                                )
                                _hover_helper(self._slider_manip)

    def _on_slide_x_changed(self, x):
        size_manip = self._manip_frame.computed_width / 100 * self._SIZE_PERCENT_MANIPULATOR_WIDTH
        if x.value < 0:
            self._slide_placer.offset_x = 0
        elif x.value > self._manip_frame.computed_width - size_manip:
            self._slide_placer.offset_x = self._manip_frame.computed_width - size_manip

        item_path_scroll_frames = self._delegate.get_scroll_frames()
        if item_path_scroll_frames:
            max_frame_scroll_x = max(frame.scroll_x_max for frame in item_path_scroll_frames.values())
            value = (max_frame_scroll_x / (self._manip_frame.computed_width - size_manip)) * x
            for frame in item_path_scroll_frames.values():
                frame.scroll_x = value

    def _on_slide_y_changed(self, _, y):
        if y.value < 0:
            self._slide_placer.offset_y = 0
        self._layer_tree_widget.height = ui.Pixel(self._height + y.value)

    def _on_stage_opened(self):
        """Reset expansion state when a new stage is opened."""
        self._tree_expanded.clear()
        self._selection.clear()
        self._edit_target_identifier = None
        self._select_edit_target_on_refresh = True

    def _on_edit_target_changed(self):
        """Focus the new edit target on the next model refresh."""
        # The model item is rebuilt by the upcoming refresh, so read the current stage edit target directly.
        edit_target_layer = self._model.stage.GetEditTarget().GetLayer() if self._model.stage else None
        edit_target_identifier = edit_target_layer.identifier if edit_target_layer else None
        if not edit_target_identifier or edit_target_identifier == self._edit_target_identifier:
            return
        self._edit_target_identifier = edit_target_identifier
        self._selection.clear()
        self._select_edit_target_on_refresh = True

    @usd.handle_exception
    async def __refresh_async(self):
        # Refresh the expansion states
        await kit.app.get_app().next_update_async()
        selection = []
        scroll_to_selection = False

        items = self._model.get_item_children(recursive=True)
        edit_target = self._model.edit_target_layer
        edit_target_identifier = edit_target.data["layer"].identifier if edit_target else None

        if edit_target and self._select_edit_target_on_refresh:
            self._select_edit_target_on_refresh = False
            self._edit_target_identifier = edit_target_identifier
            self._selection = {edit_target_identifier}
            scroll_to_selection = True
            parent = edit_target.parent
            while parent:
                self._tree_expanded[parent.data["layer"].identifier] = True
                parent = parent.parent
        elif self._layer_tree_widget.selection:
            self._selection = {
                item.data["layer"].identifier
                for item in self._layer_tree_widget.selection
                if item.data.get("layer") is not None
            }

        for item in items:
            self._layer_tree_widget.set_expanded(
                item, self._tree_expanded.get(item.data["layer"].identifier, self._expansion_default), False
            )
            if item.data.get("layer") is not None and item.data["layer"].identifier in self._selection:
                selection.append(item)

        # Refresh the selection
        await kit.app.get_app().next_update_async()
        self._ignore_selection_updates = True
        self._layer_tree_widget.selection = selection
        self._delegate.on_item_selected(selection, items, self._model)
        self._ignore_selection_updates = False

        # Update the import & create button states
        self._update_button_state(selection)
        if scroll_to_selection:
            await self._layer_tree_widget.scroll_to_items(selection)

    def on_selection_changed(self, items: list[_ItemBase]):
        if self._ignore_selection_updates:
            return

        self._select_edit_target_on_refresh = False
        self._layer_tree_widget.on_selection_changed(items)
        self._sync_selection_from_tree()

    def _sync_selection_from_tree(self, *_args):
        # Context menu builds from delegate state, so sync from the authoritative TreeView selection first.
        selection = list(self._layer_tree_widget.selection)
        # Update the import & create button states
        self._update_button_state(selection)
        # Update the delegate gradients
        self._delegate.on_item_selected(selection, self._model.get_item_children(recursive=True), self._model)

        # Store the selection for the next refresh
        self._selection = {item.data["layer"].identifier for item in selection if item.data.get("layer") is not None}

    def _on_model_refresh(self, started: bool):
        if not self._loading_frame:
            return
        self._loading_frame.visible = started
        self._layer_tree_widget.visible = not started

        if not started:
            # Refresh the selection
            self._on_item_changed(None, None)

    def _on_item_changed(self, _model, _item):
        if self._refresh_task:
            self._refresh_task.cancel()
        self._refresh_task = asyncio.ensure_future(self.__refresh_async())

    def _on_delete_pressed(self, key, _, pressed):
        # Delete or Numpad Delete keys
        if key not in {int(carb.input.KeyboardInput.DEL), int(carb.input.KeyboardInput.NUMPAD_DEL)} or pressed:
            return

        self._delete_layers()

    def _on_item_expanded(self, expanded: bool):
        for item in self._layer_tree_widget.selection:
            if not item.can_have_children:
                continue
            self._tree_expanded[item.data["layer"].identifier] = expanded

    def _create_layer(self, button, create_or_import):
        if button != 0:
            return
        parent_layer = self._get_valid_layer_from_selection()
        if not parent_layer:
            return
        # Make sure the parent is expanded on refresh so the child layer is visible
        self._tree_expanded[parent_layer.data["layer"].identifier] = True
        self._model.create_layer(create_or_import, parent=parent_layer)

    def _on_transfer_layer_changes(self, layer: _LayerItem, transfer_target: _LayerTransferTarget) -> None:
        if not self._model.has_layer_changes(layer):
            return
        if transfer_target == _LayerTransferTarget.PROJECT_LAYER:
            if self._project_layer_transfer_fn:
                self._project_layer_transfer_fn(layer)
            return
        self._model.transfer_layer_overrides(layer, transfer_target)

    def _delete_layers(self):
        filtered_selection = [item for item in self._layer_tree_widget.selection if not item.data["exclude_remove"]]
        if not filtered_selection:
            return

        def execute_commands(*_):
            with self._model.disable_refresh():
                with undo.group():
                    for item in filtered_selection:
                        self._model.delete_layer(item)

        PromptManager.post_simple_prompt(
            "",
            f"Are you sure you want to delete the selected {'layers' if len(filtered_selection) > 1 else 'layer'}?",
            ok_button_info=PromptButtonInfo(
                "Delete All" if len(filtered_selection) > 1 else "Delete",
                functools.partial(execute_commands, filtered_selection),
            ),
            cancel_button_info=PromptButtonInfo("Cancel"),
            modal=True,
            no_title_bar=True,
        )

    def _save_layers(self):
        with self._model.disable_refresh():
            with undo.group():
                for item in self._layer_tree_widget.selection:
                    if not item.data["savable"]:
                        continue
                    self._model.save_layer(item)

    def _set_lock_layers(self, value):
        with self._model.disable_refresh():
            with undo.group():
                for item in self._layer_tree_widget.selection:
                    if item.data["exclude_lock"]:
                        continue
                    self._model.set_lock_layer(item, not value)

    def _set_mute_layers(self, value):
        with self._model.disable_refresh():
            with undo.group():
                for item in self._layer_tree_widget.selection:
                    if item.data["exclude_mute"] or not item.data["can_toggle_mute"]:
                        continue
                    self._model.set_mute_layer(item, value)

    def _update_button_state(self, items: list[_LayerItem] | None = None):
        if self._hide_create_insert_buttons:
            return

        layer = self._get_valid_layer_from_selection(items)

        self._create_button.enabled = bool(layer)
        self._create_button.name = "CreateLayer" if layer else "CreateLayerDisabled"
        self._create_button.tooltip = "Create a new layer" if layer else "Invalid parent layer selection"

        self._import_button.enabled = bool(layer)
        self._import_button.name = "ImportLayer" if layer else "ImportLayerDisabled"
        self._import_button.tooltip = "Import an existing layer" if layer else "Invalid parent layer selection"

    def _get_valid_layer_from_selection(self, items: list[_LayerItem] | None = None) -> _LayerItem | None:
        layer = None
        layers = items or self._layer_tree_widget.selection
        if layers:
            layer = layers[0]
            # Make sure we only add the sublayer to unlocked layers
            while layer and (self._model.is_layer_locked(layer) or layer.data["exclude_add_child"]):
                layer = layer.parent
        return layer

    def destroy(self):
        if self._refresh_task:
            self._refresh_task.cancel()
            self._refresh_task = None
        _reset_default_attrs(self)

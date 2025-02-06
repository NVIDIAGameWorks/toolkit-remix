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

__all__ = ["EditCustomTagsWindow"]

from enum import Enum
from functools import partial

import omni.kit.undo
from omni import ui, usd
from omni.flux.custom_tags.core import CustomTagsCore
from omni.flux.utils.common import reset_default_attrs
from omni.flux.utils.common.decorators import limit_recursion
from omni.kit.widget.prompt import PromptButtonInfo, PromptManager

from .selection_tree import TagsEditItem, TagsSelectionDelegate, TagsSelectionItem, TagsSelectionModel


class ActionType(Enum):
    CREATE = 0
    EDIT = 1
    DELETE = 2
    ADD = 3
    REMOVE = 4


class EditCustomTagsWindow:
    def __init__(self, selected_paths: list[str], context_name: str = ""):
        """
        A window that allows editing all the custom tags in a stage, as well as assigning and unassigning from given
        prims.

        The actions taken before applying will all be queued up and executed at the same time when the apply button is
        clicked to avoid having to refresh the tree in the background while the window is opened.
        """
        self._default_attrs = {
            "_selected_paths": None,
            "_action_queue": None,
            "_window": None,
            "_edit_button": None,
            "_delete_button": None,
            "_stage": None,
            "_core": None,
            "_available_tags_model": None,
            "_assigned_tags_model": None,
            "_tags_delegate": None,
            "_on_tag_assigned_sub": None,
            "_on_tag_unassigned_sub": None,
            "_on_available_tag_edited_sub": None,
            "_on_available_tag_double_clicked": None,
            "_on_assigned_tag_edited_sub": None,
            "_on_assigned_tag_double_clicked": None,
        }
        for attr, value in self._default_attrs.items():
            setattr(self, attr, value)

        self._selected_paths = selected_paths

        self._action_queue = []

        self._window = None
        self._edit_button = None
        self._delete_button = None

        self._stage = usd.get_context(context_name).get_stage()
        self._core = CustomTagsCore(context_name=context_name)

        self._available_tags_model = TagsSelectionModel(display_assigned_tags=False)
        self._available_tags_delegate = TagsSelectionDelegate()
        self._assigned_tags_model = TagsSelectionModel(display_assigned_tags=True)
        self._assigned_tags_delegate = TagsSelectionDelegate()

        self._on_tag_unassigned_sub = self._available_tags_model.subscribe_items_dropped(self._on_tags_unassigned)
        self._on_tag_assigned_sub = self._assigned_tags_model.subscribe_items_dropped(self._on_tags_assigned)

        self._on_available_tag_edited_sub = self._available_tags_delegate.subscribe_item_edited(
            partial(self._on_item_edited, True)
        )
        self._on_available_tag_double_clicked = self._available_tags_delegate.subscribe_item_double_clicked(
            lambda _: self._edit_tag()
        )
        self._on_assigned_tag_edited_sub = self._assigned_tags_delegate.subscribe_item_edited(
            partial(self._on_item_edited, False)
        )
        self._on_assigned_tag_double_clicked = self._assigned_tags_delegate.subscribe_item_double_clicked(
            lambda _: self._edit_tag()
        )

        self._build_ui()

    def _build_ui(self):
        self._window = ui.Window(
            "Edit Custom Tags",
            width=500,
            height=400,
            dockPreference=ui.DockPreference.DISABLED,
            flags=(
                ui.WINDOW_FLAGS_NO_COLLAPSE
                | ui.WINDOW_FLAGS_NO_MOVE
                | ui.WINDOW_FLAGS_NO_RESIZE
                | ui.WINDOW_FLAGS_MODAL
            ),
        )

        with self._window.frame:
            with ui.HStack(spacing=ui.Pixel(8)):
                ui.Spacer(width=0)
                with ui.VStack(spacing=ui.Pixel(8)):
                    ui.Spacer(height=0)

                    with ui.HStack(height=0, spacing=ui.Pixel(8)):
                        ui.Label(
                            f"Selected Prim{'s' if len(self._selected_paths) > 1 else ''}:",
                            height=0,
                            width=0,
                            name="PropertiesPaneSectionTitle",
                        )
                        with ui.ScrollingFrame(name="PropertiesPaneSection", height=ui.Pixel(32)):
                            with ui.HStack(height=0):
                                for index, path in enumerate(self._selected_paths):
                                    ui.Label(path.split("/")[-1], tooltip=path, width=0)
                                    if index < len(self._selected_paths) - 1:
                                        ui.Label(",", width=ui.Pixel(8), height=0)

                    ui.Rectangle(height=ui.Pixel(1), name="WizardSeparator")

                    with ui.HStack(spacing=ui.Pixel(8)):
                        with ui.VStack(spacing=ui.Pixel(8)):
                            ui.Label(
                                "Available Tags",
                                tooltip=(
                                    "Tags available to be assigned to the selected Prims.\n\n"
                                    'Drag the desired tags to the "Assigned Tags" list to assign them to the selected '
                                    "Prims."
                                ),
                                name="PropertiesPaneSectionTitle",
                                height=0,
                                alignment=ui.Alignment.CENTER,
                            )
                            with ui.ScrollingFrame(name="WorkspaceBackground"):
                                self._available_tree = ui.TreeView(
                                    self._available_tags_model,
                                    delegate=self._available_tags_delegate,
                                    identifier="available_tree",
                                )
                                self._available_tags_model.set_widget(self._available_tree)
                                self._available_tree.set_selection_changed_fn(
                                    partial(self._on_selection_changed, self._available_tree)
                                )

                        with ui.VStack(spacing=ui.Pixel(8)):
                            ui.Label(
                                "Assigned Tags",
                                tooltip=(
                                    "Tags assigned to the selected Prims.\n\n"
                                    "When multiple prims are selected, this tree will only contain the tags that are "
                                    "assigned to every prim in the selection.\n\n"
                                    'Drag the desired tags to the "Available Tags" list to unassign them from the '
                                    "selected Prims."
                                ),
                                name="PropertiesPaneSectionTitle",
                                height=0,
                                alignment=ui.Alignment.CENTER,
                            )
                            with ui.ScrollingFrame(name="WorkspaceBackground"):
                                self._assigned_tree = ui.TreeView(
                                    self._assigned_tags_model,
                                    delegate=self._assigned_tags_delegate,
                                    identifier="assigned_tree",
                                )
                                self._assigned_tags_model.set_widget(self._assigned_tree)
                                self._assigned_tree.set_selection_changed_fn(
                                    partial(self._on_selection_changed, self._assigned_tree)
                                )

                    with ui.HStack(height=0, spacing=ui.Pixel(2)):
                        ui.Button("Create", height=0, clicked_fn=self._create_tag, identifier="create")
                        self._edit_button = ui.Button(
                            "Edit", height=0, enabled=False, clicked_fn=self._edit_tag, identifier="edit"
                        )
                        self._delete_button = ui.Button(
                            "Delete", height=0, enabled=False, clicked_fn=self._delete_tags, identifier="delete"
                        )

                    ui.Rectangle(height=ui.Pixel(1), name="WizardSeparator")

                    with ui.HStack(height=0, spacing=ui.Pixel(4)):
                        ui.Button("Cancel", height=0, clicked_fn=self._hide_window, identifier="cancel")
                        ui.Button("Apply", height=0, clicked_fn=self._apply, identifier="apply")

                    ui.Spacer(height=0)
                ui.Spacer(width=0)

        self._refresh_trees()

    @limit_recursion()
    def _on_selection_changed(self, widget: ui.TreeView, selection: list[TagsSelectionItem]):
        """
        Callback executed whenever the tree selection changes.

        Used to limit the selection to 1 of the 2 trees and enable/disable the Edit & Delete buttons.
        """
        # Clean the selection of the other trees
        for tree_widget in [self._available_tree, self._assigned_tree]:
            if tree_widget == widget:
                continue
            tree_widget.selection = []

        if not self._available_tree or not self._assigned_tree:
            has_selection = False
        else:
            has_selection = bool(self._available_tree.selection + self._assigned_tree.selection)

        self._update_buttons_state(has_selection)

    def _on_tags_assigned(self, tag_paths: list[str]):
        """
        Callback executed whenever a tag is dropped in the assigned tree.

        Should remove the item from the available tree and append an action to the queue
        """
        for tag_path in tag_paths:
            self._available_tags_model.remove_item(tag_path)
            for path in self._selected_paths:
                self._action_queue.append((ActionType.ADD, (path, tag_path)))

        # Update the Edit & Delete buttons when removing the item
        if not {i.path for i in self._available_tree.selection}.difference(tag_paths):
            self._update_buttons_state(False)

    def _on_tags_unassigned(self, tag_paths: list[str]):
        """
        Callback executed whenever a tag is dropped in the available tree.

        Should remove the item from the assigned tree and append an action to the queue
        """
        for tag_path in tag_paths:
            self._assigned_tags_model.remove_item(tag_path)
            for path in self._selected_paths:
                self._action_queue.append((ActionType.REMOVE, (path, tag_path)))

        # Update the Edit & Delete buttons when removing the item
        if not {i.path for i in self._assigned_tree.selection}.difference(tag_paths):
            self._update_buttons_state(False)

    def _on_item_edited(self, available_tree: bool, item: TagsEditItem, new_tag_name: str):
        """
        Callback executed whenever an Edit Item ends editing.

        Should make sure the returned value is unique, replace the item with a Tag Item and add an action to the queue
        """
        model = self._available_tags_model if available_tree else self._assigned_tags_model
        tag_path = self._core.get_unique_tag_path(
            new_tag_name,
            current_tag_path=item.original_item.path if item.original_item else None,
            existing_tag_paths=[
                i.path
                for i in self._available_tags_model.get_item_children(None)
                + self._assigned_tags_model.get_item_children(None)
                if isinstance(i, TagsSelectionItem)
            ],
        )

        if item.original_item:
            # Only Edit the tag if the name changed
            if item.original_item.title != new_tag_name:
                self._action_queue.append(
                    (ActionType.EDIT, (item.original_item.path, self._core.get_tag_name(tag_path)))
                )
        else:
            self._action_queue.append((ActionType.CREATE, self._core.get_tag_name(tag_path)))

        model.remove_item(item)
        model.insert_item(TagsSelectionItem(tag_path))

    def _refresh_trees(self):
        """
        Refresh both tag tree models
        """
        prims = [self._stage.GetPrimAtPath(paths) for paths in self._selected_paths]

        self._available_tags_model.refresh(prims)
        self._assigned_tags_model.refresh(prims)

    def _create_tag(self):
        """
        Create a new tag.

        Should insert a blank edit item in the available tree
        """
        self._available_tags_model.insert_item(TagsEditItem(), index=-1)
        self._update_buttons_state(False)

    def _edit_tag(self):
        """
        Edit the first selected tag.

        Should replace an existing item with an edit item
        """
        if not self._available_tree or not self._assigned_tree:
            return

        model = None
        tree = None

        if self._available_tree.selection:
            model = self._available_tags_model
            tree = self._available_tree
        if self._assigned_tree.selection:
            model = self._assigned_tags_model
            tree = self._assigned_tree

        if model is None or tree is None:
            return

        item_index, item = model.find_item(tree.selection[0])
        model.remove_item(item)
        model.insert_item(TagsEditItem(item), index=item_index)

        self._update_buttons_state(False)

    def _delete_tags(self):
        """
        Remove selected tags

        Should remove the items and add the action to the queue
        """
        if not self._available_tree or not self._assigned_tree:
            return

        self._action_queue.append((ActionType.DELETE, self._available_tree.selection + self._assigned_tree.selection))

        for path in self._available_tree.selection:
            self._available_tags_model.remove_item(path)

        for path in self._assigned_tree.selection:
            self._assigned_tags_model.remove_item(path)

        self._update_buttons_state(False)

    def _apply(self):
        """
        Callback executed when the `Apply` button is clicked.

        Should execute the action queue in a single undo group and hide the window
        """

        def execute_queued_actions():
            """
            Execute the queued actions in a single undo group
            """
            with omni.kit.undo.group():
                for action_data in self._action_queue:
                    action, data = action_data
                    match action:
                        case ActionType.ADD:
                            self._core.add_tag_to_prim(*data)
                        case ActionType.REMOVE:
                            self._core.remove_tag_from_prim(*data)
                        case ActionType.EDIT:
                            self._core.rename_tag(*data)
                        case ActionType.DELETE:
                            self._core.delete_tags(data, use_undo_group=False)
                        case ActionType.CREATE:
                            self._core.create_tag(data, use_undo_group=False)

            self._action_queue.clear()

        if any(a for a, _ in self._action_queue if a == ActionType.DELETE):
            self._hide_window()
            PromptManager.post_simple_prompt(
                "Confirm Tag Deletion",
                (
                    "Are you sure you want to delete the selected tags?\n\n"
                    "Deleting the tag will remove it from all the prims it is currently assigned to."
                ),
                ok_button_info=PromptButtonInfo("Cancel", self._show_window),
                cancel_button_info=PromptButtonInfo("Confirm", execute_queued_actions),
                modal=True,
            )
        else:
            execute_queued_actions()
            self._hide_window()

    def _update_buttons_state(self, value: bool):
        """
        Update the state of the Edit & Delete buttons

        Args:
            value: The new state of the buttons
        """
        self._edit_button.enabled = value
        self._delete_button.enabled = value

    def _hide_window(self):
        """
        Callback used to hide the window
        """
        if not self._window:
            return
        self._window.visible = False

    def _show_window(self):
        """
        Callback used to show the window
        """
        if not self._window:
            return
        self._window.visible = True

    def destroy(self):
        reset_default_attrs(self)

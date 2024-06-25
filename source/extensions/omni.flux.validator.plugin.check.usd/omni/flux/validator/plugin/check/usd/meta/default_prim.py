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

from typing import TYPE_CHECKING, Any, List, Tuple

import omni.kit.commands
import omni.kit.undo
import omni.ui as ui
import omni.usd
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

from ..base.check_base_usd import CheckBaseUSD as _CheckBaseUSD  # noqa PLE0402

if TYPE_CHECKING:
    from pxr import Usd


class _ListItem(ui.AbstractItem):
    """Single item of the model"""

    def __init__(self, prim):
        super().__init__()
        self.prim = prim
        self.name_model = ui.SimpleStringModel(prim.name)

    def __repr__(self):
        return f'"{self.name_model.as_string}"'


class _ListModel(ui.AbstractItemModel):
    """
    Represents the model for lists. It's very easy to initialize it
    with any string list:
        string_list = ["Hello", "World"]
        model = ListModel(*string_list)
        ui.TreeView(model)
    """

    def __init__(self):
        super().__init__()
        self._children = []

    def set_children(self, prims):
        """Update the list of top level prims, and refresh the UI"""
        self._children = [_ListItem(t) for t in prims]
        self._item_changed(None)

    def has_children(self):
        return len(self._children) > 0

    def get_item_children(self, item):
        """Returns all the children when the widget asks it."""
        if item is not None:
            # Since we are doing a flat list, we return the children of root only.
            # If it's not root we return.
            return []

        return self._children

    def get_item_value_model_count(self, item):
        """The number of columns"""
        return 1

    def get_item_value_model(self, item, column_id):
        """
        Return value model.
        It's the object that tracks the specific value.
        In our case we use ui.SimpleStringModel.
        """
        return item.name_model


class DefaultPrim(_CheckBaseUSD):
    class Data(_CheckBaseUSD.Data):
        manual_selection: bool = False

    name = "DefaultPrim"
    tooltip = "This plugin will ensure a usd file has a default prim."
    data_type = Data
    display_name = "Has Default Prim"

    def __init__(self):
        self._default_attr = {"_model": None, "_tree": None, "_frame": None}
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)
        self._model = _ListModel()
        super().__init__()

    def destroy(self):
        """Destroy."""
        _reset_default_attrs(self)

    @omni.usd.handle_exception
    async def _check(
        self, schema_data: Data, context_plugin_data: Any, selector_plugin_data: Any
    ) -> Tuple[bool, str, Any]:
        """
        Checks if the given stage has a default prim.

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the selector plugin

        Returns: True if the check passed, False if not
        """
        message = "Check:\n"

        stage = omni.usd.get_context(context_plugin_data).get_stage()
        default_prim = stage.GetDefaultPrim()
        root_prim_paths = [p.GetPath() for p in self.__get_root_prims(stage)]

        has_default = bool(default_prim and default_prim.GetPath() in root_prim_paths if root_prim_paths else True)
        has_single_root = len(root_prim_paths) <= 1

        if not has_default:
            message += f"- FAIL: Invalid default prim {stage.GetRootLayer().identifier}\n"
        elif not has_single_root:
            message += f"- FAIL: Multiple root prims {stage.GetRootLayer().identifier}\n"
        else:
            message += f"- PASS: {stage.GetRootLayer().identifier}\n"

        return has_default and has_single_root, message, None

    @omni.usd.handle_exception
    async def _fix(
        self, schema_data: Data, context_plugin_data: Any, selector_plugin_data: Any
    ) -> Tuple[bool, str, Any]:
        """
        Attempts to set a default prim.

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the selector plugin

        Returns: True if the data where fixed, False if not
        """
        message = "Fix:\n"
        all_pass = True
        stage = omni.usd.get_context(context_plugin_data).get_stage()

        root_prims_paths = [p.GetPath() for p in self.__get_root_prims(stage)]
        if len(root_prims_paths) <= 1:
            default_prim = stage.GetDefaultPrim()
            if (not default_prim or default_prim.GetPath() not in root_prims_paths) and root_prims_paths:
                omni.kit.commands.execute("SetDefaultPrim", prim_path=root_prims_paths[0], stage=stage)
                message += f"- PASS: default prim set to {root_prims_paths[0].name}\n"
            else:
                message += f"- PASS: {stage.GetRootLayer().identifier}\n"
        elif schema_data.manual_selection:
            self._model.set_children(root_prims_paths)
            if self._frame:
                self._frame.visible = True
            message += f"- FAIL: more than one root prim in {stage.GetRootLayer().identifier}\n"
            all_pass = False
        else:
            with omni.kit.undo.group():
                # Group the prims under a single prim
                omni.kit.commands.execute("GroupPrims", prim_paths=root_prims_paths, destructive=False, stage=stage)
                # Fetch the newly created group
                root_prims = self.__get_root_prims(stage)
                group_path = root_prims[0].GetPath() if root_prims else None
                if group_path:
                    # Set the group as the default prim
                    omni.kit.commands.execute("SetDefaultPrim", prim_path=group_path, stage=stage)
            if group_path:
                message += f"- PASS: Created new default prim `{group_path}` from PseudoRoot.\n"
            else:
                message += "- FAIL: Unable to create group prim from PseudoRoot.\n"
                all_pass = False

        return all_pass, message, None

    def _on_tree_selection_changed(self, items):
        if items:
            default_prim = items[0].prim
            omni.kit.commands.execute("SetDefaultPrim", prim_path=default_prim)
            self._model.set_children([])
            self._frame.visible = False

    @omni.usd.handle_exception
    async def _build_ui(self, schema_data: Data) -> Any:
        """
        Build the UI for the plugin
        """
        self._frame = ui.VStack()
        with self._frame:
            self._frame.visible = self._model.has_children()
            ui.Label("File is missing a Default Prim.  Choose one:", name="DefaultPrimLabel")
            ui.Spacer(height=ui.Pixel(8))

            with ui.HStack():
                ui.Spacer(width=ui.Pixel(4))
                with ui.ZStack(height=0):
                    ui.Rectangle(name="BackgroundWithBorder")
                    with ui.HStack():
                        ui.Spacer(width=ui.Pixel(4))
                        self._tree = ui.TreeView(
                            self._model,
                            name="DefaultPrimSelection",
                            identifier="default_prim_treeview",
                            root_visible=False,
                            header_visible=False,
                        )
                        self._tree.set_selection_changed_fn(self._on_tree_selection_changed)
                ui.Spacer(width=ui.Pixel(4))

    def __get_root_prims(self, stage: "Usd.Stage") -> List["Usd.Prim"]:
        root_prims = []

        session_layer = stage.GetSessionLayer()
        for prim in stage.GetPseudoRoot().GetChildren():
            # Get all the root prims except for Session Layer prims
            if session_layer.GetPrimAtPath(prim.GetPath()):
                continue
            root_prims.append(prim)

        return root_prims

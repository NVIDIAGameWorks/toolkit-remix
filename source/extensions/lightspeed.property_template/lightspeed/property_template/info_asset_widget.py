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

import functools

import omni.ui as ui
import omni.usd
from lightspeed.common import constants
from omni.kit.property.usd.usd_property_widget import UsdPropertiesWidget
from omni.kit.window.property.templates import HORIZONTAL_SPACING
from pxr import Sdf

from .info_asset_tree.delegate import Delegate
from .info_asset_tree.model import Item, Model


class InfoAssetWidget(UsdPropertiesWidget):
    def __init__(self, title: str):
        super().__init__(title=title, collapsed=False)
        self._title = title
        self._tree_view = None
        self._tree_models = []
        self._tree_delegate = Delegate()
        self._correcting_prim_path = False
        self.__prototypes_data = {}
        self.__prototypes_data_inverted = {}

    def _select_all_instances(self, instances):
        usd_context = omni.usd.get_context()
        usd_context.get_selection().set_selected_prim_paths([str(instance) for instance in instances], True)

    def on_new_payload(self, payload):

        self.__prototypes_data = {}

        def get_reference_prims(_prim):
            prim_paths = []
            for prim_spec in _prim.GetPrimStack():
                items = prim_spec.referenceList.prependedItems
                for item in items:
                    if item.primPath:
                        prim_paths.append(item.primPath)

            return prim_paths

        if len(payload) == 0:
            return False

        stage = payload.get_stage()
        instance_prims = []

        for p in payload:
            prim = stage.GetPrimAtPath(p)
            if prim.IsValid():
                if str(p).startswith(constants.INSTANCE_PATH):
                    instance_prims.append(prim)
                elif str(p).startswith(constants.MESH_PATH):
                    self.__prototypes_data[p] = [Sdf.Path(p)]

        # Get the mesh asset(s) for all selected instances
        for prim in instance_prims:
            refs_and_layers = omni.usd.get_composed_references_from_prim(prim)
            for ref, _ in refs_and_layers:
                if not ref.assetPath:
                    if (
                        ref.primPath in self.__prototypes_data
                        and prim.GetPath() not in self.__prototypes_data[ref.primPath]
                    ):
                        self.__prototypes_data[ref.primPath].append(prim.GetPath())
                    else:
                        self.__prototypes_data[ref.primPath] = [ref.primPath, prim.GetPath()]
                    self.__prototypes_data_inverted[prim.GetPath()] = ref.primPath

        # grab all instances affected by the protoype
        iterator = iter(stage.TraverseAll())
        for prim in iterator:
            ref = get_reference_prims(prim)
            if ref and ref[0] in self.__prototypes_data and prim.GetPath() not in self.__prototypes_data[ref[0]]:
                self.__prototypes_data[ref[0]].append(prim.GetPath())
                self.__prototypes_data_inverted[prim.GetPath()] = ref[0]

        self._payload = payload
        if not self.__prototypes_data:
            return False
        return True

    def clean(self):
        self._tree_delegate.destroy()
        self._tree_delegate = None
        for model in self._tree_models:
            model.destroy()
        self._tree_models = []
        self._tree_view = None
        super().clean()

    def build_items(self):
        self._collapsable_frame.name = "groupFrame"  # to have dark background
        self._tree_models = []
        with ui.VStack(spacing=8):
            for prim_path in self._payload:
                with ui.CollapsableFrame(
                    title=prim_path.name,
                ):
                    with ui.VStack(spacing=8):
                        with ui.HStack(spacing=HORIZONTAL_SPACING):
                            ui.Label("Selected prim path(s)", name="label", width=ui.Percent(25))
                            ui.StringField(read_only=True).model.set_value(str(prim_path))

                        instances = []
                        if self.__prototypes_data_inverted.get(prim_path):
                            instances = self.__prototypes_data[self.__prototypes_data_inverted[prim_path]]
                        elif self.__prototypes_data.get(prim_path):
                            instances = self.__prototypes_data[prim_path]
                        if instances:
                            instances0 = sorted(instances, key=lambda x: x.pathString)
                            instances1 = sorted(instances0, key=lambda x: len(x.pathString), reverse=False)

                            ui.Label("This instance shares the same mesh/material(s) than:", name="label")

                            model = Model()
                            items = []
                            current_item = None
                            for instance in instances1:
                                item = Item(str(instance))
                                if instance == prim_path:
                                    current_item = item
                                items.append(item)
                            model.set_items(items)
                            self._tree_models.append(model)
                            with ui.ScrollingFrame(
                                horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                                vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_ON,
                                style_type_name_override="TreeView",
                                height=100,
                            ):
                                self._tree_view = ui.TreeView(
                                    model,
                                    delegate=self._tree_delegate,
                                    root_visible=False,
                                    header_visible=False,
                                    name="TreePanel",
                                )
                                self._tree_view.selection = [current_item]
                                self._tree_view.set_selection_changed_fn(self._on_tree_selection_changed)
                            ui.Button(
                                "Select all instances",
                                clicked_fn=functools.partial(self._select_all_instances, instances1),
                                tooltip="Select all instances that uses this USD reference",
                            )

    def _on_tree_selection_changed(self, items):
        if len(items) > 1:
            self._tree_view.selection = [items[0]]
        if items:
            usd_context = omni.usd.get_context()
            usd_context.get_selection().set_selected_prim_paths([items[0].path], True)

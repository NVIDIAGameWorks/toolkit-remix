"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = ["LogicPropertyWidget"]

import asyncio
from typing import Any

import omni.graph.core as og
import omni.graph.tools.ogn as ogn
import omni.kit
import omni.ui as ui
import omni.usd
from lightspeed.common.constants import OMNI_GRAPH_NODE_TYPE
from omni.flux.property_widget_builder.model.usd import USDAttributeItem, USDAttrListItem
from omni.flux.property_widget_builder.model.usd import USDDelegate as _USDPropertyDelegate
from omni.flux.property_widget_builder.model.usd import USDModel as _USDPropertyModel
from omni.flux.property_widget_builder.model.usd import USDPropertyWidget
from omni.flux.property_widget_builder.model.usd import get_usd_listener_instance
from omni.flux.property_widget_builder.widget import FieldBuilder
from omni.flux.property_widget_builder.widget import ItemGroup
from omni.flux.utils.common import Event
from omni.flux.utils.common import EventSubscription
from pxr import Sdf, Usd

LOGIC_ATTR_GROUP_ORDER = ("Inputs", "Outputs", "State", "Node", "Other")
LOGIC_ATTR_GROUP_FALLBACK = "Other"

# Attribute name prefixes
OGN_ATTR_PREFIX_INPUTS = "inputs:"
OGN_ATTR_PREFIX_OUTPUTS = "outputs:"
OGN_ATTR_PREFIX_NODE = "node:"
OGN_ATTR_PREFIX_STATE = "state:"
OGN_ATTR_PREFIX_UI = "ui:"


class LogicPropertyWidget:
    """
    Properties panel for Remix Logic graph management and graph node prim types.
    """

    def __init__(
        self,
        context_name: str,
        tree_column_widths: list[ui.Length] | None = None,
        columns_resizable: bool = False,
        right_aligned_labels: bool = True,
        lookup_table: dict[str, dict[str, str]] | None = None,
        field_builders: list[FieldBuilder] | None = None,
    ):
        """
        Args:
            context_name: USD context name
            tree_column_widths: Column widths for the tree
            columns_resizable: Whether columns are resizable
            right_aligned_labels: Whether labels are right aligned
            lookup_table: Table for custom display names and groups
            field_builders: Custom field builders for specific attribute types
        """

        self._property_delegate = None
        self._property_model = None
        self._property_widget = None
        self._root_frame = None

        self.__refresh_done = Event()
        self._refresh_task = None

        self._node_type_label_text: str = ""
        self._node_type_label_description_text: str = ""

        self._context_name = context_name
        self._context = omni.usd.get_context(context_name)
        if tree_column_widths is None:
            tree_column_widths = [ui.Pixel(270), ui.Fraction(1)]
        self._tree_column_widths = tree_column_widths
        self._columns_resizable = columns_resizable
        self._right_aligned_labels = right_aligned_labels

        self.__usd_listener_instance = get_usd_listener_instance()

        self._paths: list[Sdf.Path] = []
        self._valid_target_paths: list[Sdf.Path] = []

        self._lookup_table = lookup_table or {}

        self.__create_ui(field_builders=field_builders)

    def _refresh_done(self) -> None:
        """Call the event object that has the list of functions."""
        if self.__refresh_done:
            self.__refresh_done()

    def subscribe_refresh_done(self, callback) -> EventSubscription:
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return EventSubscription(self.__refresh_done, callback)

    @property
    def field_builders(self):
        if self._property_delegate is None:
            raise AttributeError("Need to run __create_ui first.")
        return self._property_delegate.field_builders

    def __create_ui(self, field_builders: list[FieldBuilder] | None = None) -> None:
        """Create the UI components."""
        self._property_model = _USDPropertyModel(self._context_name)
        self._property_delegate = _USDPropertyDelegate(
            field_builders=field_builders,
            right_aligned_labels=self._right_aligned_labels,
        )
        self._root_frame = ui.Frame(build_fn=self._build_root_frame)

    def _build_root_frame(self) -> None:
        with ui.ZStack():
            with ui.VStack(height=0, spacing=ui.Pixel(8)):
                if self._paths:
                    # A logic node is selected, so show node info and the property widget
                    ui.Spacer(height=ui.Pixel(8))
                    ui.Line(name="PropertiesPaneSectionTitle")
                    ui.Spacer(height=ui.Pixel(8))

                    with ui.VStack(height=0, spacing=ui.Pixel(8)):
                        ui.Label(f"Node Type: {self._node_type_label_text}", name="PropertiesWidgetLabel")
                        if self._node_type_label_description_text:
                            ui.Label(
                                self._node_type_label_description_text,
                                word_wrap=True,
                            )
                    ui.Spacer(height=ui.Pixel(8))
                    self._property_widget = USDPropertyWidget(
                        self._context_name,
                        model=self._property_model,
                        delegate=self._property_delegate,
                        tree_column_widths=self._tree_column_widths,
                        columns_resizable=self._columns_resizable,
                        refresh_callback=self.refresh,
                    )
                else:
                    with ui.HStack(height=ui.Pixel(24), spacing=ui.Pixel(8)):
                        ui.Spacer(height=0)
                        with ui.VStack(width=0):
                            ui.Spacer()
                            ui.Label("None", name="PropertiesWidgetLabel")
                            ui.Spacer()
                        ui.Spacer(height=0)

    def refresh(
        self,
        prims: list[Usd.Prim] | None = None,
        valid_target_prims: list[Usd.Prim] | None = None,
    ):
        """
        Refresh the panel with the given prims

        Args:
            prims: The prims to display properties for
            valid_target_prims: Valid target prims for creating logic graphs
        """
        if self._refresh_task is not None:
            self._refresh_task.cancel()
        self._refresh_task = asyncio.ensure_future(self._deferred_refresh(prims, valid_target_prims))

    @omni.usd.handle_exception
    async def _deferred_refresh(
        self,
        prims: list[Usd.Prim] | None = None,
        valid_target_prims: list[Usd.Prim] | None = None,
    ):
        """
        Deferred refresh to handle USD updates properly

        Args:
            prims: The prims to display properties for
            valid_target_prims: Valid target prims for creating logic graphs
        """

        if prims is not None:
            self._paths = [prim.GetPath() for prim in prims]
        if valid_target_prims is not None:
            self._valid_target_paths = [prim.GetPath() for prim in valid_target_prims]

        # Wait 1 frame to make sure the USD is up-to-date
        await omni.kit.app.get_app().next_update_async()

        if self.__usd_listener_instance and self._property_model:  # noqa PLE0203
            self.__usd_listener_instance.remove_model(self._property_model)  # noqa PLE0203

        stage: Usd.Stage = self._context.get_stage()
        items: list[ItemGroup | USDAttributeItem | USDAttrListItem] = []
        valid_paths: list[Sdf.Path] = []

        self._node_type_label_text = "No valid node type selected"
        self._node_type_label_description_text = ""

        node_types: list[og.NodeType] = []

        if stage is not None:  # noqa PLR1702

            # Group attributes by name across all selected prims
            attr_added: dict[str, list[tuple[Usd.Prim, og.Attribute]]] = {}

            if prims is None:
                prims = []

            for prim in prims:
                if not prim.IsValid():
                    continue
                if prim.GetTypeName() != OMNI_GRAPH_NODE_TYPE:
                    continue

                node: og.Node = og.get_node_by_path(str(prim.GetPath()))
                if not node:
                    continue
                node_types.append(node.get_node_type())
                valid_paths.append(prim.GetPath())

                attrs = node.get_attributes()
                for attr in attrs:
                    attr_name = attr.get_name()

                    # Filter for logic graph relevant attributes
                    if attr_name.startswith(OGN_ATTR_PREFIX_UI):
                        continue

                    # Group attributes by name across all prims
                    attr_added.setdefault(attr_name, []).append((prim, attr))

            # Get text for the node type description
            # Dedupe with a set of node type names because node type is not hashable
            node_type_names = {node_type.get_node_type() for node_type in node_types}
            if len(node_type_names) == 1:
                self._node_type_label_text = node_types[0].get_metadata(ogn.MetadataKeys.UI_NAME)
                self._node_type_label_description_text = node_types[0].get_metadata(ogn.MetadataKeys.DESCRIPTION)
            elif len(node_type_names) > 1:
                self._node_type_label_text = "Multiple node types selected"

            # Group items by category for better organization
            group_items: dict[str, ItemGroup] = {}
            num_prims = len(valid_paths)

            # Sort attribute names for better organization
            sorted_attr_names = self._sort_logic_attributes(list(attr_added.keys()))

            # Create attribute items and collect them by group
            for attr_name in sorted_attr_names:
                prims_and_attrs = attr_added[attr_name]
                # Only allow editing common attributes (attributes that exist on all selected prims)
                if num_prims != len(prims_and_attrs):
                    # Skip attribute because not all prims have it
                    continue

                # assume all selected prims with matching attrs are the same
                prim, attr = prims_and_attrs[0]

                # Get all attribute paths for this attribute name across all prims
                attributes = [attr for prim, attr in prims_and_attrs]
                attribute_paths = [Sdf.Path(attr.get_path()) for attr in attributes]

                # Prioritize values from lookup table
                display_info = self._lookup_table.get(attr_name, {})
                display_name = display_info.get("name")
                group_name = display_info.get("group")
                tooltip = display_info.get("tooltip")

                # Fill in missing values from the ogn attribute
                if not display_name:
                    display_name = attr.get_metadata(ogn.MetadataKeys.UI_NAME) or attr_name
                if not group_name:
                    if attr_name.startswith(OGN_ATTR_PREFIX_INPUTS):
                        group_name = "Inputs"
                    elif attr_name.startswith(OGN_ATTR_PREFIX_OUTPUTS):
                        group_name = "Outputs"
                    elif attr_name.startswith(OGN_ATTR_PREFIX_STATE):
                        group_name = "State"
                    elif attr_name.startswith(OGN_ATTR_PREFIX_NODE):
                        group_name = "Node"
                    else:
                        group_name = LOGIC_ATTR_GROUP_FALLBACK
                if not tooltip:
                    tooltip = attr.get_metadata(ogn.MetadataKeys.DESCRIPTION) or ""

                default_value: Any = attr.get_metadata(ogn.MetadataKeys.DEFAULT)

                options: list[str] | None = None
                allowed_tokens = attr.get_metadata(ogn.MetadataKeys.ALLOWED_TOKENS)
                if allowed_tokens:
                    options = allowed_tokens.split(",")

                read_only = True
                if attr_name.startswith(OGN_ATTR_PREFIX_INPUTS):
                    read_only = False

                # TODO: Add support for target relationships (REMIX-4245)
                if attr.get_type_name() == "target":
                    continue  # skip for now

                value_type_name = None
                ogn_type: og.AttributeType = attr.get_attribute_data().get_type()
                value_type_name_str: str = og.AttributeType.sdf_type_name_from_type(ogn_type)
                if value_type_name_str:
                    value_type_name = Sdf.ValueTypeNames.Find(value_type_name_str)
                if not value_type_name:
                    value_type_name = Sdf.ValueTypeNames.String

                # Create an attribute item to manage all attribute paths
                if options:
                    attr_item = USDAttrListItem(
                        self._context_name,
                        attribute_paths,
                        default_value,
                        options,
                        read_only=read_only,
                        value_type_name=value_type_name,
                        display_attr_names=[display_name],
                        display_attr_names_tooltip=[tooltip],
                    )
                else:
                    attr_item = USDAttributeItem(
                        self._context_name,
                        attribute_paths,
                        read_only=read_only,
                        value_type_name=value_type_name,
                        display_attr_names=[display_name],
                        display_attr_names_tooltip=[tooltip],
                    )

                # Collect items by group (but don't add to items list yet)
                if group_name not in group_items:
                    group_items[group_name] = ItemGroup(group_name)
                group_items[group_name].children.append(attr_item)

            # Add groups to items in the specified order
            for group_name in LOGIC_ATTR_GROUP_ORDER:
                if group_name in group_items:
                    items.append(group_items[group_name])

            # Add any remaining groups not in the predefined order (for future extensibility)
            for group_name, group in group_items.items():
                if group_name not in LOGIC_ATTR_GROUP_ORDER:
                    items.append(group)

        self._property_model.set_prim_paths(valid_paths)
        self._property_model.set_items(items)
        if self.__usd_listener_instance:
            self.__usd_listener_instance.add_model(self._property_model)

        self._root_frame.rebuild()

        self._refresh_done()

    def _sort_logic_attributes(self, attr_names: list[str]) -> list[str]:
        """Sort logic graph attributes by type and name."""
        # For logic graphs, we'll separate inputs, outputs, and state attributes
        # and sort each group alphabetically
        inputs: list[str] = []
        outputs: list[str] = []
        state: list[str] = []
        node: list[str] = []
        other: list[str] = []

        for attr_name in attr_names:
            if attr_name.startswith(OGN_ATTR_PREFIX_INPUTS):
                inputs.append(attr_name)
            elif attr_name.startswith(OGN_ATTR_PREFIX_OUTPUTS):
                outputs.append(attr_name)
            elif attr_name.startswith(OGN_ATTR_PREFIX_STATE):
                state.append(attr_name)
            elif attr_name.startswith(OGN_ATTR_PREFIX_NODE):
                node.append(attr_name)
            else:
                other.append(attr_name)

        # Sort each group alphabetically
        inputs.sort()
        outputs.sort()
        state.sort()
        node.sort()
        other.sort()

        # Combine: inputs, outputs, state, then other
        return inputs + outputs + state + node + other

    @property
    def property_model(self):
        return self._property_model

    def show(self, value: bool) -> None:
        """
        Show the panel or not

        Args:
            value: Visible or not
        """
        if self._property_widget is not None:
            self._property_widget.enable_listeners(value)
        self._root_frame.visible = value
        if not value and self.__usd_listener_instance and self._property_model:
            self.__usd_listener_instance.remove_model(self._property_model)
        if not value:
            self._property_delegate.reset()

    def destroy(self) -> None:
        """Clean up listeners and UI Widgets."""
        if self._refresh_task:
            self._refresh_task.cancel()
        if self._root_frame:
            self._root_frame.clear()
        if self.__usd_listener_instance and self._property_model:
            self.__usd_listener_instance.remove_model(self._property_model)
        self.__usd_listener_instance = None
        self.__refresh_done = None
        self._refresh_task = None
        self._context = None
        self._property_delegate = None
        self._property_model = None
        self._property_widget = None
        self._root_frame = None

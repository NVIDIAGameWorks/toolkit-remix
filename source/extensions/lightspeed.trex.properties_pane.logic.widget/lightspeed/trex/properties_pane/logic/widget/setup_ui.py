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
import re
from functools import partial
from typing import Any, Callable

import omni.graph.core as og
import omni.graph.tools.ogn as ogn
import omni.kit
import omni.kit.commands
import omni.ui as ui
import omni.usd
from lightspeed.common.constants import OMNI_GRAPH_NODE_TYPE, REGEX_MESH_TO_INSTANCE_SUB, GlobalEventNames
from lightspeed.events_manager import get_instance as _get_event_manager_instance
from lightspeed.trex.logic.core.attributes import get_ogn_default_value
from lightspeed.trex.logic.core.graphs import LogicGraphCore
from omni.flux.info_icon.widget import InfoIconWidget
from omni.flux.property_widget_builder.delegates.string_value.file_picker import FilePicker
from omni.flux.property_widget_builder.model.usd import USDAttributeItem, USDAttrListItem
from omni.flux.property_widget_builder.model.usd import USDDelegate as _USDPropertyDelegate
from omni.flux.property_widget_builder.model.usd import USDModel as _USDPropertyModel
from omni.flux.property_widget_builder.model.usd import (
    USDPropertyWidget,
    USDRelationshipItem,
    get_usd_listener_instance,
)
from omni.flux.property_widget_builder.model.usd.field_builders.ogn import is_ogn_node_attr
from omni.flux.property_widget_builder.model.usd.utils import is_property_relationship
from omni.flux.property_widget_builder.widget import FieldBuilder, ItemGroup
from omni.flux.utils.common import Event, EventSubscription
from omni.flux.utils.common.icons import get_prim_type_icons as _get_prim_type_icons
from pxr import Sdf, Usd

LOGIC_ATTR_GROUP_ORDER = ("Inputs", "Outputs", "State", "Other")
LOGIC_ATTR_GROUP_FALLBACK = "Other"

# Attribute name prefixes
OGN_ATTR_PREFIX_INPUTS = "inputs:"
OGN_ATTR_PREFIX_OUTPUTS = "outputs:"
OGN_ATTR_PREFIX_NODE = "node:"
OGN_ATTR_PREFIX_STATE = "state:"
OGN_ATTR_PREFIX_UI = "ui:"


def _is_const_asset_path_value(item) -> bool:
    """Check if item is ConstAssetPath.value attribute."""
    return is_ogn_node_attr(item, "lightspeed.trex.logic.ConstAssetPath", "inputs:value")


# Field builder for ConstAssetPath.value - uses FilePicker instead of string field
CONST_ASSET_PATH_FIELD_BUILDER = FieldBuilder(
    claim_func=_is_const_asset_path_value,
    build_func=FilePicker(use_relative_paths=True).build_ui,
)

_SPACING_SM = 4
_SPACING_MD = 8
_ICON_SIZE = 16
_ROW_HEIGHT = 24
_BUTTON_WIDTH_SM = 80
_LABEL_WIDTH_MD = 120
_TREE_COLUMN_WIDTH = 270


def _build_prim_row_with_icon(
    icon_map: dict[str, str],
    prim_path: str,
    prim_type: str,
    clicked_fn: Callable | None,
    row_height: int,
) -> None:
    """
    Custom row builder that displays prim type icon.

    Args:
        icon_map: Mapping of prim type names to icon style names.
        prim_path: The prim path to display.
        prim_type: The prim type name.
        clicked_fn: Callback when the row is clicked.
        row_height: Height of the row in pixels.
    """
    icon_name = icon_map.get(prim_type, "Xform")
    tooltip = f"({prim_type}) {prim_path}" if prim_type else prim_path
    display_path = re.sub(r".*/mesh_[^/]+/", "", prim_path)

    with ui.HStack(height=ui.Pixel(row_height)):
        ui.Spacer(width=ui.Pixel(_SPACING_MD))
        with ui.VStack(width=ui.Pixel(_ICON_SIZE)):
            ui.Spacer()
            ui.Image("", name=icon_name, width=ui.Pixel(_ICON_SIZE), height=ui.Pixel(_ICON_SIZE))
            ui.Spacer()
        ui.Spacer(width=ui.Pixel(_SPACING_SM))
        ui.Button(
            display_path,
            height=ui.Pixel(row_height),
            name="StagePrimPickerItem",
            clicked_fn=clicked_fn,
            alignment=ui.Alignment.LEFT_CENTER,
            tooltip=tooltip,
        )
        ui.Spacer(width=ui.Pixel(_SPACING_MD))


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
        show_node_properties: bool = True,
    ):
        """
        Args:
            context_name: USD context name
            tree_column_widths: Column widths for the tree
            columns_resizable: Whether columns are resizable
            right_aligned_labels: Whether labels are right aligned
            lookup_table: Table for custom display names and groups
            field_builders: Custom field builders for specific attribute types
            show_node_properties: Whether to show node properties widget
        """

        self._event_manager = _get_event_manager_instance()
        self._property_delegate = None
        self._property_model = None
        self._property_widget = None
        self._property_frame = None
        self._dynamic_content_frame = None
        self._root_frame = None

        self.__refresh_done = Event()
        self._refresh_task = None

        self._node_type_label_text: str = ""
        self._node_type_label_description_text: str = ""
        self._node_type_tooltip_text: str = ""

        self._context_name = context_name
        self._context = omni.usd.get_context(context_name)
        if tree_column_widths is None:
            tree_column_widths = [ui.Pixel(_TREE_COLUMN_WIDTH), ui.Fraction(1)]
        self._tree_column_widths = tree_column_widths
        self._columns_resizable = columns_resizable
        self._right_aligned_labels = right_aligned_labels
        self._show_node_properties = show_node_properties

        self.__usd_listener_instance = get_usd_listener_instance()

        self._paths: list[Sdf.Path] = []
        self._valid_target_paths: list[Sdf.Path] = []

        self._lookup_table = lookup_table or {}

        # Add ConstAssetPath file picker to field builders
        all_field_builders = [CONST_ASSET_PATH_FIELD_BUILDER]
        if field_builders:
            all_field_builders.extend(field_builders)

        self.__create_ui(field_builders=all_field_builders)

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

    def _compute_path_patterns_for_node(self, node_path: str) -> tuple[list[str], str] | None:
        """
        Compute path patterns for target picker based on mesh_HASH ancestor.

        Extracts mesh_HASH path using regex, then shows all its children.

        Returns:
            Tuple of (path_patterns, mesh_hash_path) or None if no match.
        """
        match = re.match(REGEX_MESH_TO_INSTANCE_SUB, node_path)
        if match:
            mesh_hash_path = match.group(1)
            return [f"{mesh_hash_path}/**"], mesh_hash_path
        return None

    def _build_relationship_ui_metadata(
        self,
        node_path: str,
        attr_name: str,
    ) -> dict:
        """
        Build ui_metadata for a relationship item's picker widget.

        Args:
            node_path: Path to the OmniGraph node
            attr_name: Name of the relationship attribute

        Returns:
            Dict with picker configuration (path_patterns, prim_filter, etc.)
        """
        ui_metadata: dict[str, Any] = {
            "initial_items": 20,
        }

        # Compute path patterns from node location
        path_info = self._compute_path_patterns_for_node(node_path)
        if path_info:
            path_patterns, mesh_hash_path = path_info
            ui_metadata["path_patterns"] = path_patterns
            mesh_hash_name = mesh_hash_path.rsplit("/", 1)[-1]

            def build_header():
                ui.Label("Selected Prim: ", name="StagePrimPickerHeaderText", width=_LABEL_WIDTH_MD)
                ui.Label(mesh_hash_name, name="StagePrimPickerHeaderTextBold", width=0)

            ui_metadata["header_text"] = build_header
            ui_metadata["header_tooltip"] = "Only children of the selected prims can be selected"

        # Get filter types from OmniGraph metadata
        node = og.get_node_by_path(node_path)
        if node:
            target_attr = node.get_attribute(attr_name)
            if target_attr:
                filter_prim_types = target_attr.get_metadata("filterPrimTypes") or []
                if filter_prim_types:

                    def prim_filter(prim):
                        prim_full_type = prim.GetPrimTypeInfo().GetSchemaType().typeName
                        return prim_full_type in filter_prim_types

                    ui_metadata["prim_filter"] = prim_filter

        # Add custom row builder with prim type icons
        icon_map = _get_prim_type_icons()
        if icon_map:
            ui_metadata["row_build_fn"] = partial(_build_prim_row_with_icon, icon_map)

        return ui_metadata

    def __create_ui(self, field_builders: list[FieldBuilder] | None = None) -> None:
        """Create the UI components once - PropertyWidget is reused across refreshes to preserve expansion state."""
        self._property_model = _USDPropertyModel(self._context_name)
        self._property_delegate = _USDPropertyDelegate(
            field_builders=field_builders,
            right_aligned_labels=self._right_aligned_labels,
        )
        self._root_frame = ui.Frame()
        with self._root_frame:
            with ui.VStack():
                # Dynamic content frame - rebuilt for buttons and existing graphs list
                self._dynamic_content_frame = ui.Frame(build_fn=self._build_dynamic_content)

                # Property widget frame - created once, visibility toggled to preserve expansion state
                self._property_frame = ui.Frame(visible=False)
                with self._property_frame:
                    self._property_widget = USDPropertyWidget(
                        self._context_name,
                        model=self._property_model,
                        delegate=self._property_delegate,
                        tree_column_widths=self._tree_column_widths,
                        columns_resizable=self._columns_resizable,
                        refresh_callback=self.refresh,
                    )

    def _get_relative_path(self, path: Sdf.Path, valid_target_paths: list[Sdf.Path]) -> str:
        """Get the relative path of the given path"""
        for target_path in valid_target_paths:
            if path.HasPrefix(target_path):
                return str(path.MakeRelativePath(target_path))
        return path.GetName()

    def _build_dynamic_content(self) -> None:
        """Build the dynamic content (buttons, existing graphs list, node info labels)."""
        with ui.VStack(height=0):
            # Check if a logic graph can be created from the selected prims
            if len(self._valid_target_paths) == 1:
                tooltip = "Create a new logic graph for the selected asset"
            else:
                tooltip = (
                    "Select a prim inside of a mesh or light asset replacement root to create a logic graph.\n\n"
                    "NOTE: The logic graph will be created on the associated root not the instance prim."
                )
            with ui.VStack(spacing=ui.Pixel(8)):
                ui.Spacer(height=0)
                ui.Button(
                    "Create a New Logic Graph",
                    clicked_fn=lambda: self._create_logic_graphs(self._valid_target_paths),
                    tooltip=tooltip,
                    enabled=len(self._valid_target_paths) == 1,
                    height=ui.Pixel(_ROW_HEIGHT),
                )
                # Check if there are any existing logic graphs
                ui.Spacer(height=0)
            existing_graphs = LogicGraphCore.get_existing_logic_graphs(
                self._context.get_stage(), self._valid_target_paths
            )
            if existing_graphs:
                ui.Label("Existing Graphs", name="PropertiesWidgetLabel", height=0)
                ui.Spacer(height=ui.Pixel(_SPACING_SM))

            for graph in existing_graphs:
                with ui.HStack(height=ui.Pixel(_ROW_HEIGHT), spacing=ui.Pixel(_SPACING_SM)):
                    relative_path = self._get_relative_path(graph.GetPath(), self._valid_target_paths)
                    ui.Label(
                        graph.GetPath().name, tooltip=relative_path, elided_text=True, name="PropertiesWidgetValue"
                    )
                    ui.Spacer(width=0)
                    ui.Image(
                        "",
                        name="Edit",
                        width=ui.Pixel(_ICON_SIZE),
                        height=ui.Pixel(_ICON_SIZE),
                        tooltip="Edit the logic graph",
                        mouse_released_fn=partial(self._edit_logic_graph, graph),
                    )
                    ui.Spacer(width=0)
                    ui.Image(
                        "",
                        name="TrashCan",
                        width=ui.Pixel(_ICON_SIZE),
                        height=ui.Pixel(_ICON_SIZE),
                        tooltip="Delete the logic graph",
                        mouse_released_fn=partial(self._delete_logic_graph, graph),
                    )
                    ui.Spacer(width=0)
            if self._paths and self._show_node_properties:
                # A logic node is selected, so show node info
                ui.Spacer(height=ui.Pixel(_SPACING_MD))
                ui.Line(name="PropertiesPaneSectionTitle")
                ui.Spacer(height=ui.Pixel(_SPACING_MD))

                with ui.HStack(height=0, spacing=ui.Pixel(_SPACING_SM)):
                    ui.Label("Node Type", name="PropertiesWidgetLabel", height=0, width=0)
                    ui.Spacer(width=0)
                    if self._node_type_tooltip_text:
                        InfoIconWidget(self._node_type_tooltip_text)
                        ui.Spacer(width=0)
                ui.Spacer(height=ui.Pixel(_SPACING_SM))

                ui.Label(self._node_type_label_text, name="PropertiesWidgetValue", width=0)
                ui.Spacer(height=ui.Pixel(_SPACING_MD))

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

        # Check if widget is being destroyed
        if not self._context:
            return

        if self.__usd_listener_instance and self._property_model:  # noqa PLE0203
            self.__usd_listener_instance.remove_model(self._property_model)  # noqa PLE0203

        stage: Usd.Stage = self._context.get_stage()
        items: list[ItemGroup | USDAttributeItem | USDAttrListItem | USDRelationshipItem] = []
        valid_paths: list[Sdf.Path] = []

        self._node_type_label_text = "No valid node type selected"
        self._node_type_label_description_text = ""
        self._node_type_tooltip_text = ""

        node_types: list[og.NodeType] = []

        if stage is not None:  # noqa PLR1702

            # Group attributes by name across all selected prims
            attr_added: dict[str, list[tuple[Usd.Prim, og.Attribute]]] = {}

            if prims is None:
                prims = [stage.GetPrimAtPath(path) for path in self._paths]

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
                    # Skip node: attributes (type, version info shown in tooltip instead)
                    if attr_name.startswith(OGN_ATTR_PREFIX_NODE):
                        continue

                    # Group attributes by name across all prims
                    attr_added.setdefault(attr_name, []).append((prim, attr))

            # Get text for the node type info
            # Dedupe with a set of node type names because node type is not hashable
            node_type_names = {node_type.get_node_type() for node_type in node_types}
            if len(node_type_names) == 1:
                node_type = node_types[0]
                self._node_type_label_text = node_type.get_metadata(ogn.MetadataKeys.UI_NAME)
                # Build tooltip with description and node type info
                description = node_type.get_metadata(ogn.MetadataKeys.DESCRIPTION) or ""
                self._node_type_label_description_text = description
                full_type_name = node_type.get_node_type()
                # Get version from node:typeVersion attribute on the prim
                version = stage.GetPrimAtPath(valid_paths[0]).GetAttribute("node:typeVersion").Get(0)
                # Build tooltip text
                tooltip_parts = []
                if description:
                    tooltip_parts.append(description)
                    tooltip_parts.append("\n---\n")
                tooltip_parts.append(f"Node Internal Name: {full_type_name}")
                tooltip_parts.append(f"Node Version: {version}")
                self._node_type_tooltip_text = "\n".join(tooltip_parts)
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
                    else:
                        group_name = LOGIC_ATTR_GROUP_FALLBACK
                if not tooltip:
                    tooltip = attr.get_metadata(ogn.MetadataKeys.DESCRIPTION) or ""

                default_value: Any = get_ogn_default_value(attr)

                options: list[str] | None = None
                allowed_tokens = attr.get_metadata(ogn.MetadataKeys.ALLOWED_TOKENS)
                if allowed_tokens:
                    options = allowed_tokens.split(",")

                is_input = attr_name.startswith(OGN_ATTR_PREFIX_INPUTS)
                read_only = True
                if is_input:
                    read_only = False

                is_relationship = is_property_relationship(stage, attribute_paths[0])
                if is_relationship:
                    # Build prim picker configuration (filters, path patterns, pagination, etc.)
                    node_path = str(prim.GetPath())
                    ui_metadata = self._build_relationship_ui_metadata(node_path, attr_name)

                    attr_item = USDRelationshipItem(
                        self._context_name,
                        attribute_paths,
                        display_attr_names=[display_name],
                        display_attr_names_tooltip=[tooltip],
                        read_only=read_only,
                        ui_metadata=ui_metadata,
                    )
                else:
                    value_type_name = None
                    ogn_type: og.AttributeType = attr.get_resolved_type()
                    if ogn_type.base_type == og.BaseDataType.UNKNOWN:
                        # Fall back to attribute data type for unresolved flexible types
                        ogn_type = attr.get_attribute_data().get_type()
                    value_type_name_str: str = og.AttributeType.sdf_type_name_from_type(ogn_type)
                    if value_type_name_str:
                        value_type_name = Sdf.ValueTypeNames.Find(value_type_name_str)
                    if not value_type_name:
                        value_type_name = Sdf.ValueTypeNames.String
                        default_value = str(default_value)

                    extended_type = attr.get_extended_type()
                    is_flexible_type = extended_type in (
                        og.ExtendedAttributeType.EXTENDED_ATTR_TYPE_UNION,
                        og.ExtendedAttributeType.EXTENDED_ATTR_TYPE_ANY,
                    )
                    if is_flexible_type:
                        read_only = True
                        if is_input:
                            tooltip += "(Flexible Input - Set value and resolve type by connecting to a node's output)"
                        else:
                            tooltip += "(Flexible Output Type - Determined by connected input types)"
                        if ogn_type.base_type == og.BaseDataType.UNKNOWN:
                            if is_input:
                                default_value = "Connect to a node output."
                            else:
                                default_value = "Unresolved: Connect flexible inputs"
                        else:
                            # If type is resolved, get the value from the connected port
                            upstream_connections = attr.get_upstream_connections()
                            if upstream_connections:
                                default_value = upstream_connections[0].get()
                            else:
                                default_value = None
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
                            default_value=default_value,
                            read_only=read_only,
                            value_type_name=value_type_name,
                            display_attr_names=[display_name],
                            display_attr_names_tooltip=[tooltip],
                        )

                # Collect items by group (but don't add to items list yet)
                if group_name not in group_items:
                    group_items[group_name] = ItemGroup(group_name, expanded=True)
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

        # Rebuild only the dynamic content (buttons, graphs list, labels)
        self._dynamic_content_frame.rebuild()

        # Toggle property widget visibility - PropertyWidget instance is preserved to retain expansion state
        show_properties = bool(self._paths and self._show_node_properties)
        self._property_frame.visible = show_properties

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

    def _create_logic_graphs(self, prim_paths: list[Sdf.Path]) -> None:
        """Create logic graphs on the specified prims."""
        if len(prim_paths) != 1:
            raise ValueError(f"Expected 1 prim path, got {len(prim_paths)}")
        prim = self._context.get_stage().GetPrimAtPath(prim_paths[0])
        if not prim:
            raise ValueError(f"Received invalid prim at path {prim_paths[0]}")
        self._event_manager.call_global_custom_event(GlobalEventNames.LOGIC_GRAPH_CREATE_REQUEST.value, prim)

    def _edit_logic_graph(self, graph: Usd.Prim, x, y, b, m) -> None:
        """Edit the given logic graph."""
        if b != 0:
            return
        self._event_manager.call_global_custom_event(GlobalEventNames.LOGIC_GRAPH_EDIT_REQUEST.value, graph)

    def _delete_logic_graph(self, graph: Usd.Prim, x, y, b, m) -> None:
        """Delete the given logic graph."""
        if b != 0:
            return
        omni.kit.commands.execute("DeletePrimsCommand", paths=[str(graph.GetPath())])
        # Rebuild the UI to reflect the changes in the existing logic graphs
        if self._dynamic_content_frame:
            self._dynamic_content_frame.rebuild()

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
        self._event_manager = None
        self._property_delegate = None
        self._property_model = None
        self._property_widget = None
        self._property_frame = None
        self._dynamic_content_frame = None
        self._root_frame = None

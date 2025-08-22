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

import asyncio
from typing import Dict, List, Optional, Union

import carb
import omni.kit
import omni.ui as ui
import omni.usd
from lightspeed.common.constants import PARTICLE_PRIMVAR_PREFIX, PARTICLE_SCHEMA_NAME
from lightspeed.trex.schemas.utils import get_schema_prim as _get_schema_prim
from lightspeed.trex.utils.common.prim_utils import get_prototype
from omni.flux.property_widget_builder.model.usd import DisableAllListenersBlock as _USDDisableAllListenersBlock
from omni.flux.property_widget_builder.model.usd import USDAttributeItem as _USDAttributeItem
from omni.flux.property_widget_builder.model.usd import USDAttrListItem as _USDAttrListItem
from omni.flux.property_widget_builder.model.usd import USDDelegate as _USDPropertyDelegate
from omni.flux.property_widget_builder.model.usd import USDModel as _USDPropertyModel
from omni.flux.property_widget_builder.model.usd import USDPropertyWidget as _PropertyWidget
from omni.flux.property_widget_builder.model.usd import get_usd_listener_instance as _get_usd_listener_instance
from omni.flux.property_widget_builder.widget import FieldBuilder as _FieldBuilder
from omni.flux.property_widget_builder.widget import ItemGroup as _ItemGroup
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from pxr import Sdf, Usd

from .particle_lookup_table import get_particle_lookup_table as _get_particle_lookup_table

PARTICLE_ATTR_GROUP_ORDER = ("Spawn", "Target", "Visual", "Collision", "Simulation")
PARTICLE_ATTR_GROUP_FALLBACK = "General"


class ParticleSystemPropertyWidget:
    """
    Properties panel for RemixParticleSystem prim types.
    Shows and allows editing of particle system attributes.
    """

    def __init__(
        self,
        context_name: str,
        tree_column_widths: Optional[List[ui.Length]] = None,
        columns_resizable: bool = False,
        right_aligned_labels: bool = True,
        lookup_table: Optional[Dict[str, Dict[str, str]]] = None,
        field_builders: list[_FieldBuilder] | None = None,
    ):
        """
        Args:
            context_name (str): USD context name
            tree_column_widths (Optional[List[ui.Length]]): Column widths for the tree
            columns_resizable (bool): Whether columns are resizable
            right_aligned_labels (bool): Whether labels are right aligned
            lookup_table (Optional[Dict[str, Dict[str, str]]]): Table for custom display names and groups
            field_builders (List[_FieldBuilder]): Custom field builders for specific attribute types
        """

        self._default_attr = {
            "_columns_resizable": None,
            "_context": None,
            "_context_name": None,
            "_lookup_table": None,
            "_paths": None,
            "_property_delegate": None,
            "_property_model": None,
            "_property_widget": None,
            "_right_aligned_labels": None,
            "_none_frame": None,
            "_root_frame": None,
            "_tree_column_widths": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self.__refresh_done = _Event()
        self._refresh_task = None

        self._context_name = context_name
        self._context = omni.usd.get_context(context_name)
        self._tree_column_widths = tree_column_widths
        self._columns_resizable = columns_resizable
        self._right_aligned_labels = right_aligned_labels

        self.__usd_listener_instance = _get_usd_listener_instance()

        self._paths = []
        if not lookup_table:
            lookup_table = _get_particle_lookup_table()
        self._lookup_table = lookup_table

        self.__create_ui(field_builders=field_builders)

    def _refresh_done(self):
        """Call the event object that has the list of functions"""
        self.__refresh_done()

    def subscribe_refresh_done(self, callback):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__refresh_done, callback)

    @property
    def field_builders(self):
        if self._property_delegate is None:
            raise AttributeError("Need to run __create_ui first.")
        return self._property_delegate.field_builders

    def __create_ui(self, field_builders: list[_FieldBuilder] | None = None):
        """Create the UI components"""
        self._property_model = _USDPropertyModel(self._context_name)
        self._property_delegate = _USDPropertyDelegate(
            field_builders=field_builders, right_aligned_labels=self._right_aligned_labels
        )
        with ui.ZStack():
            self._none_frame = ui.Frame(visible=True)
            with self._none_frame:
                with ui.VStack():
                    with ui.HStack(height=ui.Pixel(24), spacing=ui.Pixel(8)):
                        ui.Spacer(height=0)
                        with ui.VStack(width=0):
                            ui.Spacer()
                            ui.Label("None", name="PropertiesWidgetLabel")
                            ui.Spacer()
                        ui.Spacer(height=0)
                    ui.Spacer(height=ui.Pixel(8))

            self._root_frame = ui.Frame(visible=False)
            with self._root_frame:
                self._property_widget = _PropertyWidget(
                    self._context_name,
                    model=self._property_model,
                    delegate=self._property_delegate,
                    tree_column_widths=self._tree_column_widths,
                    columns_resizable=self._columns_resizable,
                    refresh_callback=self.refresh,
                )

    def refresh(self, paths: Optional[List[Union[str, "Sdf.Path"]]] = None):
        """
        Refresh the panel with the given prim paths

        Args:
            paths: the USD prim paths to use
        """
        if self._refresh_task is not None:
            self._refresh_task.cancel()
        self._refresh_task = asyncio.ensure_future(self._deferred_refresh(paths))

    @omni.usd.handle_exception
    async def _deferred_refresh(self, paths: Optional[List[Union[str, "Sdf.Path"]]] = None):
        """
        Deferred refresh to handle USD updates properly

        Args:
            paths: the paths of particle system prims
        """
        if paths is not None:
            self._paths = paths

        # Wait 1 frame to make sure the USD is up-to-date
        await omni.kit.app.get_app().next_update_async()

        if self.__usd_listener_instance and self._property_model:  # noqa PLE0203
            self.__usd_listener_instance.remove_model(self._property_model)  # noqa PLE0203

        schema_layer, schema_prim = _get_schema_prim(PARTICLE_SCHEMA_NAME)
        if not schema_layer or not schema_prim:
            # Early return to prevent further processing with invalid schema
            carb.log_error("Schema layer or prim not found")
            return

        stage = self._context.get_stage()
        items = []
        valid_paths = []

        if stage is not None:  # noqa PLR1702
            prims = [
                prototype_prim
                for path in self._paths
                if (prototype_prim := get_prototype(stage.GetPrimAtPath(path)))  # Filtering Nones out
            ]

            # Group attributes by name across all selected prims
            attr_added: dict[str, list[tuple[Usd.Prim, Usd.Attribute]]] = {}

            with _USDDisableAllListenersBlock(self.__usd_listener_instance):
                for prim in prims:
                    if not prim.IsValid():
                        continue

                    if not prim.HasAPI(PARTICLE_SCHEMA_NAME):
                        continue

                    valid_paths.append(prim.GetPath())

                    attrs = prim.GetAttributes()
                    for attr in attrs:
                        attr_name = attr.GetName()

                        if not attr_name.startswith("primvars:particle"):
                            continue

                        # Group attributes by name across all prims
                        attr_added.setdefault(attr_name, []).append((prim, attr))

            # Group items by category for better organization
            group_items = {}
            num_prims = len([p for p in prims if p.IsValid() and p.HasAPI(PARTICLE_SCHEMA_NAME)])

            # Sort attribute names for better organization (min/max pairs together, then alphabetical)
            sorted_attr_names = self._sort_particle_attributes(list(attr_added.keys()))

            # Create attribute items and collect them by group
            for attr_name in sorted_attr_names:
                prims_and_attrs = attr_added[attr_name]
                # Only allow editing common attributes (attributes that exist on all selected prims)
                if num_prims != len(prims_and_attrs):
                    # Skip attribute because not all prims have it
                    continue

                # Get all attribute paths for this attribute name across all prims
                attributes = [prim.GetAttribute(attr.GetName()) for prim, attr in prims_and_attrs]
                attribute_paths = [attr.GetPath() for attr in attributes]

                # Get display info from lookup table
                display_info = self._lookup_table.get(attr_name, {})
                display_name = display_info.get("name", attr_name)
                group_name = display_info.get("group", PARTICLE_ATTR_GROUP_FALLBACK)

                # Get the attribute from the schema prim
                default_value = None
                options: list[str] | None = None
                if schema_prim:
                    schema_attr: Sdf.AttributeSpec = schema_prim.properties.get(attr_name)
                    if schema_attr:
                        options = schema_attr.allowedTokens
                        default_value = schema_attr.default

                # Create an attribute item to manage all attribute paths
                if options:
                    attr_item = _USDAttrListItem(
                        self._context_name,
                        attribute_paths,
                        default_value=default_value,
                        display_attr_names=[display_name],
                        display_attr_names_tooltip=[display_info.get("tooltip", "")],
                        options=options,
                        read_only=False,
                    )
                else:
                    attr_item = _USDAttributeItem(
                        self._context_name,
                        attribute_paths,
                        display_attr_names=[display_name],
                        display_attr_names_tooltip=[display_info.get("tooltip", "")],
                        read_only=False,
                    )

                # Collect items by group (but don't add to items list yet)
                if group_name not in group_items:
                    group_items[group_name] = _ItemGroup(group_name)
                group_items[group_name].children.append(attr_item)

            # Add groups to items in the specified order
            for group_name in PARTICLE_ATTR_GROUP_ORDER:
                if group_name in group_items:
                    items.append(group_items[group_name])

            # Add any remaining groups not in the predefined order (for future extensibility)
            for group_name, group in group_items.items():
                if group_name not in PARTICLE_ATTR_GROUP_ORDER:
                    items.append(group)

        if valid_paths:
            self._none_frame.visible = False
            self._root_frame.visible = True
        else:
            self._none_frame.visible = True
            self._root_frame.visible = False

        self._property_model.set_prim_paths(valid_paths)
        self._property_model.set_items(items)
        self.__usd_listener_instance.add_model(self._property_model)

        self._refresh_done()

    def _sort_particle_attributes(self, attr_names: list[str]) -> list[str]:
        # Find all min/max pairs dynamically
        min_max_pairs = self._find_min_max_pairs(attr_names)

        # Create groups: paired attributes and standalone attributes
        paired_attrs = []
        standalone_attrs = []
        processed_attrs = set()

        for attr_name in attr_names:
            if attr_name in processed_attrs:
                continue

            base_name = self._get_base_name(attr_name)

            # Check if this is a min attribute with a corresponding max
            if base_name in min_max_pairs:
                max_base_name = min_max_pairs[base_name]
                max_attr_name = f"{PARTICLE_PRIMVAR_PREFIX}{max_base_name}"
                if max_attr_name in attr_names:
                    # Add min first, then max
                    core_name = base_name[3:]  # Remove "min" prefix for sorting
                    paired_attrs.append((core_name, attr_name, max_attr_name))
                    processed_attrs.add(attr_name)
                    processed_attrs.add(max_attr_name)
                    continue

            # Check if this is a max attribute with a corresponding min
            if base_name.startswith("max"):
                core_name = base_name[3:]  # Remove "max" prefix
                min_base_name = f"min{core_name}"
                min_attr_name = f"{PARTICLE_PRIMVAR_PREFIX}{min_base_name}"
                if min_attr_name in attr_names and min_attr_name not in processed_attrs:
                    # Add min first, then max
                    paired_attrs.append((core_name, min_attr_name, attr_name))
                    processed_attrs.add(min_attr_name)
                    processed_attrs.add(attr_name)
                    continue

            # Standalone attribute
            if attr_name not in processed_attrs:
                standalone_attrs.append(attr_name)
                processed_attrs.add(attr_name)

        # Sort paired attributes by the core name (e.g., "ParticleSize", "RotationSpeed")
        paired_attrs.sort(key=lambda x: x[0])

        # Sort standalone attributes alphabetically by base name
        standalone_attrs.sort(key=self._get_base_name)

        # Combine results: paired attributes first (min, max), then standalone
        result = []
        for _, min_attr, max_attr in paired_attrs:
            result.extend([min_attr, max_attr])
        result.extend(standalone_attrs)

        return result

    def _get_base_name(self, attr_name_: str) -> str:
        if attr_name_.startswith(PARTICLE_PRIMVAR_PREFIX):
            return attr_name_[len(PARTICLE_PRIMVAR_PREFIX) :]  # noqa format/lint incompatible
        return attr_name_

    # Dynamically find min/max pairs by analyzing attribute names
    def _find_min_max_pairs(self, names: list[str]) -> dict[str, str]:
        pairs = {}
        base_names = [self._get_base_name(name) for name in names]

        for base_name in base_names:
            if base_name.startswith("min"):
                # Extract the core name (e.g., "ParticleSize" from "minParticleSize")
                core_name = base_name[3:]  # Remove "min" prefix
                max_name = f"max{core_name}"

                # Check if corresponding max exists
                if max_name in base_names:
                    pairs[base_name] = max_name

        return pairs

    @property
    def property_model(self):
        return self._property_model

    def show(self, value):
        """
        Show the panel or not

        Args:
            value: visible or not
        """
        if self._property_widget is not None:
            self._property_widget.enable_listeners(value)
        self._root_frame.visible = value
        if not value and self.__usd_listener_instance and self._property_model:
            self.__usd_listener_instance.remove_model(self._property_model)
        if not value:
            self._property_delegate.reset()

    def destroy(self):
        """Clean up listeners and UI Widgets"""
        if self._root_frame:
            self._root_frame.clear()
        if self.__usd_listener_instance and self._property_model:
            self.__usd_listener_instance.remove_model(self._property_model)
        self.__usd_listener_instance = None
        self.__refresh_done = None
        self._refresh_task = None
        _reset_default_attrs(self)

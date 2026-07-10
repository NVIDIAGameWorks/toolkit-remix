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

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from typing import Any

import carb
import omni.kit
import omni.ui as ui
import omni.usd
from lightspeed.common.constants import PARTICLE_PRIMVAR_PREFIX, PARTICLE_SCHEMA_NAME
from lightspeed.trex.schemas.utils import get_schema_prim as _get_schema_prim
from omni.flux.property_widget_builder.model.usd import BuildLayerTransferMenu as _BuildLayerTransferMenu
from omni.flux.property_widget_builder.model.usd import USDAttributeItem as _USDAttributeItem
from omni.flux.property_widget_builder.model.usd import USDAttrListItem as _USDAttrListItem
from omni.flux.property_widget_builder.model.usd import USDDelegate as _USDPropertyDelegate
from omni.flux.property_widget_builder.model.usd import USDLogicalGroupOutletItem as _USDLogicalGroupOutletItem
from omni.flux.property_widget_builder.model.usd import USDModel as _USDPropertyModel
from omni.flux.property_widget_builder.model.usd import USDPropertyWidget as _PropertyWidget
from omni.flux.property_widget_builder.model.usd import get_usd_listener_instance as _get_usd_listener_instance
from omni.flux.property_widget_builder.model.usd.logical_group_constants import (
    CURVE_LOGICAL_GROUP_DEFINITION as _CURVE_LOGICAL_GROUP_DEFINITION,
)
from omni.flux.property_widget_builder.model.usd.logical_row import LogicalGroupDefinition as _LogicalGroupDefinition
from omni.flux.property_widget_builder.widget import FieldBuilder as _FieldBuilder
from omni.flux.property_widget_builder.widget import ItemGroup as _ItemGroup
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common.prims import unique_prim_sequence as _unique_prim_sequence
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from pxr import Sdf, Usd

from .particle_edit_groups import PARTICLE_CURVE_LOOKUP as _PARTICLE_CURVE_LOOKUP
from .particle_edit_groups import PARTICLE_EDIT_GROUPS as _PARTICLE_EDIT_GROUPS
from .particle_edit_groups import PARTICLE_LEGACY_ANIMATION_MAPPINGS as _PARTICLE_LEGACY_ANIMATION_MAPPINGS
from .particle_lookup_table import get_particle_lookup_table as _get_particle_lookup_table
from .bounds_adapter import ParticleBoundsAdapter as _ParticleBoundsAdapter
from .legacy_support_helper import seed_current_animated_attrs_from_legacy as _seed_current_animated_attrs_from_legacy


PARTICLE_ATTR_GROUP_FALLBACK = "Extra"
PARTICLE_ATTR_GROUP_ORDER = ("General", "Spawn", "Target", "Visual", "Collision", "Simulation")
_PreOpenCallback = Callable[[Callable[[], None]], None]
_CURVE_VALUES_SUFFIX = ":values"
_PARTICLE_CURVE_OPTIONAL_SUFFIXES = frozenset({"preInfinity", "postInfinity"})
_PARTICLE_CURVE_REQUIRED_SUFFIXES = frozenset(_CURVE_LOGICAL_GROUP_DEFINITION.suffixes).difference(
    _PARTICLE_CURVE_OPTIONAL_SUFFIXES
)


def _get_schema_attr_display_group(schema_attr: Sdf.AttributeSpec | None) -> str | None:
    """Return a non-empty schema display group, if one is authored.

    Args:
        schema_attr: Schema attribute to inspect.

    Returns:
        Trimmed display group, or ``None``.
    """
    if schema_attr is None:
        return None
    display_group = schema_attr.GetInfo(Sdf.AttributeSpec.DisplayGroupKey)
    if isinstance(display_group, str):
        display_group = display_group.strip()
        if display_group:
            return display_group
    return None


def _resolve_edit_group_outlet_group(schema_prim: Sdf.PrimSpec, edit_group_layout: dict[str, Any]) -> str | None:
    """Resolve the UI group for a particle curve outlet from schema metadata.

    Args:
        schema_prim: Generated particle schema prim.
        edit_group_layout: Particle edit-group layout definition.

    Returns:
        Display group for the outlet, fallback group, or ``None`` when the layout has no curves.
    """
    curve_map = edit_group_layout.get("curve_map")
    if not curve_map:
        return None
    for curve_id in curve_map:
        schema_attr = schema_prim.properties.get(f"{curve_id}{_CURVE_VALUES_SUFFIX}")
        display_group = _get_schema_attr_display_group(schema_attr)
        if display_group:
            return display_group
    return PARTICLE_ATTR_GROUP_FALLBACK


def _resolve_curve_logical_group_definition(
    schema_prim: Sdf.PrimSpec, edit_group_layout: dict[str, Any]
) -> _LogicalGroupDefinition:
    """Resolve the curve suffix set supported by the generated particle schema.

    Particle curves must have the required scalar curve suffixes. Optional full-FCurve suffixes such as
    infinity mode are included only when the schema declares them for every curve in the edit group.

    Args:
        schema_prim: Generated particle schema prim.
        edit_group_layout: Particle edit-group layout definition.

    Returns:
        Logical group definition matching the schema-supported suffixes.

    Raises:
        ValueError: If the edit group is missing curve entries or required curve schema attrs.
    """
    curve_map = edit_group_layout.get("curve_map")
    if not curve_map:
        message = "Particle curve edit group is missing curve_map entries."
        raise ValueError(message)

    missing_attrs = []
    for curve_id in curve_map:
        missing_attrs.extend(
            f"{curve_id}:{suffix}"
            for suffix in _PARTICLE_CURVE_REQUIRED_SUFFIXES
            if f"{curve_id}:{suffix}" not in schema_prim.properties
        )
    if missing_attrs:
        message = f"Particle curve edit group is missing required curve schema attrs: {missing_attrs}"
        raise ValueError(message)

    schema_suffixes = {
        suffix
        for suffix in _CURVE_LOGICAL_GROUP_DEFINITION.suffixes
        if all(f"{curve_id}:{suffix}" in schema_prim.properties for curve_id in curve_map)
    }
    if schema_suffixes == set(_CURVE_LOGICAL_GROUP_DEFINITION.suffixes):
        return _CURVE_LOGICAL_GROUP_DEFINITION
    return _LogicalGroupDefinition(suffixes=tuple(sorted(schema_suffixes)), widget_kind="curve")


def _add_edit_group_outlets(
    group_items: dict[str, _ItemGroup],
    schema_prim: Sdf.PrimSpec,
    edit_groups: Iterable[dict[str, Any]],
    context_name: str,
    target_paths: list[str],
    pre_open_callback_builder: Callable[[list[str], list[str]], _PreOpenCallback],
) -> None:
    """Append valid particle edit-group outlet rows to grouped property items.

    Args:
        group_items: Mutable map of display group names to item groups.
        schema_prim: Generated particle schema prim.
        edit_groups: Particle edit-group layout definitions.
        context_name: USD context name for the outlet rows.
        target_paths: Selected particle prim paths.
        pre_open_callback_builder: Callback factory for legacy value seeding before editor open.
    """
    for group in edit_groups:
        outlet_group = _resolve_edit_group_outlet_group(schema_prim, group)
        if outlet_group is None:
            continue
        try:
            logical_group_definition = _resolve_curve_logical_group_definition(schema_prim, group)
        except ValueError as exc:
            carb.log_error(str(exc))
            continue
        if outlet_group not in group_items:
            group_items[outlet_group] = _ItemGroup(outlet_group)
        outlet = _USDLogicalGroupOutletItem(
            edit_group_layout=group,
            context_name=context_name,
            target_paths=target_paths,
        )
        outlet.logical_group_definition = logical_group_definition
        # Edit group outlets are curve-only today. Gradient-based outlets need their own
        # seeding list if they are added to PARTICLE_EDIT_GROUPS later.
        animated_attr_names = list(group.get("curve_map", {}))
        outlet.pre_open_callback = pre_open_callback_builder(
            animated_attr_names,
            target_paths,
        )
        outlet.parent = group_items[outlet_group]


class ParticleSystemPropertyWidget:
    """
    Properties panel for RemixParticleSystem prim types.
    Shows and allows editing of particle system attributes.
    """

    def __init__(
        self,
        context_name: str,
        tree_column_widths: list[ui.Length] | None = None,
        columns_resizable: bool = False,
        right_aligned_labels: bool = True,
        lookup_table: dict[str, dict[str, str]] | None = None,
        field_builders: list[_FieldBuilder] | None = None,
        layer_transfer_menu_fn: _BuildLayerTransferMenu | None = None,
    ):
        """
        Args:
            context_name (str): USD context name
            tree_column_widths (list[ui.Length] | None): Column widths for the tree
            columns_resizable (bool): Whether columns are resizable
            right_aligned_labels (bool): Whether labels are right aligned
            lookup_table (dict[str, dict[str, str]] | None): Table for custom display names and groups
            field_builders (List[_FieldBuilder]): Custom field builders for specific attribute types
            layer_transfer_menu_fn: Callback that adds property-layer transfer actions to property row menus.
        """

        self._default_attr = {
            "_columns_resizable": None,
            "_context": None,
            "_context_name": None,
            "_create_button": None,
            "_create_frame": None,
            "_lookup_table": None,
            "_paths": None,
            "_valid_target_paths": None,
            "_property_delegate": None,
            "_property_frame": None,
            "_property_model": None,
            "_property_widget": None,
            "_right_aligned_labels": None,
            "_layer_transfer_menu_fn": None,
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
        self._layer_transfer_menu_fn = layer_transfer_menu_fn

        self.__usd_listener_instance = _get_usd_listener_instance()

        self._paths = []
        self._valid_target_paths = []

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
        """Create the UI components once - PropertyWidget is reused across refreshes to preserve expansion state."""
        self._property_model = _USDPropertyModel(self._context_name)
        self._property_delegate = _USDPropertyDelegate(
            field_builders=field_builders,
            right_aligned_labels=self._right_aligned_labels,
            layer_transfer_menu_fn=self._layer_transfer_menu_fn,
        )
        self._root_frame = ui.Frame()
        with self._root_frame:
            with ui.ZStack():
                # Frame for when particle system exists - always created, visibility toggled
                self._property_frame = ui.Frame(visible=False, identifier="frame_particle_widget")
                with self._property_frame:
                    self._property_widget = _PropertyWidget(
                        self._context_name,
                        model=self._property_model,
                        delegate=self._property_delegate,
                        tree_column_widths=self._tree_column_widths,
                        columns_resizable=self._columns_resizable,
                        refresh_callback=self.refresh,
                    )

                # Frame for when no particle system exists - always created, visibility toggled
                self._create_frame = ui.Frame(visible=True, identifier="frame_particle_create")
                with self._create_frame:
                    with ui.VStack(height=0):
                        with ui.VStack(height=ui.Pixel(24)):
                            ui.Spacer()
                            self._create_button = ui.Button(
                                "Create a Particle System",
                                clicked_fn=lambda: self._create_particle_systems(self._valid_target_paths),
                                tooltip="Select a material prim or mesh prim to create a particle system.",
                                enabled=False,
                                identifier="create_particle_system_button",
                            )
                            ui.Spacer()
                        ui.Spacer(height=ui.Pixel(8))

    def _update_create_button_state(self):
        """Update the create button tooltip and enabled state based on valid_target_paths."""
        if self._create_button:
            if self._valid_target_paths:
                self._create_button.tooltip = "Create a particle system on the selected prim"
                self._create_button.enabled = True
            else:
                self._create_button.tooltip = (
                    "Select a material prim or mesh prim to create a particle system.\n\n"
                    "NOTE: Instance prims are also supported but the particle system will be created on the "
                    "associated mesh prim."
                )
                self._create_button.enabled = False

    def refresh(
        self,
        paths: list[str | Sdf.Path] | None = None,
        valid_target_paths: list[str | Sdf.Path] | None = None,
    ):
        """Refresh the panel for particle prims or create-capable targets.

        Args:
            paths: USD prim paths for selected particle systems to display.
            valid_target_paths: USD prim paths that support particle creation
                when no particle systems are currently selected.
        """
        if self._refresh_task is not None:
            self._refresh_task.cancel()
        self._refresh_task = asyncio.ensure_future(self._deferred_refresh(paths, valid_target_paths))

    @omni.usd.handle_exception
    async def _deferred_refresh(
        self,
        paths: list[str | Sdf.Path] | None = None,
        valid_target_paths: list[str | Sdf.Path] | None = None,
    ) -> None:
        """Refresh the panel asynchronously after USD selection updates settle.

        Args:
            paths: USD prim paths for selected particle systems to display.
            valid_target_paths: USD prim paths that support particle creation
                when no particle systems are currently selected.
        """
        if paths is not None:
            self._paths = paths
        if valid_target_paths is not None:
            self._valid_target_paths = valid_target_paths

        # Wait 1 frame to make sure the USD is up-to-date
        await omni.kit.app.get_app().next_update_async()

        if self.__usd_listener_instance and self._property_model:
            self.__usd_listener_instance.remove_model(self._property_model)

        schema_layer, schema_prim = _get_schema_prim(PARTICLE_SCHEMA_NAME)
        if not schema_layer or not schema_prim:
            # Early return to prevent further processing with invalid schema
            carb.log_error("Schema layer or prim not found")
            return

        stage = self._context.get_stage()
        items = []
        valid_paths = []

        if stage is not None:
            prims = _unique_prim_sequence(
                [stage.GetPrimAtPath(path) for path in self._paths],
                prototypes_only=True,
            )

            # Group attributes by name across all selected prims
            attr_added: dict[str, list[tuple[Usd.Prim, Usd.Attribute]]] = {}
            valid_paths_by_key: dict[str, Sdf.Path] = {}

            for prim in prims:
                if not prim.IsValid():
                    continue

                if not prim.HasAPI(PARTICLE_SCHEMA_NAME):
                    continue

                valid_paths_by_key.setdefault(str(prim.GetPath()), prim.GetPath())

                attrs = prim.GetAttributes()
                for attr in attrs:
                    attr_name = attr.GetName()

                    if not attr_name.startswith("primvars:particle"):
                        continue

                    # Group attributes by name across all prims
                    attr_added.setdefault(attr_name, []).append((prim, attr))

            # Group items by category for better organization
            group_items = {}
            valid_paths = list(valid_paths_by_key.values())
            num_prims = len(valid_paths)

            # Create edit group outlet buttons first so curve outlets (Particle Size, Velocity, etc.)
            # render at the top of their schema-defined group, before the regular per-attribute rows.
            if valid_paths:
                target_paths = [str(path) for path in valid_paths]
                _add_edit_group_outlets(
                    group_items=group_items,
                    schema_prim=schema_prim,
                    edit_groups=_PARTICLE_EDIT_GROUPS.values(),
                    context_name=self._context_name,
                    target_paths=target_paths,
                    pre_open_callback_builder=self._build_pre_open_callback,
                )

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
                if attr_name in _PARTICLE_LEGACY_ANIMATION_MAPPINGS:
                    continue
                curve_id = self._extract_curve_id(attr_name)
                if curve_id in _PARTICLE_CURVE_LOOKUP:
                    continue

                # Get the attribute from the schema prim
                default_value = None
                options: list[str] | None = None
                schema_attr: Sdf.AttributeSpec | None = None
                if schema_prim:
                    schema_attr = schema_prim.properties.get(attr_name)
                    if schema_attr:
                        options = schema_attr.allowedTokens
                        default_value = schema_attr.default
                raw_bounds_metadata = self._collect_particle_bounds_metadata(attributes, schema_attr)
                bounds_adapter = _ParticleBoundsAdapter(raw_bounds_metadata)

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
                        bounds_adapter=bounds_adapter,
                    )

                if attr_name.endswith(":values"):
                    animated_attr_name = attr_name[: -len(":values")]
                    attr_item.pre_open_callback = self._build_pre_open_callback(
                        animated_attr_name,
                        [str(attr.GetPrim().GetPath()) for attr in attributes],
                    )

                # Collect items by group (but don't add to items list yet)
                if group_name not in group_items:
                    group_items[group_name] = _ItemGroup(group_name)
                attr_item.parent = group_items[group_name]

            # Add groups to items in the specified order
            items.extend(
                group_items[group_name] for group_name in PARTICLE_ATTR_GROUP_ORDER if group_name in group_items
            )

            # Add any remaining groups not in the predefined order (for future extensibility)
            items.extend(
                group for group_name, group in group_items.items() if group_name not in PARTICLE_ATTR_GROUP_ORDER
            )

        self._property_model.set_prim_paths(valid_paths)
        self._property_model.set_items(items)
        self.__usd_listener_instance.add_model(self._property_model)

        # Toggle visibility between property widget and create button
        has_particles = bool(valid_paths)
        self._property_frame.visible = has_particles
        self._create_frame.visible = not has_particles
        self._update_create_button_state()

        self._refresh_done()

    @staticmethod
    def _collect_particle_bounds_metadata(
        attributes: list[Usd.Attribute],
        schema_attr: Sdf.AttributeSpec | None,
    ) -> object | None:
        """Pick the metadata payload used for particle bounds normalization.

        Attribute customData is preferred so per-prim overrides are honored.
        Schema customData is used only as a fallback.

        Args:
            attributes: Candidate USD attributes for the current panel item.
            schema_attr: Optional schema attribute spec fallback source.

        Returns:
            First available attr ``customData`` payload, otherwise schema
            ``customData``, otherwise ``None``.
        """
        for attr in attributes:
            custom_data = attr.GetMetadata("customData")
            if custom_data is not None:
                return custom_data
        if schema_attr:
            return schema_attr.customData or None
        return None

    def _build_pre_open_callback(
        self,
        animated_attr_names: str | list[str] | None,
        target_paths: list[str],
    ) -> _PreOpenCallback:
        """Build a curve-editor pre-open hook for legacy animated values.

        The returned callback seeds the current animated particle attributes
        from legacy values before opening the editor. ``None`` intentionally
        skips seeding while still opening the editor, which lets callers share
        the same hook shape for controls without legacy animated data.

        Args:
            animated_attr_names: Animated particle attribute name or names to
                seed from legacy values, or ``None`` when no legacy seeding is
                needed.
            target_paths: Ordered selected particle target prim paths to seed.

        Returns:
            Callback that performs any legacy seeding and then opens the editor.
        """

        def _callback(open_editor_fn: Callable[[], None]) -> None:
            """Seed legacy animated attrs, refresh the property model, then open the editor.

            Args:
                open_editor_fn: Final editor-opening callback to invoke after seeding.
            """
            if _seed_current_animated_attrs_from_legacy(animated_attr_names, self._context_name, target_paths):
                self._property_model.refresh()
            open_editor_fn()

        return _callback

    @staticmethod
    def _extract_curve_id(attr_name: str) -> str | None:
        """Strip the curve suffix (e.g. :values, :times) from an attribute name.

        Returns the curve_id prefix, or None if the attr is not a curve suffix.
        """
        parts = attr_name.rsplit(":", 1)
        if len(parts) == 2 and parts[1] in {
            "times",
            "values",
            "inTangentTimes",
            "inTangentValues",
            "inTangentTypes",
            "outTangentTimes",
            "outTangentValues",
            "outTangentTypes",
            "preInfinity",
            "postInfinity",
            "tangentBrokens",
        }:
            return parts[0]
        return None

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
            return attr_name_[len(PARTICLE_PRIMVAR_PREFIX) :]
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

    def _create_particle_systems(self, prim_paths: list[str]):
        with omni.kit.undo.group():
            for prim_path in prim_paths:
                omni.kit.commands.execute(
                    "CreateParticleSystemCommand", prim=self._context.get_stage().GetPrimAtPath(prim_path)
                )

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
        if self._refresh_task:
            self._refresh_task.cancel()
        if self._root_frame:
            self._root_frame.clear()
        if self.__usd_listener_instance and self._property_model:
            self.__usd_listener_instance.remove_model(self._property_model)
        self.__usd_listener_instance = None
        self.__refresh_done = None
        self._refresh_task = None
        _reset_default_attrs(self)

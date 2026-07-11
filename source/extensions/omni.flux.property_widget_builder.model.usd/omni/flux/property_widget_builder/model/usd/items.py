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

from __future__ import annotations

import abc
import asyncio
import collections
import dataclasses
from collections.abc import Callable, Iterable, Sequence
from functools import partial
from typing import Any, Protocol, cast

import omni.kit
import omni.kit.commands
import omni.kit.undo
import omni.usd
from omni.flux.property_widget_builder.widget import Item as _Item
from omni.flux.property_widget_builder.widget.tree.item_model import ItemGroupNameModel as _ItemGroupNameModel
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common.types import ScalarValue as _ScalarValue
from omni.kit.window.popup_dialog import MessageDialog as _MessageDialog
from pxr import Sdf, Usd, UsdGeom

from .item_model.attr_list_model_value import UsdListModelAttrValueModel as _UsdListModelAttrValueModel
from .item_model.attr_list_model_value import VirtualUsdListModelAttrValueModel as _VirtualUsdListModelAttrValueModel
from .item_model.attr_name import UsdAttributeNameModel as _UsdAttributeNameModel
from .item_model.attr_value import UsdAttributeValueModel as _UsdAttributeValueModel
from .item_model.attr_value import VirtualUsdAttributeValueModel as _VirtualUsdAttributeValueModel
from .item_model.metadata_list_model_value import UsdListModelAttrMetadataValueModel as _UsdAttributeMetadataValueModel
from .logical_group_constants import CURVE_LOGICAL_GROUP_DEFINITION
from .logical_row import LogicalGroupDefinition as _LogicalGroupDefinition
from .logical_row import get_grouped_item_value_signature as _get_grouped_item_value_signature
from .logical_row import LogicalRowState as _LogicalRowState
from .mapping import CHANNEL_ELEMENT_BUILDER_TABLE
from .mapping import DEFAULT_PRECISION as _DEFAULT_PRECISION
from .mapping import OPS_ATTR_PRECISION_TABLE as _OPS_ATTR_PRECISION_TABLE

from .bounds_adapter import BoundsAdapter as _BoundsAdapter
from .utils import delete_all_overrides as _delete_all_overrides
from .utils import delete_layer_override as _delete_layer_override
from .utils import get_default_attribute_value as _get_default_attribute_value
from .utils import get_metadata as _get_metadata
from .utils import get_type_name as _get_type_name
from .utils import is_item_overriden as _is_item_overriden


class _AttributeBackedValueModel(Protocol):
    """Value model contract for rows backed by USD attributes."""

    @property
    def attributes(self) -> list[Usd.Attribute] | None:
        """Return USD attributes represented by the value model."""
        ...


class _LogicalRowApiMixin:
    """Shared row API for explicit logical-row behavior."""

    _include_self_value_models_when_unowned = False
    logical_group_items: list[Any]
    pre_open_callback: Callable[[Callable[[], None]], None] | None

    def get_owned_value_models(self) -> list[Any]:
        """Return value models owned by this row and its logical companions."""
        owned_items = self.logical_group_items
        if not owned_items and self._include_self_value_models_when_unowned:
            owned_items = [self]

        value_models = []
        for owned_item in owned_items:
            value_models.extend(owned_item.value_models)
        return value_models

    def run_pre_open_callback(self, action: Callable[[], None]) -> None:
        """Run the row pre-open callback when present, otherwise run the action directly."""
        if self.pre_open_callback is not None:
            self.pre_open_callback(action)
            return
        action()

    def get_property_stack(self) -> list[Sdf.PropertySpec]:
        """Return unique authored property specs for every property owned by this row.

        Returns:
            Composed property specs without duplicate layer/path pairs.
        """
        property_stack = []
        property_stack_keys = set()
        for prop in self.get_owned_properties():
            if not prop or not prop.IsValid():
                continue
            for stack_item in prop.GetPropertyStack(Usd.TimeCode.Default()):
                key = (stack_item.layer.identifier, stack_item.path)
                if key in property_stack_keys:
                    continue
                property_stack_keys.add(key)
                property_stack.append(stack_item)
        return property_stack

    def get_layer_override_layers(self, layer_identifiers: Iterable[str]) -> list[Sdf.Layer]:
        """Return logical override layers for authored property specs owned by this row.

        Args:
            layer_identifiers: Layer identifiers allowed to appear in the result.

        Returns:
            Unique layers, one per allowed layer identifier, with authored property specs for this row.
        """
        layer_identifiers = set(layer_identifiers)
        layers = []
        seen = set()
        for stack_item in self.get_property_stack():
            layer_identifier = stack_item.layer.identifier
            if layer_identifier not in layer_identifiers or layer_identifier in seen:
                continue
            seen.add(layer_identifier)
            layers.append(stack_item.layer)
        return layers


def _get_value_model_attributes(value_models: Iterable[_AttributeBackedValueModel]) -> list[Usd.Attribute]:
    """Return unique valid USD attributes exposed by value models.

    Args:
        value_models: Attribute-backed value models.

    Returns:
        Ordered unique valid USD attributes.
    """
    attributes = []
    seen = set()
    for value_model in value_models:
        for attribute in value_model.attributes or []:
            if not attribute:
                continue
            path = attribute.GetPath()
            if path in seen:
                continue
            seen.add(path)
            attributes.append(attribute)
    return attributes


def _get_logical_group_attributes(
    context_name: str,
    target_paths: list[str],
    base_names: Iterable[str],
    definition: _LogicalGroupDefinition,
) -> list[Usd.Attribute]:
    """Return valid attrs for logical groups across all target prims.

    Args:
        context_name: USD context containing the target prims.
        target_paths: Prim paths to inspect.
        base_names: Logical group base names.
        definition: Suffix definition for each logical group.

    Returns:
        Valid USD attributes found for every requested group attr.
    """
    stage = omni.usd.get_context(context_name).get_stage()
    attributes = []
    if stage is None:
        return attributes
    for prim_path in target_paths:
        prim = stage.GetPrimAtPath(prim_path)
        if not prim or not prim.IsValid():
            continue
        for base_name in base_names:
            for attr_name in definition.get_attr_names(base_name):
                attr = prim.GetAttribute(attr_name)
                if attr and attr.IsValid():
                    attributes.append(attr)
    return attributes


class _BaseUSDAttributeItem(_LogicalRowApiMixin, _Item):
    """
    Base Item of the Model.
    """

    _include_self_value_models_when_unowned = True

    def __init__(
        self,
        context_name: str,
        attribute_paths: list[Sdf.Path],
    ) -> None:
        """
        Args:
            context_name: the context name
            attribute_paths: the list of USD attribute(s) the item will represent
        """
        super().__init__()
        self._context_name = context_name
        self._stage = omni.usd.get_context(self._context_name).get_stage()

        self._attribute_paths = attribute_paths
        self._name_models = []
        self._value_models = []

        self.pre_open_callback: Callable[[Callable[[], None]], None] | None = None
        self.edit_group_layout: dict | None = None
        self.edit_group_path: str | None = None
        self.logical_group_items: list[_BaseUSDAttributeItem] = []
        self.logical_group_definition: _LogicalGroupDefinition | None = None

        self.__on_override_removed = _Event()

    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        """Return attributes reset by the item cleanup helper."""
        default_attr = super().default_attr
        default_attr.update(
            {
                "_context_name": None,
                "_attribute_paths": None,
                "_stage": None,
                "pre_open_callback": None,
                "edit_group_layout": None,
                "edit_group_path": None,
                "logical_group_items": None,
                "logical_group_definition": None,
            }
        )
        return default_attr

    @property
    def attribute_paths(self) -> list[Sdf.Path]:
        """
        Get the attribute/property paths this item represents.

        Returns:
            List of USD property paths
        """
        return self._attribute_paths

    def get_all_properties(self) -> list[Usd.Property]:
        """
        Get every USD property represented by this item.

        Returns:
            Valid USD properties the item acts on.
        """
        properties: list[Usd.Property] = []
        seen: set[Sdf.Path] = set()

        def append_property(prop: Usd.Property | None) -> None:
            """Append one valid property once.

            Args:
                prop: Candidate property to append.
            """
            if not prop or not prop.IsValid() or prop.GetPath() in seen:
                return
            seen.add(prop.GetPath())
            properties.append(prop)

        for property_path in self._attribute_paths:
            append_property(self._stage.GetPropertyAtPath(property_path) if self._stage else None)
        for prop in self.get_all_attributes():
            append_property(prop)
        return properties

    @property
    def context_name(self) -> str:
        """
        Get the USD context name for this item.

        Returns:
            USD context name string
        """
        return self._context_name

    def set_display_attr_names(self, display_attr_names: list[str]) -> None:
        """
        Set the display name of the attributes

        Args:
            display_attr_names: list of display name
        """
        for i, name_model in enumerate(self._name_models):
            try:
                display_attr_name = display_attr_names[i]
            except IndexError:
                # we don't need to repeat the attribute name multiple times here
                display_attr_name = ""
            name_model.set_display_attr_name(display_attr_name)

    def set_display_attr_names_tooltip(self, display_attr_names_tooltip: list[str]) -> None:
        """
        Set the display name of the attributes

        Args:
            display_attr_names_tooltip: list of display name tooltip
        """
        for i, name_model in enumerate(self._name_models):
            try:
                tooltip = display_attr_names_tooltip[i]
            except IndexError:
                # we don't need to repeat the attribute tooltip multiple times here
                tooltip = ""
            name_model.set_display_attr_name_tooltip(tooltip)

    def get_all_attributes(self) -> list[Usd.Attribute]:
        """
        Get every USD attribute represented by this item.

        Returns:
            List of authored USD attributes the item acts on.
        """
        return _get_value_model_attributes(cast(Iterable[_AttributeBackedValueModel], self.value_models))

    def get_owned_attributes(self) -> list[Usd.Attribute]:
        """Return the USD attributes owned by this visible property row."""
        if self.logical_group_definition is not None:
            return self._get_logical_group_attributes()
        if not self.logical_group_items:
            return self.get_all_attributes()

        return _get_value_model_attributes(cast(Iterable[_AttributeBackedValueModel], self.get_owned_value_models()))

    @property
    def is_overriden(self) -> bool:
        """Return whether the row has authored attribute overrides.

        Returns:
            True if any owned USD attribute has an override.
        """
        attributes = self.get_owned_attributes()
        if attributes:
            return _is_item_overriden(self._stage, attributes)
        return any(value_model.is_overriden for value_model in self.get_owned_value_models())

    def get_owned_properties(self) -> list[Usd.Property]:
        """Return the USD properties owned by this visible property row."""
        if not self.logical_group_items and self.logical_group_definition is None:
            return self.get_all_properties()
        return list(self.get_owned_attributes())

    def _get_logical_group_base_name(self) -> str | None:
        """Return this row's logical group base name from its primary attribute path.

        Returns:
            Logical group base name, or ``None`` when this row is not a logical group.
        """
        if self.logical_group_definition is None or not self.attribute_paths:
            return None
        return self.logical_group_definition.get_base_name(self.attribute_paths[0].name)

    def get_target_paths(self) -> list[str]:
        """Return target prim paths derived from this attribute row's USD attribute paths.

        Regular USD property rows are anchored by one or more concrete USD attributes. Their edit targets are the
        unique prim paths owning those attributes, kept in attribute-path order so multi-selection edits preserve the
        same top/source ordering used by the rest of the property row model.
        """
        result: list[str] = []
        seen: set[str] = set()
        for attr_path in self.attribute_paths:
            prim_path = str(attr_path.GetPrimPath())
            if prim_path in seen:
                continue
            seen.add(prim_path)
            result.append(prim_path)
        return result

    def _get_logical_group_attributes(self) -> list[Usd.Attribute]:
        """Return attributes belonging to this row's logical group on every target.

        Returns:
            Valid USD attributes for this row's logical group.
        """
        definition = self.logical_group_definition
        base_name = self._get_logical_group_base_name()
        if definition is None or base_name is None:
            return []
        return _get_logical_group_attributes(self._context_name, self.get_target_paths(), [base_name], definition)

    def get_row_state(self) -> _LogicalRowState:
        """Return the visual state for this property row."""
        value_models = self.get_owned_value_models()
        definition = self.logical_group_definition
        base_name = self._get_logical_group_base_name()
        if definition is not None and base_name is not None:
            return _LogicalRowState(
                is_mixed=definition.is_mixed(self._context_name, self.get_target_paths(), base_name),
                is_overriden=self.is_overriden,
                is_default=all(value_model.is_default for value_model in value_models),
            )
        return _LogicalRowState(
            is_mixed=any(value_model.is_mixed for value_model in value_models),
            is_overriden=(
                any(value_model.is_overriden for value_model in value_models)
                if self.logical_group_items
                else self.is_overriden
            ),
            is_default=all(value_model.is_default for value_model in value_models),
        )

    def reset_row_value(self) -> None:
        """Reset this property row to its default value."""
        value_models = self.get_owned_value_models()
        if all(value_model.is_default for value_model in value_models):
            return
        with omni.kit.undo.group():
            for value_model in value_models:
                value_model.reset_default_value()

    def delete_row_overrides(self, layer: Sdf.Layer | None = None) -> None:
        """Delete overrides owned by this property row.

        Args:
            layer: Optional layer to remove opinions from. When omitted, all
                layer overrides for this row are removed.
        """
        if not self.logical_group_items:
            if layer is None:
                self.delete_all_overrides()
            else:
                self.delete_layer_override(layer)
            return

        attributes = self.get_owned_attributes()
        with Sdf.ChangeBlock():
            for attribute in attributes:
                if layer is None:
                    _delete_all_overrides(attribute, context_name=self._context_name)
                else:
                    _delete_layer_override(layer, attribute, context_name=self._context_name)
        self.__on_override_removed()

    def delete_all_overrides(self):
        attributes = self.get_all_attributes()
        with Sdf.ChangeBlock():
            for attribute in attributes:
                _delete_all_overrides(attribute, context_name=self._context_name)
        self.__on_override_removed()

    def delete_layer_override(self, layer):
        attributes = self.get_all_attributes()
        with Sdf.ChangeBlock():
            for attribute in attributes:
                _delete_layer_override(layer, attribute, context_name=self._context_name)
        self.__on_override_removed()

    def subscribe_override_removed(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_override_removed, function)


class USDAttributeItem(_BaseUSDAttributeItem):
    """
    Item that represent a USD attribute on the tree

    Args:
        context_name: the context name
        attribute_paths: the list of USD attribute(s) the item will represent
        display_attr_names: override the name(s) of the attribute(s) to show by those one
        display_attr_names_tooltip: tooltip to show on the attribute name
        default_value: optional override for the default value
        read_only: show the attribute(s) as read only
        value_type_name: if None, the type name will be inferred
        related_override_paths: optional related properties that should receive specs with value writes
        ui_metadata: optional dict of UI hints used only when constructing the
            default ``BoundsAdapter``. Treat as a producer payload for bounds
            normalization rather than a direct bounds source.
        bounds_adapter: optional preconfigured bounds adapter instance. When
            provided, this is the canonical source of bounds/step values.
            When omitted, ``BoundsAdapter`` is constructed with ``ui_metadata``.
    """

    def __init__(
        self,
        context_name: str,
        attribute_paths: list[Sdf.Path],
        display_attr_names: list[str] | None = None,
        display_attr_names_tooltip: list[str] | None = None,
        default_value: Any = None,
        read_only: bool = False,
        value_type_name: Sdf.ValueTypeName | None = None,
        related_override_paths: list[Sdf.Path] | None = None,
        ui_metadata: dict | None = None,
        bounds_adapter: _BoundsAdapter | None = None,
    ):
        super().__init__(context_name, attribute_paths)
        # take only the first attribute name because the attribute name is the same for all values
        # (even in multi selection)
        type_name = value_type_name or _get_type_name(_get_metadata(context_name, attribute_paths))
        self._element_count = CHANNEL_ELEMENT_BUILDER_TABLE.get(type_name, 1)

        # we don't need to repeat the attribute name and tooltip multiple times here
        if self._element_count > 1:
            if display_attr_names:
                display_attr_names.extend([""] * (self._element_count - len(display_attr_names)))
            if display_attr_names_tooltip:
                display_attr_names_tooltip.extend([""] * (self._element_count - len(display_attr_names_tooltip)))

        self._init_name_models(context_name, attribute_paths, display_attr_names, display_attr_names_tooltip)
        self._init_value_models(
            context_name,
            attribute_paths,
            default_value=default_value,
            read_only=read_only,
            value_type_name=value_type_name,
            display_attr_names=display_attr_names,
            related_override_paths=related_override_paths,
        )
        self._ui_metadata = ui_metadata

        if bounds_adapter is None:
            bounds_adapter = _BoundsAdapter(self._ui_metadata)
        self._ui_bounds_adapter = bounds_adapter

    def get_min_max_bounds(
        self,
    ) -> tuple[_ScalarValue | None, _ScalarValue | None, _ScalarValue | None, _ScalarValue | None] | None:
        """
        Get normalized bounds metadata from the configured adapter instance.

        Bounds come from the adapter payload provided at item construction.
        Partial bounds are allowed, so any tuple element may be ``None``.

        Returns:
            ``(min_value, max_value, hard_min_value, hard_max_value)`` when
            bounds metadata exists, or ``None`` when no bounds metadata is
            present. Callers that require both min and max (for example,
            slider widgets) must validate that both are non-None.
        """
        return self._ui_bounds_adapter.bounds

    def get_step_value(self) -> _ScalarValue | None:
        """Get the UI step size for this attribute, if any.

        Resolves step from the configured adapter instance.

        Returns:
            The step value as a float or int, or ``None`` if no step is defined.
        """
        return self._ui_bounds_adapter.step

    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        """Return attributes reset by the item cleanup helper."""
        default_attr = super().default_attr
        default_attr.update(
            {
                "_element_count": 1,
                "_name_models": None,
                "_value_models": None,
                "_ui_metadata": None,
                "_ui_bounds_adapter": None,
            }
        )
        return default_attr

    def _init_name_models(self, context_name, attribute_paths, display_attr_names, display_attr_names_tooltip):
        self._name_models = [
            _UsdAttributeNameModel(
                context_name,
                attribute_paths[0],
                i,
                display_attr_name=display_attr_names[i] if display_attr_names else None,
                display_attr_name_tooltip=display_attr_names_tooltip[i] if display_attr_names_tooltip else None,
            )
            for i in range(self._element_count)
        ]

    def _init_value_models(
        self,
        context_name,
        attribute_paths,
        default_value: Any = None,
        read_only: bool = False,
        value_type_name: Sdf.ValueTypeName | None = None,
        display_attr_names: list[str] | None = None,
        related_override_paths: list[Sdf.Path] | None = None,
    ):
        # Value tooltips use the base display name for every vector channel; the value model adds X/Y/Z/W suffixes.
        self._value_models = [
            _UsdAttributeValueModel(
                context_name,
                attribute_paths,
                i,
                default_value=default_value,
                read_only=read_only,
                value_type_name=value_type_name,
                tooltip_display_name=display_attr_names[0] if display_attr_names else None,
                related_override_paths=related_override_paths,
            )
            for i in range(self._element_count)
        ]

    @property
    def element_count(self):
        """Number of channel the attribute has (for example, float3 is 3 channels)"""
        return self._element_count

    @property
    def has_bounds_data(self) -> bool:
        """True if any normalized bounds metadata is present on the configured adapter."""
        return self.get_min_max_bounds() is not None


class USDAttributeXformItem(USDAttributeItem):
    """USD attribute item that treats related xform ops as one owned row."""

    def __init__(
        self,
        context_name: str,
        attribute_paths: list[Sdf.Path],
        display_attr_names: list[str] | None = None,
        display_attr_names_tooltip: list[str] | None = None,
        read_only: bool = False,
        value_type_name: Sdf.ValueTypeName | None = None,
        related_attribute_paths: list[Sdf.Path] | None = None,
    ) -> None:
        """Create an xform item that authors all sibling xform ops together.

        Args:
            context_name: USD context containing the attrs.
            attribute_paths: Xform attr paths represented by the row.
            display_attr_names: Optional per-channel display names.
            display_attr_names_tooltip: Optional per-channel tooltips.
            read_only: Whether the row is editable.
            value_type_name: Optional explicit USD value type.
            related_attribute_paths: Related xform property paths to author with value writes.
        """
        related_attribute_paths = list(dict.fromkeys(related_attribute_paths or []))
        super().__init__(
            context_name,
            attribute_paths,
            display_attr_names=display_attr_names,
            display_attr_names_tooltip=display_attr_names_tooltip,
            read_only=read_only,
            value_type_name=value_type_name,
            related_override_paths=related_attribute_paths,
        )
        self._related_attribute_paths = related_attribute_paths

    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        """Return attributes reset by the item cleanup helper."""
        default_attr = super().default_attr
        default_attr.update(
            {
                "_related_attribute_paths": None,
            }
        )
        return default_attr

    def __show_confirmation_dialog(self, handler: Callable) -> None:
        def handle_ok(_dialog: _MessageDialog) -> None:
            handler()
            _dialog.hide()

        dialog = _MessageDialog(
            width=350,
            message="Deleting this override will remove all XForm overrides for this object. Do you want to proceed?",
            ok_handler=handle_ok,
            ok_label="Delete",
            cancel_label="Cancel",
        )
        dialog.show()

    def _get_prims(self, attributes: list[Usd.Attribute]) -> list[Usd.Prim]:
        """Get the associated prim for each attribute.

        Args:
            attributes: USD attributes whose owning prims should be resolved.

        Returns:
            Unique prims that own the supplied attributes.
        """
        stage = omni.usd.get_context(self._context_name).get_stage()
        if not stage:
            return []
        return list({stage.GetPrimAtPath(attribute.GetPrimPath()) for attribute in attributes})

    def get_all_attributes(self) -> list[Usd.Attribute]:
        """
        Xform items should return all xform attributes, not just the selected attribute.

        Returns:
            List of authored USD attributes the item acts on.
        """
        if self._related_attribute_paths:
            attributes = []
            seen = set()
            for attribute_path in self._related_attribute_paths:
                if attribute_path in seen:
                    continue
                seen.add(attribute_path)
                attr = self._stage.GetAttributeAtPath(attribute_path) if self._stage else None
                if attr and attr.IsValid():
                    attributes.append(attr)
            return attributes

        attributes = set()
        for prim in self._get_prims(super().get_all_attributes()):
            xformable_prim = UsdGeom.Xformable(prim)
            for op in xformable_prim.GetOrderedXformOps():
                attributes.add(op.GetAttr())
            attributes.add(xformable_prim.GetXformOpOrderAttr())
        return list(attributes)

    def delete_all_overrides(self) -> None:
        self.__show_confirmation_dialog(partial(super().delete_all_overrides))

    def delete_layer_override(self, layer) -> None:
        self.__show_confirmation_dialog(partial(super().delete_layer_override, layer))


class VirtualUSDAttributeItem(USDAttributeItem):
    """Item of the model"""

    def __init__(
        self,
        context_name: str,
        attribute_paths: list[Sdf.Path],
        value_type_name: Sdf.ValueTypeName,
        default_value: Any,
        display_attr_names: list[str] | None = None,
        display_attr_names_tooltip: list[str] | None = None,
        read_only: bool = False,
        metadata: dict | None = None,
        bounds_adapter: _BoundsAdapter | None = None,
        create_callback: Callable[[Any], None] | None = None,
    ):
        """
        Args:
            context_name: The context name
            attribute_paths: The attribute paths
            value_type_name: Value type name for the default values
            default_value: The default value for the attributes
            create_callback: A function called after the attribute is edited (End Edit).
                             By default, this simply adds the attribute to the prim
            display_attr_names: Display name for the attribute
            display_attr_names_tooltip: tooltip to show on the attribute name
            read_only: If the attribute is read-only
            metadata: Optional value-model metadata used by virtual attribute
                behavior (for example type/context hints). This is not used for
                bounds normalization.
            bounds_adapter: Optional preconfigured bounds adapter instance.
                This is the canonical source of bounds/step values.
        """
        # Note: These are excluded from the default_attr because we do not want them cleared in super().__init__()
        self._default_value = default_value
        self._metadata = metadata
        self._create_callback = create_callback
        self._value_type_name = value_type_name

        super().__init__(
            context_name,
            attribute_paths,
            display_attr_names=display_attr_names,
            display_attr_names_tooltip=display_attr_names_tooltip,
            read_only=read_only,
            value_type_name=value_type_name,
            bounds_adapter=bounds_adapter,
        )

    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        return super().default_attr

    def _init_name_models(self, context_name, attribute_paths, display_attr_names, display_attr_names_tooltip):
        self._name_models = [
            _UsdAttributeNameModel(
                context_name,
                attribute_paths[0],
                i,
                display_attr_name=display_attr_names[i] if display_attr_names else None,
                display_attr_name_tooltip=display_attr_names_tooltip[i] if display_attr_names_tooltip else None,
            )
            for i in range(self._element_count)
        ]

    def _init_value_models(
        self,
        context_name,
        attribute_paths,
        default_value: Any = None,
        read_only: bool = False,
        value_type_name: Sdf.ValueTypeName | None = None,
        display_attr_names: list[str] | None = None,
        related_override_paths: list[Sdf.Path] | None = None,
    ):
        # Note: VirtualUSDAttributeItem uses self._default_value from __init__, ignoring passed default_value
        if not value_type_name:
            raise ValueError("value_type_name is required for virtual attribute value models")
        self._value_models = [
            _VirtualUsdAttributeValueModel(
                context_name,
                attribute_paths,
                i,
                value_type_name,
                default_value=self._default_value,
                read_only=read_only,
                metadata=self._metadata,
                create_callback=self._create_callback,
                tooltip_display_name=display_attr_names[0] if display_attr_names else None,
                related_override_paths=related_override_paths,
            )
            for i in range(self._element_count)
        ]


class _BaseListModelItem(_BaseUSDAttributeItem):
    """Item of the model"""

    value_model_class: type[_UsdListModelAttrValueModel] | type[_UsdAttributeMetadataValueModel] = (
        _UsdListModelAttrValueModel
    )

    def __init__(
        self,
        context_name: str,
        attribute_paths: list[Sdf.Path],
        default_value: str,
        options: list[str],
        read_only: bool = False,
        value_type_name: Sdf.ValueTypeName | None = None,
        metadata: dict = None,
        display_attr_names: list[str] | None = None,
        display_attr_names_tooltip: list[str] | None = None,
        metadata_key: str | None = None,
    ):
        """
        Args:
            context_name: the context name
            attribute_paths: the list of USD attribute(s) the item will represent
            default_value: the metadata key default value
            options: the metadata available options
            read_only: read only or not
            value_type_name: the type name of the attribute
            metadata: provide the attribute metadata if virtual
            display_attr_names: override the name(s) of the attribute(s) to show by those one
            display_attr_names_tooltip: tooltip to show on the attribute name
            metadata_key: the metadata key to show
        """
        super().__init__(context_name, attribute_paths)
        self._metadata_key = metadata_key
        self._metadata = metadata
        self._init_name_models(context_name, attribute_paths, display_attr_names, display_attr_names_tooltip)
        self._init_value_models(
            context_name,
            attribute_paths,
            default_value,
            options,
            read_only,
            value_type_name=value_type_name,
            display_attr_names=display_attr_names,
        )

    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        """Return attributes reset by the item cleanup helper."""
        default_attr = super().default_attr
        default_attr.update(
            {
                "_name_models": None,
                "_value_models": None,
            }
        )
        return default_attr

    def _init_name_models(self, context_name, attribute_paths, display_attr_names, display_attr_names_tooltip):
        display_attr_name = self._resolve_display_attr_name(display_attr_names)
        display_attr_name_tooltip = display_attr_names_tooltip[0] if display_attr_names_tooltip else None

        self._name_models = [
            _UsdAttributeNameModel(
                context_name,
                attribute_paths[0],
                0,
                display_attr_name=display_attr_name,
                display_attr_name_tooltip=display_attr_name_tooltip,
            )
        ]

    def _init_value_models(
        self,
        context_name,
        attribute_paths,
        default_value,
        options,
        read_only,
        value_type_name: Sdf.ValueTypeName | None = None,
        display_attr_names: list[str] | None = None,
    ):
        display_attr_name = self._resolve_display_attr_name(display_attr_names)
        self._value_models = [
            self.value_model_class(
                context_name,
                attribute_paths,
                default_value,
                options,
                read_only=read_only,
                value_type_name=value_type_name,
                metadata=self._metadata,
                metadata_key=self._metadata_key,
                tooltip_display_name=display_attr_name,
            )
        ]

    def _resolve_display_attr_name(self, display_attr_names: list[str] | None) -> str | None:
        """Resolve the display name shared by the label and value tooltip."""
        display_attr_name = display_attr_names[0] if display_attr_names else None
        if display_attr_name and self._metadata_key:
            return f"{display_attr_name} {self._metadata_key}"
        return display_attr_name


class USDMetadataListItem(_BaseListModelItem):
    """Item of the model"""

    value_model_class: type[_UsdAttributeMetadataValueModel] = _UsdAttributeMetadataValueModel

    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        return super().default_attr


class USDAttrListItem(_BaseListModelItem):
    """Item of the model"""

    value_model_class = _UsdListModelAttrValueModel

    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        return super().default_attr


class VirtualUSDAttrListItem(_BaseListModelItem):
    """Item of the model"""

    value_model_class = _VirtualUsdListModelAttrValueModel

    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        return super().default_attr


@dataclasses.dataclass
class USDAttributeDef:
    """
    Holds arguments for a USD attribute that may be created at a later time.
    """

    path: Sdf.Path
    attr_type: Sdf.ValueTypeNames
    op: UsdGeom.XformOp = None
    value: Any | None = None
    exists: bool = False
    documentation: str = None
    display_group: str = None


class USDAttributeItemStub(USDAttributeItem):
    """
    Holds USD attribute(s) that may be created at a later time.
    """

    def __init__(
        self,
        name: str,
        context_name: str,
        attribute_defs: Sequence[USDAttributeDef],
    ):
        """
        Parameters
        ----------
        name: str
            A name for the group of attributes this item represents.
        context_name:  str
        attribute_defs: Sequence[USDAttributeDef]
            Attribute definitions to create. These are created in the order they are provided.
        """
        super().__init__(
            context_name=context_name,
            attribute_paths=[x.path for x in attribute_defs],
        )

        self.name = name
        self._attribute_defs = attribute_defs

        self._refresh_task: asyncio.Task | None = None
        self._create_task: asyncio.Task | None = None

        self.__on_create_attributes_begin = _Event()
        self.__on_create_attributes_end = _Event()

    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        default_attr = super().default_attr
        default_attr.update(
            {
                "_attribute_defs": None,
                "_refresh_task": None,
                "_create_task": None,
            }
        )
        return default_attr

    def _init_name_models(self, context_name, attribute_paths, display_attr_names, display_attr_names_tooltip):
        self._name_models = []

    def _init_value_models(
        self,
        context_name,
        attribute_paths,
        default_value: Any = None,
        read_only: bool = False,
        value_type_name: Sdf.ValueTypeName | None = None,
        display_attr_names: list[str] | None = None,
        related_override_paths: list[Sdf.Path] | None = None,
    ):
        self._value_models = []

    @omni.usd.handle_exception
    async def _any_attr_defs_exist_or_changed_async(self) -> bool:
        """
        Determine if any of the attribute paths this item represents exist in USD.
        """
        await omni.kit.app.get_app().next_update_async()
        if self._attribute_defs is None:
            return False
        for attr_def in self._attribute_defs:
            prim = self._stage.GetPrimAtPath(attr_def.path.GetPrimPath())
            if prim.IsValid():
                attr = prim.GetAttribute(attr_def.path.name)
                if attr.IsValid() and not attr.IsHidden():
                    if attr_def.exists:
                        if attr_def.value != attr.Get():
                            return True
                    else:
                        return True
        return False

    @omni.usd.handle_exception
    async def _refresh_async(self):
        if self._create_task is None and await self._any_attr_defs_exist_or_changed_async():
            self.__on_create_attributes_end(self._attribute_paths)
        self._refresh_task = None

    def refresh(self):
        """
        Trigger a task to determine if the attributes should be created.

        This can happen if the attributes are created by some mechanism besides interacting with widgets presented in
        the TreeView.
        """
        if self._refresh_task is None and self._create_task is None:
            self._refresh_task = asyncio.ensure_future(self._refresh_async())

    def _create_attributes(self):
        with omni.kit.undo.group():
            for attr_def in self._attribute_defs:
                # Grab the current value for existing attributes, otherwise use the default.
                if attr_def.exists:
                    attr_value = self._stage.GetAttributeAtPath(attr_def.path).Get()
                else:
                    attr_value = attr_def.value

                omni.kit.commands.execute(
                    "ChangePropertyCommand",
                    prop_path=str(attr_def.path),
                    value=attr_value,
                    prev=None,
                    type_to_create_if_not_exist=attr_def.attr_type,
                    usd_context_name=self._context_name,
                )
                if attr_def.documentation:
                    omni.kit.commands.execute(
                        "ChangeMetadataCommand",
                        object_paths=[str(attr_def.path)],
                        key=Sdf.PropertySpec.DocumentationKey,
                        value=attr_def.documentation,
                        usd_context_name=self._context_name,
                    )

    @omni.usd.handle_exception
    async def _create_attributes_async(self):
        self.__on_create_attributes_begin(self._attribute_paths)
        await omni.kit.app.get_app().next_update_async()
        self._create_attributes()
        self.__on_create_attributes_end(self._attribute_paths)
        self._create_task = None

    def create_attributes(self):
        """
        Create the USD attributes.
        """
        if self._create_task is None:
            self._create_task = asyncio.ensure_future(self._create_attributes_async())

    def subscribe_create_attributes_begin(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_create_attributes_begin, function)

    def subscribe_create_attributes_end(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_create_attributes_end, function)


class USDAttributeXformItemStub(USDAttributeItemStub):
    """
    Holds USD XForm attribute(s) that may be created at a later time.
    """

    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        return super().default_attr

    def _create_attributes(self):
        # NOTE: we intentionally do not invoke the super class's implementation of this function
        attr_defs_by_prim = collections.defaultdict(list)
        for attr_def in self._attribute_defs:
            prim = self._stage.GetPrimAtPath(attr_def.path.GetPrimPath())

            # Grab the current value for existing attributes, otherwise use the default.
            if attr_def.exists:
                value = prim.GetAttribute(attr_def.path.name).Get()
            else:
                value = attr_def.value

            attr_defs_by_prim[prim].append(
                {
                    "name": attr_def.path.name,
                    "op": attr_def.op,
                    "precision": _OPS_ATTR_PRECISION_TABLE.get(attr_def.op, _DEFAULT_PRECISION),
                    "value": value,
                }
            )

        with omni.kit.undo.group():
            for prim, attr_defs in attr_defs_by_prim.items():
                omni.kit.commands.execute(
                    "SetFluxXFormPrim",
                    prim_path=str(prim.GetPath()),
                    attribute_defs=attr_defs,
                    context_name=self._context_name,
                    stage=self._stage,
                )


class USDRelationshipItem(_BaseUSDAttributeItem):
    """
    Item representing USD relationship properties.

    Parallel to USDAttributeItem but uses UsdRelationshipValueModel.
    Relationships are always single-target (element_count = 1).
    """

    def __init__(
        self,
        context_name: str,
        relationship_paths: list[Sdf.Path],
        display_attr_names: list[str] | None = None,
        display_attr_names_tooltip: list[str] | None = None,
        read_only: bool = False,
        ui_metadata: dict[str, Any] | None = None,
    ):
        """
        Create relationship item.

        Args:
            context_name: USD context name
            relationship_paths: Paths to relationship properties
            display_attr_names: Display names for property
            display_attr_names_tooltip: Tooltips for property
            read_only: Whether relationship can be edited
            ui_metadata: Optional dict of UI hints for field builders (e.g., picker config).
                        Framework stores this opaquely; consumers interpret it.
        """
        super().__init__(context_name, relationship_paths)

        self._element_count = 1
        self._ui_metadata = ui_metadata or {}

        self._init_name_models(context_name, relationship_paths, display_attr_names, display_attr_names_tooltip)
        self._init_value_models(context_name, relationship_paths, read_only)

    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        """Return attributes reset by the item cleanup helper."""
        default_attr = super().default_attr
        default_attr.update(
            {
                "_element_count": 1,
                "_name_models": None,
                "_value_models": None,
                "_ui_metadata": None,
            }
        )
        return default_attr

    @property
    def ui_metadata(self) -> dict[str, Any]:
        """
        Get UI metadata hints for field builders.

        Returns:
            Dict of UI hints (e.g., picker configuration). Framework stores
            this opaquely; consumers interpret the contents.
        """
        return self._ui_metadata

    def _init_name_models(
        self,
        context_name: str,
        relationship_paths: list[Sdf.Path],
        display_attr_names: list[str] | None,
        display_attr_names_tooltip: list[str] | None,
    ) -> None:
        """Create name models for relationship display.

        Args:
            context_name: USD context containing the relationships.
            relationship_paths: Relationship paths represented by the row.
            display_attr_names: Optional display names.
            display_attr_names_tooltip: Optional display tooltips.
        """
        self._name_models = [
            _UsdAttributeNameModel(
                context_name,
                relationship_paths[0],
                0,
                display_attr_name=display_attr_names[0] if display_attr_names else None,
                display_attr_name_tooltip=display_attr_names_tooltip[0] if display_attr_names_tooltip else None,
            )
        ]

    def _init_value_models(self, context_name: str, relationship_paths: list[Sdf.Path], read_only: bool) -> None:
        """Create relationship value model.

        Args:
            context_name: USD context containing the relationships.
            relationship_paths: Relationship paths represented by the row.
            read_only: Whether the value model is editable.
        """
        from .item_model.relationship_value import UsdRelationshipValueModel  # noqa: PLC0415

        self._value_models = [
            UsdRelationshipValueModel(
                context_name,
                relationship_paths,
                read_only=read_only,
            )
        ]

    @property
    def element_count(self) -> int:
        """Return the single value column used by relationship rows."""
        return 1

    def get_all_attributes(self) -> list[Usd.Attribute]:
        """Return no USD attributes because relationship rows are relationship-backed."""
        return []


class USDLogicalGroupOutletItem(_LogicalRowApiMixin, _Item):
    """Accessor outlet for a logical group of curve attributes.

    Not backed by a USD attribute. The consumer places it in an ItemGroup
    to show a button that opens the curve editor in multi-curve mode.

    Args:
        edit_group_layout: Panel-level layout dict (shared instance with tagged items).
        context_name: USD context name.
        target_paths: Ordered prim paths the curves live on.
    """

    def __init__(self, edit_group_layout: dict, context_name: str, target_paths: list[str]) -> None:
        """Create a synthetic outlet item from edit-group metadata and explicit targets.

        Args:
            edit_group_layout: Particle edit-group layout defining curve groups and display metadata.
            context_name: USD context containing the target prims.
            target_paths: Ordered prim paths controlled by this outlet.
        """
        super().__init__()
        self.edit_group_layout = edit_group_layout
        self.context_name = context_name
        self.pre_open_callback: Callable[[Callable[[], None]], None] | None = None
        self.target_paths = list(target_paths)
        self.logical_group_items: list[_BaseUSDAttributeItem] = []
        self.logical_group_definition: _LogicalGroupDefinition = CURVE_LOGICAL_GROUP_DEFINITION

        display = edit_group_layout.get("display_name", "Curves")
        tooltip = edit_group_layout.get("tooltip", "")
        self._name_models = [_ItemGroupNameModel(display, tooltip)]
        self._value_models = []

    @property
    def default_attr(self) -> dict[str, None]:
        """Return attributes reset by the item cleanup helper."""
        default_attr = super().default_attr
        default_attr.update(
            {
                "edit_group_layout": None,
                "context_name": None,
                "target_paths": None,
                "pre_open_callback": None,
                "logical_group_items": None,
                "logical_group_definition": None,
            }
        )
        return default_attr

    @property
    def element_count(self) -> int:
        """Return the single value cell used by the outlet button."""
        return 1

    def get_target_paths(self) -> list[str]:
        """Return the explicit target prim paths for this synthetic logical group outlet.

        Outlet rows are not anchored by a single USD attribute path. They represent a grouped editor button built from
        edit-group metadata, so their targets come from the ordered prim path list supplied by that builder rather
        than being inferred from companion attribute items.
        """
        return list(self.target_paths)

    def get_owned_attributes(self) -> list[Usd.Attribute]:
        """Return the USD attributes owned by this logical group outlet row."""
        base_names = self.edit_group_layout.get("curve_map", {})
        return _get_logical_group_attributes(
            self.context_name, self.get_target_paths(), base_names, self.logical_group_definition
        )

    def get_owned_properties(self) -> list[Usd.Property]:
        """Return the USD properties owned by this logical group outlet row."""
        return list(self.get_owned_attributes())

    def get_row_state(self) -> _LogicalRowState:
        """Return the visual state for this logical group outlet row."""
        base_names = list(self.edit_group_layout.get("curve_map", {}))
        target_paths = self.get_target_paths()
        if not target_paths or not base_names:
            return _LogicalRowState()
        stage = omni.usd.get_context(self.context_name).get_stage()
        if stage is None:
            return _LogicalRowState()
        attributes = self.get_owned_attributes()
        is_overriden = _is_item_overriden(stage, attributes)
        is_default = True
        for attribute in attributes:
            default_value = _get_default_attribute_value(attribute)
            if default_value is None:
                continue
            if attribute.Get() != default_value:
                is_default = False
                break
        is_mixed = False
        for base_name in base_names:
            attr_names = self.logical_group_definition.get_attr_names(base_name)
            first_signature = _get_grouped_item_value_signature(stage, target_paths[0], attr_names)
            for prim_path in target_paths[1:]:
                if _get_grouped_item_value_signature(stage, prim_path, attr_names) != first_signature:
                    is_mixed = True
                    break
            if is_mixed:
                break
        return _LogicalRowState(is_mixed=is_mixed, is_overriden=is_overriden, is_default=is_default)

    def reset_row_value(self) -> None:
        """Reset this logical group outlet row to its default value."""
        if self.get_row_state().is_default:
            return
        with omni.kit.undo.group():
            for attribute in self.get_owned_attributes():
                default_value = _get_default_attribute_value(attribute)
                if default_value is None:
                    continue
                omni.kit.commands.execute(
                    "ChangeProperty",
                    prop_path=attribute.GetPath(),
                    value=default_value,
                    prev=None,
                    usd_context_name=self.context_name,
                )

    def delete_row_overrides(self, layer: Sdf.Layer | None = None) -> None:
        """Delete overrides owned by this logical group outlet row.

        Args:
            layer: Optional layer to remove opinions from. When omitted, all
                layer overrides for this outlet are removed.
        """
        attributes = self.get_owned_attributes()
        with Sdf.ChangeBlock():
            for attribute in attributes:
                if layer is None:
                    _delete_all_overrides(attribute, context_name=self.context_name)
                else:
                    _delete_layer_override(layer, attribute, context_name=self.context_name)

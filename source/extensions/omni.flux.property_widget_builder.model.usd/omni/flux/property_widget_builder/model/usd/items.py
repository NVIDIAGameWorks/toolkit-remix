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

import abc
import asyncio
import collections
import dataclasses
import typing
from functools import partial
from typing import Any, Callable, List, Optional, Sequence, Type

import omni.kit
import omni.kit.commands
import omni.kit.undo
import omni.usd
from omni.flux.property_widget_builder.widget import Item as _Item
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.kit.window.popup_dialog import MessageDialog as _MessageDialog
from pxr import Sdf, UsdGeom

from .item_model.attr_list_model_value import UsdListModelAttrValueModel as _UsdListModelAttrValueModel
from .item_model.attr_list_model_value import VirtualUsdListModelAttrValueModel as _VirtualUsdListModelAttrValueModel
from .item_model.attr_name import UsdAttributeNameModel as _UsdAttributeNameModel
from .item_model.attr_value import UsdAttributeValueModel as _UsdAttributeValueModel
from .item_model.attr_value import VirtualUsdAttributeValueModel as _VirtualUsdAttributeValueModel
from .item_model.metadata_list_model_value import UsdListModelAttrMetadataValueModel as _UsdAttributeMetadataValueModel
from .mapping import CHANNEL_ELEMENT_BUILDER_TABLE
from .mapping import DEFAULT_PRECISION as _DEFAULT_PRECISION
from .mapping import OPS_ATTR_PRECISION_TABLE as _OPS_ATTR_PRECISION_TABLE
from .utils import delete_all_overrides as _delete_all_overrides
from .utils import delete_layer_override as _delete_layer_override
from .utils import get_metadata as _get_metadata
from .utils import get_type_name as _get_type_name

if typing.TYPE_CHECKING:
    from pxr import Usd


class _BaseUSDAttributeItem(_Item):
    """
    Base Item of the Model.
    """

    def __init__(
        self,
        context_name: str,
        attribute_paths: List[Sdf.Path],
    ):
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

        self.__on_override_removed = _Event()

    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        default_attr = super().default_attr
        default_attr.update(
            {
                "_context_name": None,
                "_attribute_paths": None,
                "_stage": None,
            }
        )
        return default_attr

    def set_display_attr_names(self, display_attr_names: List[str]):
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

    def set_display_attr_names_tooltip(self, display_attr_names_tooltip: List[str]):
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

    def _get_all_attributes(self) -> List["Usd.Attribute"]:
        attributes = set()
        for value_model in self.value_models:
            attributes = attributes.union(value_model.attributes)
        return list(attributes)

    def delete_all_overrides(self):
        attributes = self._get_all_attributes()
        with Sdf.ChangeBlock():
            for attribute in attributes:
                _delete_all_overrides(attribute, context_name=self._context_name)
        self.__on_override_removed()

    def delete_layer_override(self, layer):
        attributes = self._get_all_attributes()
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
    """Item of the model"""

    def __init__(
        self,
        context_name: str,
        attribute_paths: List[Sdf.Path],
        display_attr_names: Optional[List[str]] = None,
        display_attr_names_tooltip: Optional[List[str]] = None,
        read_only: bool = False,
        value_type_name: Sdf.ValueTypeNames = None,
    ):
        """
        Item that represent a USD attribute on the tree

        Args:
            context_name: the context name
            attribute_paths: the list of USD attribute(s) the item will represent
            display_attr_names: override the name(s) of the attribute(s) to show by those one
            display_attr_names_tooltip: tooltip to show on the attribute name
            read_only: show the attribute(s) as read only
            value_type_name: if None, the type name will be inferred
        """
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
        self._init_value_models(context_name, attribute_paths, read_only=read_only, value_type_name=value_type_name)

    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        default_attr = super().default_attr
        default_attr.update(
            {
                "_element_count": 1,
                "_name_models": None,
                "_value_models": None,
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

    def _init_value_models(self, context_name, attribute_paths, read_only, value_type_name=None):
        type_name = str(value_type_name) if value_type_name is not None else value_type_name
        self._value_models = [
            _UsdAttributeValueModel(context_name, attribute_paths, i, read_only=read_only, type_name=type_name)
            for i in range(self._element_count)
        ]

    @property
    def element_count(self):
        """Number of channel the attribute has (for example, float3 is 3 channels)"""
        return self._element_count


class USDAttributeXformItem(USDAttributeItem):
    def __init__(
        self,
        context_name: str,
        attribute_paths: List[Sdf.Path],
        display_attr_names: Optional[List[str]] = None,
        display_attr_names_tooltip: Optional[List[str]] = None,
        read_only: bool = False,
        value_type_name: Sdf.ValueTypeNames = None,
    ):
        super().__init__(
            context_name,
            attribute_paths,
            display_attr_names=display_attr_names,
            display_attr_names_tooltip=display_attr_names_tooltip,
            read_only=read_only,
            value_type_name=value_type_name,
        )

        self._edit_subs = []
        for model in self._value_models:
            self._edit_subs.append(model.subscribe_end_edit_fn(self.__override_all_xform_ops))

    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        default_attr = super().default_attr
        default_attr.update(
            {
                "_edit_subs": None,
            }
        )
        return default_attr

    def __override_all_xform_ops(self, *_) -> None:
        with omni.kit.undo.group():
            for attr in self._get_all_attributes():
                omni.kit.commands.execute(
                    "ChangeProperty",
                    prop_path=attr.GetPath(),
                    value=attr.Get(),
                    prev=None,
                    usd_context_name=self._context_name,
                )

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

    def _get_prims(self, attributes: List["Usd.Attribute"]) -> List["Usd.Prim"]:
        """
        Get the associated prim for each attribute.
        """
        stage = omni.usd.get_context(self._context_name).get_stage()
        if not stage:
            return []
        return list({stage.GetPrimAtPath(attribute.GetPrimPath()) for attribute in attributes})

    def _get_all_attributes(self) -> List["Usd.Attribute"]:
        """
        Xform items should return all xform attributes, not just the selected attribute.
        """
        attributes = set()
        for prim in self._get_prims(super()._get_all_attributes()):
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
        attribute_paths: List[Sdf.Path],
        value_type_name: Sdf.ValueTypeNames,
        default_value: List[Any],
        display_attr_names: Optional[List[str]] = None,
        display_attr_names_tooltip: Optional[List[str]] = None,
        read_only: bool = False,
        metadata: dict = None,
        create_callback: Optional[Callable[[Any], None]] = None,
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
        """
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
        )

    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        default_attr = super().default_attr
        default_attr.update(
            {
                "_default_value": None,
                "_metadata": None,
                "_create_callback": None,
                "_value_type_name": None,
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

    def _init_value_models(self, context_name, attribute_paths, read_only, value_type_name=None):
        type_name = str(value_type_name) if value_type_name is not None else value_type_name
        self._value_models = [
            _VirtualUsdAttributeValueModel(
                context_name,
                attribute_paths,
                i,
                read_only=read_only,
                type_name=type_name,
                default_value=self._default_value,
                metadata=self._metadata,
                create_callback=self._create_callback,
            )
            for i in range(self._element_count)
        ]


class _BaseListModelItem(_BaseUSDAttributeItem):
    """Item of the model"""

    value_model_class: Type[_UsdListModelAttrValueModel] | Type[_UsdAttributeMetadataValueModel] = (
        _UsdListModelAttrValueModel
    )

    def __init__(
        self,
        context_name: str,
        attribute_paths: List[Sdf.Path],
        default_value: str,
        options: List[str],
        read_only: bool = False,
        value_type_name: str = None,
        metadata: dict = None,
        display_attr_names: Optional[List[str]] = None,
        display_attr_names_tooltip: Optional[List[str]] = None,
        metadata_key: Optional[str] = None,
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
            context_name, attribute_paths, default_value, options, read_only, value_type_name=value_type_name
        )

    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        default_attr = super().default_attr
        default_attr.update(
            {
                "_name_models": None,
                "_value_models": None,
            }
        )
        return default_attr

    def _init_name_models(self, context_name, attribute_paths, display_attr_names, display_attr_names_tooltip):
        display_attr_name = None
        if display_attr_names:
            display_attr_name = display_attr_names[0]
        if display_attr_name and self._metadata_key:
            display_attr_name = f"{display_attr_name} {self._metadata_key}"
        display_attr_name_tooltip = None
        if display_attr_names_tooltip:
            display_attr_name_tooltip = display_attr_names_tooltip[0]

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
        self, context_name, attribute_paths, default_value, options, read_only, value_type_name=None
    ):
        type_name = str(value_type_name) if value_type_name is not None else value_type_name
        self._value_models = [
            self.value_model_class(
                context_name,
                attribute_paths,
                default_value,
                options,
                read_only=read_only,
                type_name=type_name,
                metadata=self._metadata,
                metadata_key=self._metadata_key,
            )
        ]


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
    value: Optional[Any] = None
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

        self._refresh_task: Optional[asyncio.Task] = None
        self._create_task: Optional[asyncio.Task] = None

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

    def _init_value_models(self, context_name, attribute_paths, read_only, value_type_name=None):
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

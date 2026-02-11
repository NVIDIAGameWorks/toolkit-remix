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

from typing import Any

import omni.kit
import omni.ui as ui
import omni.usd
from omni.flux.property_widget_builder.model.usd import USDAttributeDef as _USDAttributeDef
from omni.flux.property_widget_builder.model.usd import USDAttributeXformItem as _USDAttributeXformItem
from omni.flux.property_widget_builder.model.usd import USDAttributeXformItemStub as _USDAttributeXformItemStub
from omni.flux.property_widget_builder.model.usd import USDDelegate as _USDPropertyDelegate
from omni.flux.property_widget_builder.model.usd import USDModel as _USDPropertyModel
from omni.flux.property_widget_builder.model.usd import USDPropertyWidget as _PropertyWidget
from omni.flux.property_widget_builder.model.usd import get_usd_listener_instance as _get_usd_listener_instance
from omni.flux.property_widget_builder.model.usd.utils import filter_virtual_attributes as _filter_virtual_attributes
from omni.flux.property_widget_builder.widget import FieldBuilder as _FieldBuilder
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from pxr import Sdf, UsdGeom

from .mapping import ATTR_DISPLAY_NAMES_TABLE as _ATTR_DISPLAY_NAMES_TABLE
from .mapping import DEFAULT_VIRTUAL_XFORM_OPS as _DEFAULT_VIRTUAL_XFORM_OPS
from .mapping import OPS_ATTR_NAME_TABLE as _OPS_ATTR_NAME_TABLE
from .mapping import OPS_ATTR_TYPE_TABLE as _OPS_ATTR_TYPE_TABLE
from .mapping import OPS_UI_ATTR_OP_ORDER_TABLE as _OPS_UI_ATTR_OP_ORDER_TABLE


class TransformPropertyWidget:
    """
    Show a panel that shows transform attributes of a prim.
    If the prim doesn't have any transform (xform) attribute, the panel will find and show the closest parent that has
    those attributes.
    """

    def __init__(
        self,
        context_name: str,
        tree_column_widths: list[ui.Length] = None,
        columns_resizable: bool = False,
        right_aligned_labels: bool = True,
        attr_display_names_table: dict[UsdGeom.XformOp, list[str]] = None,
        virtual_xform_ops: list[list[tuple[list[UsdGeom.XformOp], list[Any]]]] = None,
        field_builders: list[_FieldBuilder] | None = None,
    ):
        """
        Show a panel that shows transform attributes of a prim

        Args:
            context_name: the usd context
            tree_column_widths: the width of the columns in the tree
            columns_resizable: if the columns are resizable
            right_aligned_labels: if the labels are right aligned
            attr_display_names_table: dictionary that set custom display for transform attributes
            virtual_xform_ops: the virtual ops to create if missing.
                               - The top-level array is a list of XForm Groups (Translate, Rotation, Scale, etc.)
                               - Will display 1 per group, first item is chosen as default if the group doesn't exist
                               - Each group item is a tuple of XForm Type list and Default Values List
            field_builders (List[_FieldBuilder])
        """

        self._default_attr = {
            "_context_name": None,
            "_context": None,
            "_tree_column_widths": None,
            "_columns_resizable": None,
            "_right_aligned_labels": None,
            "_root_frame": None,
            "_attr_display_names_table": None,
            "_property_widget": None,
            "_property_model": None,
            "_property_delegate": None,
            "_on_item_changed_sub": None,
            "_on_item_expanded_sub": None,
            "_paths": None,
            "_virtual_ops": None,
            "_has_virtual_ops": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self.__refresh_done = _Event()

        self.__usd_listener_instance = _get_usd_listener_instance()

        self._attr_display_names_table = attr_display_names_table or _ATTR_DISPLAY_NAMES_TABLE

        self._context_name = context_name
        self._context = omni.usd.get_context(context_name)

        self._tree_column_widths = tree_column_widths
        self._columns_resizable = columns_resizable
        self._right_aligned_labels = right_aligned_labels

        self._paths = []
        self._virtual_ops = virtual_xform_ops or _DEFAULT_VIRTUAL_XFORM_OPS
        self._has_virtual_ops = False

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
        self._property_model = _USDPropertyModel(self._context_name)
        self._property_delegate = _USDPropertyDelegate(
            field_builders=field_builders, right_aligned_labels=self._right_aligned_labels
        )
        self._root_frame = ui.Frame(height=0)
        with self._root_frame:
            self._property_widget = _PropertyWidget(
                self._context_name,
                model=self._property_model,
                delegate=self._property_delegate,
                refresh_callback=self.refresh,
                tree_column_widths=self._tree_column_widths,
                columns_resizable=self._columns_resizable,
            )

    def refresh(self, paths: list[str | Sdf.Path] | None = None):
        """
        Refresh the panel with the given prim paths

        Args:
            paths: the USD prim paths to use
        """
        if paths is not None:
            self._paths = paths

        if not self._root_frame or not self._root_frame.visible:
            return

        if self.__usd_listener_instance and self._property_model:
            self.__usd_listener_instance.remove_model(self._property_model)

        stage = self._context.get_stage()
        items = []
        valid_paths = []

        if stage is not None:
            prims = [stage.GetPrimAtPath(path) for path in self._paths]

            attrs_added = {}
            # pre-pass to check valid prims with the attribute
            for prim in prims:
                if not prim.IsValid():
                    continue
                valid_paths.append(prim.GetPath())

                xform = UsdGeom.Xformable(prim)
                xform_ops = xform.GetOrderedXformOps() or []

                for xform_op in xform_ops:
                    attr = xform_op.GetAttr()
                    attr_name = attr.GetName()
                    attrs_added.setdefault((attr_name, xform_op.GetOpType()), []).append(attr)

            num_prims = len(valid_paths)
            for (attr_name, xform_op_type), attrs in attrs_added.items():
                if 1 < len(attrs) != num_prims:
                    continue

                items.append(
                    (
                        xform_op_type,
                        _USDAttributeXformItem(
                            self._context_name,
                            [attr_.GetPath() for attr_ in attrs],
                            display_attr_names=self.__get_xform_custom_name(attr_name),
                        ),
                    )
                )

            if num_prims == 1:
                prim = stage.GetPrimAtPath(valid_paths[0])
                xform = UsdGeom.Xformable(prim)
                xform_ops = xform.GetOrderedXformOps() or []
                virtual_items = self._get_virtual_xform_ops(prim, [op.GetOpType() for op in xform_ops])
                self._has_virtual_ops = bool(virtual_items)
                items.extend(virtual_items)

            items.sort(key=lambda i: _OPS_UI_ATTR_OP_ORDER_TABLE.get(i[0], float("inf")))

        self._property_model.set_prim_paths(valid_paths)
        self._property_model.set_items([i for (_, i) in items])
        self.__usd_listener_instance.add_model(self._property_model)
        self._refresh_done()

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

    @property
    def visible(self):
        return self._root_frame.visible

    def _get_virtual_xform_ops(self, prim, xform_op_types):
        if not self._virtual_ops:
            return []

        ops_to_create = _filter_virtual_attributes(self._virtual_ops, xform_op_types)

        if not ops_to_create:
            return []

        attr_defs: dict[UsdGeom.XformOp, _USDAttributeDef] = {}

        # For xforms we always want to be creating the full set whenever an override is authored.
        # First loop through the existing op types and create attr defs.
        for op in xform_op_types:
            attr_name = _OPS_ATTR_NAME_TABLE.get(op, None)
            if not attr_name:
                continue
            attr_type = _OPS_ATTR_TYPE_TABLE.get(op, None)
            if not attr_type:
                continue
            attr = prim.GetAttribute(attr_name)
            attr_defs[op] = _USDAttributeDef(
                attr.GetPath(),
                attr_type,
                op,
                value=attr.Get(),
                exists=True,
            )

        # Next we can loop through the ops we need to create.
        for op, val in ops_to_create:
            attr_name = _OPS_ATTR_NAME_TABLE.get(op, None)
            if not attr_name:
                continue
            attr_type = _OPS_ATTR_TYPE_TABLE.get(op, None)
            if not attr_type:
                continue

            attr_defs[op] = _USDAttributeDef(
                prim.GetPath().AppendProperty(attr_name),
                attr_type,
                op,
                value=val,
                exists=False,
            )

        if not attr_defs:
            return []

        stub_item = _USDAttributeXformItemStub(
            "Transforms",
            self._context_name,
            # Attributes are created in the order they are provided.
            sorted(attr_defs.values(), key=lambda d: _OPS_UI_ATTR_OP_ORDER_TABLE.get(d.op, float("inf"))),
        )
        return [(tuple(attr_defs.keys()), stub_item)]

    def __get_xform_custom_name(self, attr_name):
        for a_type, a_name in self._attr_display_names_table.items():
            if attr_name == a_type:
                return a_name
        return None

    def destroy(self):
        if self._root_frame:
            self._root_frame.clear()
        if self.__usd_listener_instance and self._property_model:
            self.__usd_listener_instance.remove_model(self._property_model)
        _reset_default_attrs(self)
        self.__usd_listener_instance = None

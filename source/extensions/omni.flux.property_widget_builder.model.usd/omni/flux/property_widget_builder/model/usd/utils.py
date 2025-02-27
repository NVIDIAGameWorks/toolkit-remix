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

import asyncio
from typing import Any, Dict, List, Tuple, Union

from omni import kit, usd
from omni.kit.usd.layers import LayerUtils as _LayerUtils
from omni.usd.commands import remove_prim_spec as _remove_prim_spec
from pxr import Sdf, Usd

from .mapping import DEFAULT_VALUE_TABLE


def get_type_name(metadata: Dict[Any, Any]) -> Sdf.ValueTypeName:
    """
    Get the type name of an attribute

    Args:
        metadata: the metadata of an attribute

    Returns:
        The type name
    """
    type_name = metadata.get(Sdf.PrimSpec.TypeNameKey, "unknown type")
    return Sdf.ValueTypeNames.Find(type_name)


def get_metadata(context_name: str, attribute_paths: List[Union[str, Sdf.Path]]) -> Dict[Any, Any]:
    """
    Get the metadata of a list of attributes

    Args:
        context_name: current context name
        attribute_paths: the attributes to get the metadata from

    Returns:

    """
    stage = usd.get_context(context_name).get_stage()
    if stage is None:
        return {}

    for attribute_path in attribute_paths:
        prim = stage.GetPrimAtPath(attribute_path.GetPrimPath())
        if prim.IsValid():
            attr = prim.GetAttribute(attribute_path.name)
            if attr.IsValid():
                return attr.GetAllMetadata()
    return {}


def is_item_overriden(stage, attributes):
    if not stage or not attributes:
        return False
    sub_layers = _LayerUtils.get_all_sublayers(stage, include_session_layers=True, include_anonymous_layers=False)
    for attribute in attributes:
        root_layer = stage.GetRootLayer()
        if not attribute.IsValid():
            continue
        stack = attribute.GetPropertyStack(Usd.TimeCode.Default())
        for stack_item in stack:
            if stack_item.layer.identifier in sub_layers and stack_item.layer.identifier != root_layer.identifier:
                return True
    return False


def get_item_attributes(stage, attribute_paths):
    """Get the USD Attributes"""
    attributes = []
    for attribute_path in attribute_paths:
        prim = stage.GetPrimAtPath(attribute_path.GetPrimPath())
        if prim.IsValid():
            attributes.append(prim.GetAttribute(attribute_path.name))
    return attributes


def get_default_attribute_value(attribute):
    default_value = DEFAULT_VALUE_TABLE.get(attribute.GetName())
    if default_value is not None:
        return default_value

    if not isinstance(attribute, Usd.Attribute):
        return None

    custom = attribute.GetCustomData()
    if "default" in custom:
        return custom["default"]

    prim_definition = attribute.GetPrim().GetPrimDefinition()
    prop_spec = prim_definition.GetSchemaPropertySpec(attribute.GetPath().name)
    if prop_spec and prop_spec.default is not None:
        return prop_spec.default

    # If we still don't find default value, use type's default value
    value_type = attribute.GetTypeName()
    return value_type.defaultValue


def delete_all_overrides(attribute, context_name=""):
    for stack_item in attribute.GetPropertyStack(Usd.TimeCode.Default()):
        delete_layer_override(stack_item.layer, attribute, context_name=context_name)


def delete_layer_override(layer, attribute, context_name=""):
    asyncio.ensure_future(delete_layer_override_async(layer, attribute, context_name=context_name))


@usd.handle_exception
async def delete_layer_override_async(layer, attribute, context_name=""):
    # Only delete properties on unlocked layers
    if usd.is_layer_locked(usd.get_context(context_name), layer.identifier):
        return

    # TODO Feature OM-67061 - Replace with a command
    prim_spec = layer.GetPrimAtPath(attribute.GetPrimPath())
    if prim_spec is None:
        return
    prop_spec = layer.GetPropertyAtPath(attribute.GetPath())
    if not prop_spec:
        return
    prim_spec.RemoveProperty(prop_spec)

    # Wait 1 frame before cleaning up the prims
    await kit.app.get_app().next_update_async()

    # Cleanup empty prims
    def cleanup_prims_recursive(spec):
        # If the prim has no properties and children, it can be cleaned up
        if not spec or spec.properties or spec.nameChildren:
            return
        parent = spec.nameParent
        _remove_prim_spec(layer, spec.path)
        cleanup_prims_recursive(parent)

    cleanup_prims_recursive(prim_spec)


def filter_virtual_attributes(virtual_attrs: List[List[Tuple[List[Any], List[Any]]]], existing_attrs: List[Any]):
    """
    Figure out the virtual attributes to create and which ones already exist

    Note: Attribute Names don't necessarily have to be used. As long as the type of the items of first element
    of the tuples matches the type of the items in the existing_attrs list, the filtering will work.

    Args:
        virtual_attrs: the minimal sets of attributes to display.
            - Will display 1 per group, first item is chosen as default if the group doesn't exist
            - Each group item is a tuple of (Attribute Name List, Default Values List)
        existing_attrs: list of Attribute Names that exist on the prim
    """
    attrs_to_create = []
    for attr_group in virtual_attrs:
        existing_group = None
        for attr in attr_group:
            for attr_name in attr[0]:
                if attr_name in existing_attrs:
                    existing_group = attr
                    break
            if existing_group is not None:
                break
        # If the group exists, make sure every component of the group exists
        if existing_group is not None:
            group_attrs, group_vals = existing_group
            for index, attr_name in enumerate(group_attrs):
                if attr_name in existing_attrs:
                    continue
                attrs_to_create.append((attr_name, group_vals[index]))
        # If the group doesn't exist, create the default op for that group (first entry)
        else:
            default_attrs, default_vals = attr_group[0]
            for index, attr in enumerate(default_attrs):
                attrs_to_create.append((attr, default_vals[index]))
    return attrs_to_create

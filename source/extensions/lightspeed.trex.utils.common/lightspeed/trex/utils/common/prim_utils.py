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

__all__ = [
    "PrimTypes",
    "get_prim_paths",
    "filter_prims_paths",
    "is_light_prototype",
    "is_material_prototype",
    "is_shader_prototype",
    "is_mesh_prototype",
    "is_instance",
    "get_extended_selection",
    "get_children_prims",
]

import re
from enum import Enum
from typing import Callable, List, Tuple

import omni.usd
from lightspeed.common import constants
from pxr import Sdf, Usd, UsdGeom, UsdLux, UsdShade


class PrimTypes(Enum):
    LIGHTS = "lights"
    MATERIALS = "materials"
    MODELS = "models"


def get_prim_paths(
    asset_hashes: set[str] = None,
    prim_type: PrimTypes = None,
    selection: list[str] | None = None,
    filter_session_prims: bool = True,
    layer_id: str = None,
    exists: bool = True,
    context_name: str = "",
) -> list[str]:
    """
    Get the list of prim paths of a given type in the stage or current selection

    Args:
        asset_hashes: A set of hashes to filter for
        prim_type: The type of prim to fetch
        selection: Current stage selection. If not set, all the prim paths in the stage will be used.
        filter_session_prims: Whether to filter out prims defined on the session prim or not
        layer_id: Look for assets that exists or not on a given layer. Use the `exists` query parameter to set whether
                  existing or non-existing prims should be returned.
        exists: Filter an asset if it exists or not on a given layer. Use in conjunction with `layer_identifier` to
                filter on a given layer, otherwise this parameter will be ignored.
        context_name: Context name for the stage to get prim paths from

    Returns:
        A list of prims paths
    """
    if prim_type is not None:
        match prim_type:
            case PrimTypes.LIGHTS:
                return filter_prims_paths(
                    lambda prim: is_light_prototype(prim) and includes_hash(prim, asset_hashes),
                    prim_paths=selection,
                    filter_session_prims=filter_session_prims,
                    layer_id=layer_id,
                    exists=exists,
                    context_name=context_name,
                )
            case PrimTypes.MATERIALS:
                return filter_prims_paths(
                    lambda prim: is_material_prototype(prim) and includes_hash(prim, asset_hashes),
                    prim_paths=selection,
                    filter_session_prims=filter_session_prims,
                    layer_id=layer_id,
                    exists=exists,
                    context_name=context_name,
                )
            case PrimTypes.MODELS:
                return filter_prims_paths(
                    lambda prim: is_mesh_prototype(prim) and includes_hash(prim, asset_hashes),
                    prim_paths=selection,
                    filter_session_prims=filter_session_prims,
                    layer_id=layer_id,
                    exists=exists,
                    context_name=context_name,
                )

    # All types
    return filter_prims_paths(
        lambda prim: (
            (is_light_prototype(prim) or is_material_prototype(prim) or is_mesh_prototype(prim))
            and includes_hash(prim, asset_hashes)
        ),
        prim_paths=selection,
        filter_session_prims=filter_session_prims,
        layer_id=layer_id,
        exists=exists,
        context_name=context_name,
    )


def filter_prims_paths(
    predicate: Callable[["Usd.Prim"], bool],
    prim_paths: list[str] | None = None,
    filter_session_prims: bool = False,
    layer_id: str | None = None,
    exists: bool = True,
    context_name: str = "",
) -> list[str]:
    """
    Get the list of prim paths that match the given predicate in the stage or current selection

    Args:
        predicate: The predicate to match prims
        prim_paths: The list of prim paths to filter. If not set, all the prim paths in the stage will be used
        filter_session_prims: Whether to filter out prims defined on the session prim or not
        layer_id: Look for assets that exists or not on a given layer. Use the `exists` query parameter to set whether
                  existing or non-existing prims should be returned.
        exists: Filter an asset if it exists or not on a given layer. Use in conjunction with `layer_identifier` to
                filter on a given layer, otherwise this parameter will be ignored.
        context_name: Context name for the stage to get prim paths from

    Returns:
        A list of prims paths
    """

    context = omni.usd.get_context(context_name)
    stage = context.get_stage()
    session_layer = stage.GetSessionLayer()

    if prim_paths is not None:
        prims = [stage.GetPrimAtPath(path) for path in prim_paths]
    else:
        prims = stage.TraverseAll()

    def layer_predicate(prim: Usd.Prim) -> bool:
        is_valid = True
        # If we're filtering session prims and the prim exists on the session layer, it's not valid
        if filter_session_prims and session_layer.GetPrimAtPath(prim.GetPath()):
            is_valid = False
        # If we're filtering for a given layer, make sure the prim spec exists/doesn't exist on the layer
        if layer_id is not None:
            layer = Sdf.Layer.FindOrOpen(layer_id)
            # If the layer doesn't exist, just ignore the filter
            if not layer:
                return is_valid
            introducing_layer, _ = omni.usd.get_introducing_layer(prim)
            if exists:
                is_valid = bool(layer.GetPrimAtPath(prim.GetPath())) or (layer == introducing_layer)
            else:
                is_valid = not bool(layer.GetPrimAtPath(prim.GetPath())) and (layer != introducing_layer)
        return is_valid

    filtered_paths = [str(prim.GetPath()) for prim in prims if layer_predicate(prim) and predicate(prim)]

    return filtered_paths


def includes_hash(prim: "Usd.Prim", asset_hashes: set[str]) -> bool:
    """
    Returns:
        Whether the prim can be found in the set of hashes or not
    """
    if not prim:
        return False
    if asset_hashes is None:
        return True
    return bool(any(True for asset_hash in asset_hashes if asset_hash in str(prim.GetPath())))


def is_light_prototype(prim: "Usd.Prim") -> bool:
    """
    Returns:
        Whether the prims is a light prototype prim or not
    """
    if not prim:
        return False
    return bool(
        (prim.HasAPI(UsdLux.LightAPI) if hasattr(UsdLux, "LightAPI") else prim.IsA(UsdLux.Light))
        and not is_instance(prim)
    )


def is_material_prototype(prim: "Usd.Prim") -> bool:
    """
    Returns:
        Whether the prim is a material or not
    """
    if not prim:
        return False
    return bool(prim.IsA(UsdShade.Material) and not is_instance(prim))


def is_shader_prototype(prim: "Usd.Prim") -> bool:
    """
    Returns:
        Whether the prim is a material prototype prim or not
    """
    if not prim:
        return False
    return bool(prim.IsA(UsdShade.Shader) and not is_instance(prim))


def is_mesh_prototype(prim: "Usd.Prim") -> bool:
    """
    Returns:
        Whether the prim is a mesh prototype prim or not
    """
    if not prim:
        return False
    return bool(
        re.match(constants.REGEX_IN_MESH_PATH, str(prim.GetPath()))
        and (prim.IsA(UsdGeom.Subset) or prim.IsA(UsdGeom.Mesh))
    )


def is_instance(prim: "Usd.Prim") -> bool:
    """
    Returns:
        Whether the prim is an instance prim or not
    """
    if not prim:
        return False
    return bool(re.match(constants.REGEX_IN_INSTANCE_PATH, str(prim.GetPath())))


def get_extended_selection(context_name: str = "") -> list[str]:
    """
    Get the current selection and related prims.
    - If an instance is selected, select the mesh, material, and shader associated to it
    - If a mesh is selection, select the material, and shader associated to it
    - If a material is selected, select the shader associated to it
    - Select all children prims that are meshes, materials, shaders or lights
    """
    context = omni.usd.get_context(context_name)
    stage = context.get_stage()

    selection = set()
    selection = selection.union(context.get_selection().get_selected_prim_paths())

    # Expand the selection to get meshes, materials and shaders from instances
    selection_size = -1
    while len(selection) != selection_size:
        selection_size = len(selection)
        for path in selection.copy():
            prim = stage.GetPrimAtPath(path)
            if not prim:
                continue

            selection = selection.union([str(p.GetPath()) for p in get_children_prims(prim)])

            if is_instance(prim):
                # Get mesh from instance
                selection.add(str(constants.COMPILED_REGEX_INSTANCE_TO_MESH_SUB.sub(rf"{constants.MESH_PATH}\2", path)))
            elif is_mesh_prototype(prim):
                # Get material from mesh
                material, _ = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
                selection.add(str(material.GetPrim().GetPath()))
                # Get children prims
            elif is_material_prototype(prim):
                # Get shader from material
                selection.add(str(omni.usd.get_shader_from_material(prim, True).GetPath()))

    return list(selection)


def get_children_prims(
    prim: "Usd.Prim",
    from_reference_layer_path: str = None,
    level: int | None = None,
    skip_remix_ref: bool = False,
    only_prim_not_from_ref: bool = False,
) -> list["Usd.Prim"]:
    """
    Get all children prims for any given prim.

    Args:
        prim: Prim to get children from
        from_reference_layer_path: Reference layer path
        level: Recursive level to get children from
        skip_remix_ref: Whether to skip remix references or not
        only_prim_not_from_ref: Whether to only get children prims not from reference
    """
    current_level = 0

    def get_parent_ref_layers(_prim) -> list[str]:
        refs_and_layers = omni.usd.get_composed_references_from_prim(_prim)
        result = []
        if refs_and_layers:
            for ref, layer in refs_and_layers:
                if not ref.assetPath:
                    continue
                result.append(omni.client.normalize_url(layer.ComputeAbsolutePath(ref.assetPath)))
        parent = _prim.GetParent()
        if parent and parent.IsValid():
            result.extend(get_parent_ref_layers(parent))
        return result

    def traverse_instanced_children(_prim, _current_level, _skip_remix_ref):
        if level is not None and _current_level == level:
            return
        _current_level += 1
        for child in _prim.GetFilteredChildren(Usd.PrimAllPrimsPredicate):
            # it can happen that we added the same reference multiple time. But USD can't do that.
            # As a workaround, we had to create a xform child and add the reference to it.
            # Check the children and find the attribute that define that
            is_remix_ref = False
            if _skip_remix_ref:
                is_remix_ref = child.GetAttribute(constants.IS_REMIX_REF_ATTR)
                if is_remix_ref.IsValid():
                    _current_level -= 1

            layer_stack = [omni.client.normalize_url(stack.layer.realPath) for stack in child.GetPrimStack()]
            if only_prim_not_from_ref and set(layer_stack).intersection(set(get_parent_ref_layers(_prim))):
                yield from traverse_instanced_children(child, _current_level, _skip_remix_ref)
                continue

            if (
                from_reference_layer_path is not None
                and not only_prim_not_from_ref
                and from_reference_layer_path not in layer_stack
            ):
                yield from traverse_instanced_children(child, _current_level, _skip_remix_ref)
                continue
            if not is_remix_ref:
                yield child
            yield from traverse_instanced_children(child, _current_level, _skip_remix_ref)

    return list(traverse_instanced_children(prim, current_level, skip_remix_ref))


def get_reference_file_paths(prim) -> Tuple[List[Tuple["Usd.Prim", "Sdf.Reference", "Sdf.Layer", int]], int]:
    """
    Collects file references from a USD prim and its reference children.
    Handles special child prims for multiple identical references.

    Args:
        prim (Usd.Prim): The USD prim to get references from.

    Returns:
        Tuple[List[Tuple[Usd.Prim, Sdf.Reference, Sdf.Layer, int]], int]:
            List of (prim, reference, layer, index) tuples and total reference count.
    """
    prim_paths = []
    ref_and_layers = omni.usd.get_composed_references_from_prim(prim, False)
    i = 0
    for ref, layer in ref_and_layers:
        if not ref.assetPath:
            continue
        prim_paths.append((prim, ref, layer, i))
        i += 1

    # It can happen that we added the same reference multiple time. But USD can't do that.
    # As a workaround, we had to create a xform child and add the reference to it.
    # Check the children and find the attribute that define that
    for child in prim.GetChildren():
        is_remix_ref = child.GetAttribute(constants.IS_REMIX_REF_ATTR)
        if is_remix_ref.IsValid():
            ref_and_layers = omni.usd.get_composed_references_from_prim(child, False)
            for ref, layer in ref_and_layers:
                if not ref.assetPath:
                    continue
                prim_paths.append((child, ref, layer, i))
                i += 1

    return prim_paths, i

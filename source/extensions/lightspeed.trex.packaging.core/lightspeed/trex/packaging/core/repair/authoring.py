"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = ["RepairAuthoringCore"]

import carb
import omni.client
from lightspeed.trex.asset_replacements.core.shared import Setup as AssetReplacementsCore
from omni.flux.utils.common.omni_url import OmniUrl
from pxr import Sdf

from .layers import RepairLayerCore

_REFERENCE_LIST_ITEM_TYPES = (
    Sdf.ListOpTypeExplicit,
    Sdf.ListOpTypePrepended,
    Sdf.ListOpTypeAppended,
    Sdf.ListOpTypeAdded,
)
_REFERENCE_LIST_ALL_TYPES = (*_REFERENCE_LIST_ITEM_TYPES, Sdf.ListOpTypeDeleted, Sdf.ListOpTypeOrdered)


class RepairAuthoringCore:
    """
    Sdf authoring helpers for reference and texture repair opinions.
    """

    def __init__(
        self,
        asset_core: AssetReplacementsCore,
        layer_core: RepairLayerCore,
    ):
        """Initialize the authoring helper.

        Args:
            asset_core: Asset replacement core used for default-prim metadata helpers.
            layer_core: Layer helper used for path resolution.
        """
        self._asset_core = asset_core
        self._layers = layer_core

    def replace_reference_opinion(
        self,
        should_author_override: bool,
        repair_layer: Sdf.Layer,
        source_repair_layer_identifier: str,
        target_layer_identifier: str,
        prim_path: Sdf.Path,
        current_ref: Sdf.Reference,
        fixed_asset_path: str,
    ) -> bool:
        """Replace an authored reference opinion.

        Args:
            should_author_override: Whether to author an override instead of editing the original list item.
            repair_layer: Layer receiving the repair opinion.
            source_repair_layer_identifier: Identifier for the repair layer.
            target_layer_identifier: Identifier for the layer that owns the unresolved reference.
            prim_path: Prim path that authors the reference.
            current_ref: Current authored reference.
            fixed_asset_path: Replacement asset path.

        Returns:
            Whether a repair opinion was authored.
        """
        new_ref = self._build_replacement_reference(
            source_repair_layer_identifier,
            target_layer_identifier,
            current_ref,
            fixed_asset_path,
        )

        prim_spec = self._ensure_prim_spec(repair_layer, prim_path)
        if should_author_override:
            self._set_explicit_reference_list(prim_spec, [new_ref])
            return True

        if current_ref == new_ref:
            carb.log_info(f"Reference {current_ref.assetPath} was not replaced")
            return False
        return self._replace_reference_list_item(prim_spec, current_ref, new_ref)

    def replace_reference_override(
        self,
        repair_layer: Sdf.Layer,
        repair_layer_identifier: str,
        target_layer_identifier: str,
        prim_path: Sdf.Path,
        authored_references: list[tuple[Sdf.Path, Sdf.Reference]],
        asset_path: str,
        fixed_asset_path: str,
    ) -> bool:
        """Author a local override that replaces a referenced-layer reference.

        Args:
            repair_layer: Layer receiving the repair opinion.
            repair_layer_identifier: Identifier for the repair layer.
            target_layer_identifier: Identifier for the referenced layer that owns the unresolved reference.
            prim_path: Local override prim path to author.
            authored_references: References from the target layer to mirror into the override.
            asset_path: Unresolved asset path to replace.
            fixed_asset_path: Replacement asset path.

        Returns:
            Whether a replacement override was authored.
        """
        references = []
        replaced_reference = False
        asset_path_key = OmniUrl(asset_path).path.lower()
        for _authored_prim_path, reference in authored_references:
            if (
                OmniUrl(
                    self._layers.compute_absolute_path_from_identifier(target_layer_identifier, reference.assetPath)
                ).path.lower()
                == asset_path_key
            ):
                references.append(
                    self._build_replacement_reference(
                        repair_layer_identifier,
                        target_layer_identifier,
                        reference,
                        fixed_asset_path,
                    )
                )
                replaced_reference = True
                continue
            references.append(
                self._make_reference_relative_to_layer_identifier(
                    target_layer_identifier, repair_layer_identifier, reference
                )
            )
        if not replaced_reference:
            return False

        prim_spec = self._ensure_prim_spec(repair_layer, prim_path)
        self._set_explicit_reference_list(prim_spec, references)
        return True

    def remove_reference_override(
        self,
        repair_layer: Sdf.Layer,
        repair_layer_identifier: str,
        target_layer_identifier: str,
        prim_path: Sdf.Path,
        authored_references: list[tuple[Sdf.Path, Sdf.Reference]],
        asset_path: str,
    ) -> bool:
        """Author a local override that removes a referenced-layer reference.

        Args:
            repair_layer: Layer receiving the repair opinion.
            repair_layer_identifier: Identifier for the repair layer.
            target_layer_identifier: Identifier for the referenced layer that owns the unresolved reference.
            prim_path: Local override prim path to author.
            authored_references: References from the target layer to mirror into the override.
            asset_path: Unresolved asset path to remove.

        Returns:
            Whether a removal override was authored.
        """
        references = []
        removed_reference = False
        asset_path_key = OmniUrl(asset_path).path.lower()
        for _authored_prim_path, reference in authored_references:
            if (
                OmniUrl(
                    self._layers.compute_absolute_path_from_identifier(target_layer_identifier, reference.assetPath)
                ).path.lower()
                == asset_path_key
            ):
                removed_reference = True
                continue
            references.append(
                self._make_reference_relative_to_layer_identifier(
                    target_layer_identifier, repair_layer_identifier, reference
                )
            )
        if not removed_reference:
            return False

        prim_spec = self._ensure_prim_spec(repair_layer, prim_path)
        self._set_explicit_reference_list(prim_spec, references)
        return True

    def _build_replacement_reference(
        self,
        repair_layer_identifier: str,
        target_layer_identifier: str,
        current_ref: Sdf.Reference,
        fixed_asset_path: str,
    ) -> Sdf.Reference:
        new_ref_asset_path = self._make_asset_path_relative_to_layer_identifier(
            repair_layer_identifier, fixed_asset_path
        )
        new_ref_prim_path = self._get_reference_prim_path_from_asset_path(
            new_ref_asset_path, target_layer_identifier, repair_layer_identifier, current_ref
        )
        return Sdf.Reference(
            assetPath=new_ref_asset_path.replace("\\", "/"),
            primPath=(
                Sdf.Path()
                if self._asset_core.ref_prim_path_is_default_prim(new_ref_prim_path)
                else Sdf.Path(new_ref_prim_path)
            ),
            layerOffset=current_ref.layerOffset,
        )

    def _make_reference_relative_to_layer_identifier(
        self, source_layer_identifier: str, target_layer_identifier: str, reference: Sdf.Reference
    ) -> Sdf.Reference:
        asset_path = reference.assetPath
        if asset_path:
            asset_path = self._make_asset_path_relative_to_layer_identifier(
                target_layer_identifier,
                self._layers.compute_absolute_path_from_identifier(source_layer_identifier, asset_path),
            )
        return Sdf.Reference(
            assetPath=asset_path.replace("\\", "/"),
            primPath=reference.primPath,
            layerOffset=reference.layerOffset,
        )

    def replace_texture_opinion(
        self,
        repair_layer: Sdf.Layer,
        repair_layer_identifier: str,
        texture_attr_path: str,
        texture_value: str,
    ) -> bool:
        """Author a replacement texture asset opinion.

        Args:
            repair_layer: Layer receiving the repair opinion.
            repair_layer_identifier: Identifier for the repair layer.
            texture_attr_path: Texture attribute path to author.
            texture_value: Replacement texture path.

        Returns:
            Whether a replacement opinion was authored.
        """
        attr_path = Sdf.Path(texture_attr_path)
        prim_spec = self._ensure_prim_spec(repair_layer, attr_path.GetPrimPath())
        attr_spec = repair_layer.GetPropertyAtPath(attr_path)
        if not attr_spec:
            attr_spec = Sdf.AttributeSpec(prim_spec, attr_path.name, Sdf.ValueTypeNames.Asset)
        attr_spec.default = Sdf.AssetPath(
            self._make_asset_path_relative_to_layer_identifier(repair_layer_identifier, texture_value)
        )
        return True

    @staticmethod
    def _make_asset_path_relative_to_layer_identifier(layer_identifier: str, asset_path: str) -> str:
        return omni.client.make_relative_url(layer_identifier, asset_path).replace("\\", "/")

    def _get_reference_prim_path_from_asset_path(
        self, new_asset_path: str, target_layer_identifier: str, repair_layer_identifier: str, ref: Sdf.Reference
    ) -> str:
        abs_new_asset_path = omni.client.normalize_url(
            self._layers.compute_absolute_path_from_identifier(repair_layer_identifier, new_asset_path)
        )
        abs_asset_path = omni.client.normalize_url(
            self._layers.compute_absolute_path_from_identifier(target_layer_identifier, ref.assetPath)
        )
        if abs_new_asset_path == abs_asset_path and ref.primPath:
            return str(ref.primPath)
        if abs_new_asset_path == abs_asset_path and not ref.primPath:
            return self._asset_core.get_ref_default_prim_tag()

        ref_layer = Sdf.Layer.FindOrOpen(abs_new_asset_path)
        if ref_layer and ref_layer.defaultPrim:
            return self._asset_core.get_ref_default_prim_tag()
        return str(ref.primPath)

    @staticmethod
    def _ensure_prim_spec(layer: Sdf.Layer, prim_path: Sdf.Path) -> Sdf.PrimSpec:
        prim_spec = layer.GetPrimAtPath(prim_path)
        if prim_spec:
            return prim_spec
        prim_spec = Sdf.CreatePrimInLayer(layer, prim_path)
        prim_spec.specifier = Sdf.SpecifierOver
        return prim_spec

    @staticmethod
    def _set_explicit_reference_list(prim_spec: Sdf.PrimSpec, references: list[Sdf.Reference]):
        # Repairs write deterministic replacement opinions, so list-op entries are collapsed to an explicit list.
        reference_list_op = Sdf.ReferenceListOp()
        reference_list_op.explicitItems = references
        prim_spec.SetInfo(Sdf.PrimSpec.ReferencesKey, reference_list_op)

    @classmethod
    def _replace_reference_list_item(
        cls, prim_spec: Sdf.PrimSpec, current_ref: Sdf.Reference, new_ref: Sdf.Reference
    ) -> bool:
        reference_list_op = cls._get_reference_list_op(prim_spec)
        for list_op_type in _REFERENCE_LIST_ITEM_TYPES:
            references = cls._get_reference_list_items(reference_list_op, list_op_type)
            if current_ref not in references:
                continue
            cls._set_reference_list_items(
                reference_list_op, list_op_type, [new_ref if ref == current_ref else ref for ref in references]
            )
            prim_spec.SetInfo(Sdf.PrimSpec.ReferencesKey, reference_list_op)
            return True

        return False

    @staticmethod
    def _get_reference_list_op(prim_spec: Sdf.PrimSpec) -> Sdf.ReferenceListOp:
        reference_list_op = prim_spec.GetInfo(Sdf.PrimSpec.ReferencesKey)
        if isinstance(reference_list_op, Sdf.ReferenceListOp):
            return reference_list_op

        reference_list_op = Sdf.ReferenceListOp()
        reference_list_op.prependedItems = list(prim_spec.referenceList.GetAddedOrExplicitItems())
        return reference_list_op

    @classmethod
    def _reference_list_op_is_empty(cls, reference_list_op: Sdf.ReferenceListOp) -> bool:
        return not any(
            cls._get_reference_list_items(reference_list_op, list_op_type) for list_op_type in _REFERENCE_LIST_ALL_TYPES
        )

    @staticmethod
    def _get_reference_list_items(
        reference_list_op: Sdf.ReferenceListOp, list_op_type: Sdf.ListOpType
    ) -> list[Sdf.Reference]:
        if list_op_type == Sdf.ListOpTypeExplicit:
            return list(reference_list_op.explicitItems)
        if list_op_type == Sdf.ListOpTypePrepended:
            return list(reference_list_op.prependedItems)
        if list_op_type == Sdf.ListOpTypeAppended:
            return list(reference_list_op.appendedItems)
        if list_op_type == Sdf.ListOpTypeAdded:
            return list(reference_list_op.addedItems)
        if list_op_type == Sdf.ListOpTypeDeleted:
            return list(reference_list_op.deletedItems)
        if list_op_type == Sdf.ListOpTypeOrdered:
            return list(reference_list_op.orderedItems)
        raise ValueError(f"Unsupported reference list operation type: {list_op_type}")

    @staticmethod
    def _set_reference_list_items(
        reference_list_op: Sdf.ReferenceListOp, list_op_type: Sdf.ListOpType, references: list[Sdf.Reference]
    ):
        if list_op_type == Sdf.ListOpTypeExplicit:
            reference_list_op.explicitItems = references
            return
        if list_op_type == Sdf.ListOpTypePrepended:
            reference_list_op.prependedItems = references
            return
        if list_op_type == Sdf.ListOpTypeAppended:
            reference_list_op.appendedItems = references
            return
        if list_op_type == Sdf.ListOpTypeAdded:
            reference_list_op.addedItems = references
            return
        if list_op_type == Sdf.ListOpTypeDeleted:
            reference_list_op.deletedItems = references
            return
        if list_op_type == Sdf.ListOpTypeOrdered:
            reference_list_op.orderedItems = references
            return
        raise ValueError(f"Unsupported reference list operation type: {list_op_type}")

    def remove_reference_opinion(
        self, should_author_override: bool, layer: Sdf.Layer, prim_path: Sdf.Path, current_ref: Sdf.Reference
    ) -> bool:
        """Remove an authored reference opinion.

        Args:
            should_author_override: Whether to author an override instead of editing the original list item.
            layer: Layer receiving the repair opinion.
            prim_path: Prim path that authors the reference.
            current_ref: Current authored reference.

        Returns:
            Whether a reference opinion was removed.
        """
        if should_author_override:
            prim_spec = self._ensure_prim_spec(layer, prim_path)
            self._set_explicit_reference_list(prim_spec, [])
            return True

        prim_spec = layer.GetPrimAtPath(prim_path)
        if not prim_spec:
            return False

        reference_list_op = self._get_reference_list_op(prim_spec)
        for list_op_type in _REFERENCE_LIST_ITEM_TYPES:
            references = self._get_reference_list_items(reference_list_op, list_op_type)
            if current_ref not in references:
                continue
            self._set_reference_list_items(
                reference_list_op, list_op_type, [ref for ref in references if ref != current_ref]
            )
            break
        else:
            return False

        if self._reference_list_op_is_empty(reference_list_op):
            prim_spec.ClearInfo(Sdf.PrimSpec.ReferencesKey)
        else:
            prim_spec.SetInfo(Sdf.PrimSpec.ReferencesKey, reference_list_op)
        return True

    def remove_texture_opinion(
        self, should_author_override: bool, layer: Sdf.Layer, texture_attr_path: Sdf.Path
    ) -> bool:
        """Remove or block an authored texture asset opinion.

        Args:
            should_author_override: Whether to block with a value block instead of removing the original opinion.
            layer: Layer receiving the repair opinion.
            texture_attr_path: Texture attribute path to remove or block.

        Returns:
            Whether a texture opinion was authored or removed.
        """
        prim_path = texture_attr_path.GetPrimPath()
        if should_author_override:
            prim_spec = self._ensure_prim_spec(layer, prim_path)
            attr_spec = layer.GetPropertyAtPath(texture_attr_path)
            if not attr_spec:
                attr_spec = Sdf.AttributeSpec(prim_spec, texture_attr_path.name, Sdf.ValueTypeNames.Asset)
            attr_spec.default = Sdf.ValueBlock()
            return True

        prim_spec = layer.GetPrimAtPath(prim_path)
        if not prim_spec:
            return False
        prop_spec = layer.GetPropertyAtPath(texture_attr_path)
        if prop_spec:
            prim_spec.RemoveProperty(prop_spec)
            return True
        return False

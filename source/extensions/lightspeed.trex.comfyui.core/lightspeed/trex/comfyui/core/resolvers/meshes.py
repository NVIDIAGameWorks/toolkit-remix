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

__all__ = ["AllStageMeshesResolver", "SelectedMeshResolver", "is_remix_reference"]

import dataclasses
from collections.abc import Iterator
from typing import ClassVar

from lightspeed.common.constants import IS_REMIX_REF_ATTR
from lightspeed.trex.asset_replacements.core.shared.data_models import AssetReplacementsValidators
from pxr import Sdf, Usd

from ..enums import MeshReferenceSelection, RemixType
from .base import ResolverParameter, ResolverValueError, StageExpandingResolver, ValueResolver

OwnedReference = tuple[Usd.Prim, Sdf.Reference, Sdf.Layer]


def is_remix_reference(prim: Usd.Prim) -> bool:
    """Return whether one prim is a marked Remix reference child (``ref_<id>``)."""
    return prim.GetAttribute(IS_REMIX_REF_ATTR).Get() is True


@dataclasses.dataclass
class SelectedMeshResolver(ValueResolver[str]):
    """Resolve the model file of the selected prim from its one external reference.

    The resolver needs an explicit USD context name. Without one it raises rather than guessing a stage.
    """

    label: ClassVar[str] = "Selected Mesh"
    remix_types: ClassVar[tuple[RemixType, ...]] = (RemixType.MESH_FILE_PATH,)

    reference_selection: MeshReferenceSelection = MeshReferenceSelection.SELECTED

    @property
    def parameters(self) -> tuple[ResolverParameter[MeshReferenceSelection], ...]:
        """Return the editable reference selection binding."""
        return (
            ResolverParameter(
                "reference_selection",
                MeshReferenceSelection,
                lambda: self.reference_selection,
                self._set_reference_selection,
                tuple(MeshReferenceSelection),
                "Reference Selection",
                tooltip="All references of the mesh, or only the reference that composes the selected prim.",
            ),
        )

    def _set_reference_selection(self, value: MeshReferenceSelection) -> None:
        """Store the reference selection chosen by the user."""
        self.reference_selection = value

    def __call__(self, prim: Usd.Prim) -> str:
        """Resolve exactly one external model reference.

        Args:
            prim: Selected prim whose introducing reference supplies the model.

        Returns:
            URL-preserving resolved model identifier.

        Raises:
            ResolverValueError: If no context is available or the prim does not have exactly one external reference.
        """
        if self.context_name is None:
            raise ResolverValueError("The selected mesh could not be read. Reopen the project and try again.")
        owner, references = AssetReplacementsValidators.get_prim_references(str(prim.GetPath()), self.context_name)
        references = self.select_references(
            [(owner, reference, layer) for reference, layer in references], self.reference_selection, prim
        )
        if any(not reference.assetPath for _owner, reference, _layer in references):
            raise ResolverValueError("The selected mesh uses an internal reference that ComfyUI cannot upload.")
        values = tuple(
            dict.fromkeys(
                Sdf.ComputeAssetPathRelativeToLayer(layer, reference.assetPath)
                for _owner, reference, layer in references
            )
        )
        if not values:
            raise ResolverValueError("This mesh has no external model reference.")
        if len(values) != 1:
            raise ResolverValueError(
                f"This mesh has {len(values)} external model references. "
                "Set Reference Selection on this input to choose one."
            )
        return values[0]

    @staticmethod
    def select_references(
        references: list[OwnedReference], selection: MeshReferenceSelection, selected_prim: Usd.Prim | None = None
    ) -> tuple[OwnedReference, ...]:
        """Select All references of the mesh, or only the ones that compose the selected prim.

        Args:
            references: ``(owner prim, reference, introducing layer)`` triples in Selection panel order.
            selection: All or Selected.
            selected_prim: The picked prim. Without it, Selected returns every reference.

        Returns:
            The chosen triples in the given order. Empty when Selected finds no reference for the prim.
        """
        if selection is not MeshReferenceSelection.SELECTED or selected_prim is None or not selected_prim:
            return tuple(references)
        selected_path = selected_prim.GetPath()
        # A prim inside a marked child is composed by that child's reference alone, even when the mesh prim
        # references the same model.
        inside_child = [
            item for item in references if is_remix_reference(item[0]) and selected_path.HasPrefix(item[0].GetPath())
        ]
        if inside_child:
            return tuple(inside_child)
        # A nested asset can supply the spec through an outer model reference.
        model_paths = {}
        visited = {}
        for arc in Usd.PrimCompositionQuery(selected_prim).GetCompositionArcs():
            node = arc.GetTargetNode()
            if not node.hasSpecs:
                continue
            while node:
                site = (node.layerStack.identifier, node.path)
                seen = visited.setdefault(site, [])
                if node in seen:
                    break
                seen.append(node)
                model_paths.setdefault(node.layerStack.identifier.rootLayer.realPath, set()).add(node.path)
                node = node.parent
        chosen = []
        for owner, reference, layer in references:
            if is_remix_reference(owner):
                continue
            model_layer = Sdf.Layer.Find(Sdf.ComputeAssetPathRelativeToLayer(layer, reference.assetPath))
            if model_layer is None:
                continue
            # The reference composes one prim of the model (its primPath, else the default prim) onto the owner.
            model_root = reference.primPath or Sdf.Path.absoluteRootPath.AppendChild(model_layer.defaultPrim)
            if any(path.HasPrefix(model_root) for path in model_paths.get(model_layer.realPath, ())):
                chosen.append((owner, reference, layer))
        return tuple(chosen)


@dataclasses.dataclass
class AllStageMeshesResolver(SelectedMeshResolver, StageExpandingResolver):
    """Expand the input across stage prims with external model references."""

    label: ClassVar[str] = "All Meshes"

    # The whole stage has no picked prim, so every reference of each mesh is used by default.
    reference_selection: MeshReferenceSelection = MeshReferenceSelection.ALL

    def iter_stage_prim_paths(self, stage: Usd.Stage) -> Iterator[str]:
        """Iterate prim paths with at least one external reference."""
        predicate = Usd.TraverseInstanceProxies(Usd.PrimAllPrimsPredicate)
        ancestor_cache = {}
        for prim in Usd.PrimRange.Stage(stage, predicate):
            prim_path = str(prim.GetPath())
            _, references = AssetReplacementsValidators.get_prim_references(
                prim_path, self.context_name, stage=stage, ancestor_cache=ancestor_cache
            )
            if any(reference.assetPath for reference, _ in references):
                yield prim_path

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

from __future__ import annotations

__all__ = ["AlphaCutoutStageEditor"]

import omni.client
import omni.kit.undo
import omni.usd
from lightspeed.layer_manager.core import LayerManagerCore
from lightspeed.trex.asset_replacements.core.shared import Setup as AssetReplacementsCore
from lightspeed.trex.utils.common import prim_utils
from pxr import Sdf, Usd

from .data_models import MeshCutoutResult, StageEditOutcome


class AlphaCutoutStageEditor:
    """Swap capture and replacement references for generated cutout files on the current edit target.

    Every stage mutation goes through the undoable commands of the asset replacement core and is grouped so
    one undo reverts a whole conversion run. The generated files themselves stay on disk.
    """

    def __init__(self, context_name: str):
        """Bind the editor to a USD context.

        Args:
            context_name: Name of the USD context that holds the project.
        """
        self._context_name = context_name
        self._context = omni.usd.get_context(context_name)
        self._core = AssetReplacementsCore(context_name)
        self._layer_manager = LayerManagerCore(context_name)

    def destroy(self) -> None:
        """Release the cores this editor owns."""
        self._core.destroy()
        self._layer_manager.destroy()
        self._core = None
        self._layer_manager = None
        self._context = None

    def get_edit_layer_problem(self) -> str | None:
        """Explain why the current edit target cannot receive replacements.

        Returns:
            A message for the user, or ``None`` when the edit target is a writable replacement layer.
        """
        stage = self._context.get_stage()
        if not stage:
            return "No project is open."
        layer = stage.GetEditTarget().GetLayer()
        if layer.anonymous or layer not in self._layer_manager.get_replacement_layers():
            return "The edit target must be a replacement layer. Select the mod layer or one of its sublayers."
        if omni.usd.is_layer_locked(self._context, layer.identifier):
            return "The edit target layer is locked."
        return None

    @staticmethod
    def find_existing_cutout_reference(
        prim: Usd.Prim, output_path: str
    ) -> tuple[Usd.Prim, Sdf.Reference, Sdf.Layer] | None:
        """Find the reference a prim or its reference children already hold to a cutout file.

        Args:
            prim: The ``mesh_HASH`` prototype root.
            output_path: Normalized path of the cutout file.

        Returns:
            The prim that holds the reference, the reference and its layer, or ``None``.
        """
        wanted = omni.client.normalize_url(output_path).lower()
        reference_items, _ = prim_utils.get_reference_file_paths(prim)
        for reference_prim, reference, layer, _ in reference_items:
            resolved = omni.client.normalize_url(layer.ComputeAbsolutePath(reference.assetPath)).lower()
            if resolved == wanted:
                return reference_prim, reference, layer
        return None

    def _swap_replacement_reference(
        self, stage: Usd.Stage, edit_layer: Sdf.Layer, ref_prim_path: str, output_path: str
    ) -> tuple[bool, str | None]:
        """Point a replacement reference prim at the cutout file, keeping the prim and its overrides.

        Args:
            stage: Project stage.
            edit_layer: Layer that receives the new reference.
            ref_prim_path: Path of the ``ref_*`` prim.
            output_path: Normalized path of the cutout file.

        Returns:
            Whether the reference changed, and a reason when nothing could be done.
        """
        ref_prim = stage.GetPrimAtPath(ref_prim_path)
        if not ref_prim or not ref_prim.IsValid():
            return False, "The reference prim no longer exists."
        reference_items, _ = prim_utils.get_reference_file_paths(ref_prim)
        own = [
            (reference, layer) for reference_prim, reference, layer, _ in reference_items if reference_prim == ref_prim
        ]
        if not own:
            return False, "The replacement has no reference."
        wanted = omni.client.normalize_url(output_path).lower()
        for reference, layer in own:
            if omni.client.normalize_url(layer.ComputeAbsolutePath(reference.assetPath)).lower() == wanted:
                return False, None
        reference, layer = own[0]
        self._core.replace_reference(
            stage,
            ref_prim.GetPath(),
            reference,
            layer,
            output_path,
            edit_layer,
            remove_if_remix_ref=False,
            create_if_remix_ref=False,
            use_undo_group=False,
        )
        return True, None

    def apply(self, results: list[MeshCutoutResult]) -> list[StageEditOutcome]:
        """Reference the cutout files: mask capture references, or re-point replacement references.

        A mesh that already references its cutout file keeps that reference, so re-converting with other
        parameters only rewrites the file. Replacement references are swapped on their existing ``ref_*`` prim
        so overrides authored under it keep applying.

        Args:
            results: Results whose ``output_path`` is set.

        Returns:
            One outcome per result with an output path.
        """
        stage = self._context.get_stage()
        edit_layer = stage.GetEditTarget().GetLayer()
        replacement_layers = self._layer_manager.get_replacement_layers()
        outcomes: list[StageEditOutcome] = []
        swapped: dict[str, tuple[bool, str | None]] = {}
        with omni.kit.undo.group():
            for result in results:
                if not result.output_path:
                    continue
                if result.source.ref_prim_path:
                    key = result.source.ref_prim_path
                    if key not in swapped:
                        swapped[key] = self._swap_replacement_reference(stage, edit_layer, key, result.output_path)
                    changed, reason = swapped[key]
                    outcomes.append(StageEditOutcome(result.source.prim_path, key, changed, reason))
                    continue
                prim = stage.GetPrimAtPath(result.source.prim_path)
                if not prim or not prim.IsValid():
                    outcomes.append(
                        StageEditOutcome(result.source.prim_path, None, False, "The prim no longer exists.")
                    )
                    continue
                existing = self.find_existing_cutout_reference(prim, result.output_path)
                _, reference_items = prim_utils.find_prim_with_references(prim)
                for reference_prim, reference, layer, _ in reference_items:
                    if layer in replacement_layers or reference_prim != prim:
                        continue
                    self._core.remove_reference(stage, reference_prim.GetPath(), reference, layer)
                if existing is None:
                    _, child_path = self._core.add_new_reference(
                        stage,
                        prim.GetPath(),
                        result.output_path,
                        AssetReplacementsCore.get_ref_default_prim_tag(),
                        edit_layer,
                    )
                    outcomes.append(StageEditOutcome(result.source.prim_path, str(child_path), True))
                else:
                    outcomes.append(StageEditOutcome(result.source.prim_path, str(existing[0].GetPath()), False))
        return outcomes

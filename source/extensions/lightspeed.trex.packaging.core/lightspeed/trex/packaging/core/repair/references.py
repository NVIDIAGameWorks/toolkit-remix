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

__all__ = ["RepairReferenceCore"]

from lightspeed.common.constants import ROOTNODE_INSTANCES as _ROOTNODE_INSTANCES
from lightspeed.common.constants import USD_EXTENSIONS
from omni.flux.utils.common.omni_url import OmniUrl
from pxr import Sdf

from .layers import RepairLayerCore
from .models import PackagingRepairRequest, RepairState


class RepairReferenceCore:
    """
    Reference discovery, matching, and traversal helpers for packaging repairs.
    """

    def __init__(self, layer_core: RepairLayerCore):
        """Initialize the reference helper.

        Args:
            layer_core: Layer helper used to open layers and resolve asset paths.
        """
        self._layers = layer_core

    def get_local_references(self, state: RepairState) -> list[tuple[Sdf.Path, str, Sdf.Layer, Sdf.Reference]]:
        """Get authored local references sorted from deepest prim path to shallowest.

        Args:
            state: The active repair state.

        Returns:
            Authored reference entries for local layer-stack layers.
        """
        if state.local_references is not None:
            return state.local_references

        local_references = []
        for layer_identifier, layer in self._layers.get_local_layers(state).values():
            for prim_spec in self._iter_prim_specs(state, layer):
                for reference in self._get_authored_references(prim_spec):
                    if state.is_cancelled_requested():
                        return local_references
                    if reference.assetPath:
                        local_references.append((prim_spec.path, layer_identifier, layer, reference))

        local_references.sort(key=lambda entry: len(entry[0].GetPrefixes()), reverse=True)
        state.local_references = local_references
        return local_references

    def get_local_references_by_target_layer(
        self, state: RepairState
    ) -> dict[str, list[tuple[Sdf.Path, str, Sdf.Layer, Sdf.Reference]]]:
        """Group local references by resolved target layer.

        Args:
            state: The active repair state.

        Returns:
            Mapping from normalized target layer key to authored reference entries.
        """
        if state.local_references_by_target_layer is not None:
            return state.local_references_by_target_layer

        references_by_target_layer: dict[str, list[tuple[Sdf.Path, str, Sdf.Layer, Sdf.Reference]]] = {}
        for authored_prim_path, layer_identifier, layer, reference in self.get_local_references(state):
            target_key = OmniUrl(
                self._layers.compute_absolute_path_from_identifier(layer_identifier, reference.assetPath)
            ).path.lower()
            references_by_target_layer.setdefault(target_key, []).append(
                (authored_prim_path, layer_identifier, layer, reference)
            )

        state.local_references_by_target_layer = references_by_target_layer
        return references_by_target_layer

    @staticmethod
    def _get_authored_references(prim_spec: Sdf.PrimSpec) -> list[Sdf.Reference]:
        return list(prim_spec.referenceList.GetAddedOrExplicitItems())

    @staticmethod
    def _get_reported_reference_group_path(prim_path: Sdf.Path) -> Sdf.Path:
        current_path = prim_path
        while current_path and current_path != Sdf.Path.absoluteRootPath:
            parent_path = current_path.GetParentPath()
            if (
                parent_path
                and parent_path != Sdf.Path.absoluteRootPath
                and parent_path.name == Sdf.Path(_ROOTNODE_INSTANCES).name
            ):
                return parent_path.GetParentPath()
            current_path = parent_path
        return prim_path

    def get_reference_group_repair_key(
        self, request: PackagingRepairRequest, target_layer_identifier: str, repair_layer_identifier: str
    ) -> tuple:
        """Build a deduplication key for grouped reference repairs.

        Args:
            request: The repair request.
            target_layer_identifier: Identifier of the layer that owns the unresolved opinion.
            repair_layer_identifier: Identifier of the layer where the repair will be authored.

        Returns:
            The group-level repair deduplication key.
        """
        return (
            repair_layer_identifier,
            target_layer_identifier,
            request.action,
            OmniUrl(request.asset_path).path.lower(),
            OmniUrl(request.fixed_asset_path).path.lower() if request.fixed_asset_path else "",
            str(self._get_reported_reference_group_path(request.prim_path.GetPrimPath())),
        )

    @classmethod
    def get_reference_repair_key(
        cls,
        request: PackagingRepairRequest,
        target_layer_identifier: str,
        repair_layer_identifier: str,
        prim_path: Sdf.Path,
        reference: Sdf.Reference,
    ) -> tuple:
        """Build a deduplication key for one authored reference repair.

        Args:
            request: The repair request.
            target_layer_identifier: Identifier of the layer that owns the unresolved opinion.
            repair_layer_identifier: Identifier of the layer where the repair will be authored.
            prim_path: Prim path that authors the reference.
            reference: Authored reference.

        Returns:
            The reference-level repair deduplication key.
        """
        return (
            repair_layer_identifier,
            target_layer_identifier,
            request.action,
            OmniUrl(request.asset_path).path.lower(),
            OmniUrl(request.fixed_asset_path).path.lower() if request.fixed_asset_path else "",
            str(prim_path),
            *cls._get_reference_value_key(reference),
        )

    @staticmethod
    def _get_reference_value_key(reference: Sdf.Reference) -> tuple:
        return (
            reference.assetPath,
            str(reference.primPath),
            reference.layerOffset.offset,
            reference.layerOffset.scale,
        )

    @classmethod
    def _get_reference_match_key(cls, prim_path: Sdf.Path, reference: Sdf.Reference) -> tuple:
        return (
            str(prim_path),
            *cls._get_reference_value_key(reference),
        )

    def find_reference_to_target_layer(
        self,
        state: RepairState,
        layer_identifier: str,
        reference: Sdf.Reference,
        target_layer_identifier: str,
        target_prim_path: Sdf.Path,
        local_prim_path: Sdf.Path,
        visited: set[tuple],
    ) -> tuple[Sdf.Path | None, Sdf.Reference | None]:
        """Find the local prim path and reference that introduce a target layer.

        Args:
            state: The active repair state.
            layer_identifier: Identifier for the layer that authored ``reference``.
            reference: Reference to inspect.
            target_layer_identifier: Identifier for the external target layer.
            target_prim_path: Prim path reported for the unresolved asset.
            local_prim_path: Local prim path corresponding to the reference.
            visited: Recursion guard keys.

        Returns:
            Local target prim path and reference, or ``None`` values when no path is found.
        """
        target_key = OmniUrl(target_layer_identifier).path.lower()
        cache_key = (
            OmniUrl(layer_identifier).path.lower(),
            self._get_reference_match_key(local_prim_path, reference),
            target_key,
        )
        if cache_key in visited:
            return None, None
        visited.add(cache_key)

        referenced_layer_identifier = self._layers.compute_absolute_path_from_identifier(
            layer_identifier, reference.assetPath
        )
        if OmniUrl(referenced_layer_identifier).path.lower() == target_key:
            if target_prim_path != local_prim_path and not target_prim_path.HasPrefix(local_prim_path):
                return None, None
            return local_prim_path, reference
        if OmniUrl(referenced_layer_identifier).suffix not in USD_EXTENSIONS:
            return None, None

        referenced_layer = self._layers.get_read_layer(state, referenced_layer_identifier)
        if not referenced_layer:
            return None, None

        root_path = self._get_reference_root_path(referenced_layer, reference)
        for prim_spec in self._iter_prim_specs(state, referenced_layer, root_path):
            for nested_reference in self._get_authored_references(prim_spec):
                if state.is_cancelled_requested():
                    return None, None
                if not nested_reference.assetPath:
                    continue
                nested_local_prim_path = self._get_local_override_prim_path(local_prim_path, root_path, prim_spec.path)
                target_local_prim_path, target_reference = self.find_reference_to_target_layer(
                    state,
                    referenced_layer_identifier,
                    nested_reference,
                    target_layer_identifier,
                    target_prim_path,
                    nested_local_prim_path,
                    visited,
                )
                if target_local_prim_path:
                    return target_local_prim_path, target_reference

        return None, None

    @staticmethod
    def _get_reference_root_path(layer: Sdf.Layer, reference: Sdf.Reference) -> Sdf.Path | None:
        if reference.primPath:
            return reference.primPath
        if layer.defaultPrim:
            return Sdf.Path(f"/{layer.defaultPrim}")
        return None

    def _append_references(
        self,
        matches: list[tuple[Sdf.Path, Sdf.Reference]],
        seen: set[tuple],
        prim_path: Sdf.Path,
        references: list[Sdf.Reference],
    ):
        for reference in references:
            reference_key = self._get_reference_match_key(prim_path, reference)
            if reference_key in seen:
                continue
            seen.add(reference_key)
            matches.append((prim_path, reference))

    def _iter_prim_specs(
        self,
        state: RepairState,
        layer: Sdf.Layer,
        root_path: Sdf.Path | None = None,
    ) -> list[Sdf.PrimSpec]:
        if root_path:
            root_spec = layer.GetPrimAtPath(root_path)
            prim_specs = [root_spec] if root_spec else []
        else:
            prim_specs = list(reversed(layer.rootPrims))
        result = []
        while prim_specs:
            if state.is_cancelled_requested():
                return result
            prim_spec = prim_specs.pop()
            result.append(prim_spec)
            prim_specs.extend(reversed(prim_spec.nameChildren))
        return result

    def _get_references_by_asset_path(
        self,
        state: RepairState,
        layer_identifier: str,
        layer: Sdf.Layer,
        root_path: Sdf.Path | None = None,
    ) -> dict[str, list[tuple[Sdf.Path, Sdf.Reference, list[Sdf.Reference]]]]:
        cache_key = (OmniUrl(layer_identifier).path.lower(), str(root_path or ""))
        if cache_key in state.references_by_asset_path:
            return state.references_by_asset_path[cache_key]

        references_by_asset_path: dict[str, list[tuple[Sdf.Path, Sdf.Reference, list[Sdf.Reference]]]] = {}
        for prim_spec in self._iter_prim_specs(state, layer, root_path):
            authored_references = self._get_authored_references(prim_spec)
            for reference in authored_references:
                if not reference.assetPath:
                    continue
                asset_key = OmniUrl(
                    self._layers.compute_absolute_path_from_identifier(layer_identifier, reference.assetPath)
                ).path.lower()
                references_by_asset_path.setdefault(asset_key, []).append(
                    (prim_spec.path, reference, authored_references)
                )

        state.references_by_asset_path[cache_key] = references_by_asset_path
        return references_by_asset_path

    def find_authored_references(
        self,
        state: RepairState,
        request: PackagingRepairRequest,
        target_layer_identifier: str,
        target_layer: Sdf.Layer | None,
        should_author_override: bool,
        target_local_prim_path: Sdf.Path | None = None,
        target_reference: Sdf.Reference | None = None,
    ) -> list[tuple[Sdf.Path, Sdf.Reference]]:
        """Find authored references that should be repaired for a request.

        Args:
            state: The active repair state.
            request: The repair request.
            target_layer_identifier: Identifier of the layer that owns the unresolved opinion.
            target_layer: Layer that owns the unresolved opinion.
            should_author_override: Whether repair should author an override from an introducing local layer.
            target_local_prim_path: Local prim path that introduced the external target layer.
            target_reference: Reference that introduced the external target layer.

        Returns:
            Authored references to repair.

        Raises:
            RuntimeError: If no matching reference can be found.
        """
        if not target_layer:
            raise RuntimeError(f"Unable to open target layer '{request.layer_identifier}'")

        matches = []
        seen = set()
        prim_path = request.prim_path.GetPrimPath()
        asset_key = OmniUrl(request.asset_path).path.lower()
        references_by_asset_path = self._get_references_by_asset_path(state, target_layer_identifier, target_layer)

        if should_author_override:
            override_root_path = target_local_prim_path or prim_path
            target_root_path = (
                self._get_reference_root_path(target_layer, target_reference) if target_reference else None
            )
            for target_prim_path, _matching_reference, authored_references in references_by_asset_path.get(
                asset_key, []
            ):
                override_prim_path = self._get_local_override_prim_path(
                    override_root_path, target_root_path, target_prim_path
                )
                self._append_references(matches, seen, override_prim_path, authored_references)
            return matches

        search_roots = list(dict.fromkeys((self._get_reported_reference_group_path(prim_path), prim_path)))

        for search_root in search_roots:
            for match_prim_path, matching_reference, _authored_references in references_by_asset_path.get(
                asset_key, []
            ):
                if match_prim_path != search_root and not match_prim_path.HasPrefix(search_root):
                    continue
                self._append_references(matches, seen, match_prim_path, [matching_reference])
            if matches:
                break

        if not matches:
            candidate_paths = [path for path in reversed(prim_path.GetPrefixes()) if path != Sdf.Path.absoluteRootPath]
            for candidate_path in candidate_paths:
                for match_prim_path, matching_reference, _authored_references in references_by_asset_path.get(
                    asset_key, []
                ):
                    if match_prim_path == candidate_path:
                        self._append_references(matches, seen, match_prim_path, [matching_reference])

        if not matches:
            raise RuntimeError(f"Unable to find reference '{request.asset_path}' on prim '{request.prim_path}'")
        return matches

    @staticmethod
    def _get_local_override_prim_path(
        local_root_path: Sdf.Path,
        target_root_path: Sdf.Path | None,
        target_prim_path: Sdf.Path,
    ) -> Sdf.Path:
        if target_root_path and target_prim_path.HasPrefix(target_root_path):
            return target_prim_path.ReplacePrefix(target_root_path, local_root_path)
        return local_root_path

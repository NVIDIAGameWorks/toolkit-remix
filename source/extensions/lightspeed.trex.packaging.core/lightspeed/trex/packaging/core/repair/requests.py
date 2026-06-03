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

__all__ = ["RepairRequestCore", "RepairRequestError"]

from typing import NoReturn

import carb
from omni.flux.utils.common.omni_url import OmniUrl
from pxr import Sdf

from .authoring import RepairAuthoringCore
from .enum import PackagingRepairAction
from .layers import RepairLayerCore
from .models import PackagingRepairRequest, RepairState
from .references import RepairReferenceCore


class RepairRequestError(RuntimeError):
    """Raised when an individual repair request could not be applied."""


class RepairRequestCore:
    """
    Single repair request application helpers.
    """

    def __init__(
        self,
        layer_core: RepairLayerCore,
        reference_core: RepairReferenceCore,
        authoring_core: RepairAuthoringCore,
    ):
        """Initialize the request helper.

        Args:
            layer_core: Layer helper used to open and mark editable layers.
            reference_core: Reference helper used to resolve target and introducing references.
            authoring_core: Authoring helper used to write repair opinions.
        """
        self._layers = layer_core
        self._references = reference_core
        self._authoring = authoring_core

    def apply_repair_request(self, state: RepairState, request: PackagingRepairRequest):
        """Apply one repair request.

        Args:
            state: The active repair state.
            request: The repair request to apply.
        """
        if request.action == PackagingRepairAction.IGNORE:
            state.add_ignored_request(request)
            return

        is_reference = request.prim_path.IsPrimPath()
        if (
            is_reference
            and self._references.get_reference_group_repair_key(
                request, request.layer_identifier, request.layer_identifier
            )
            in state.reference_group_repair_keys
        ):
            return

        resolved_repair_data = self._resolve_repair_request_data(state, request, is_reference)
        if state.is_cancelled_requested():
            return
        repair_layer_identifier, should_author_override, authored_references = resolved_repair_data

        try:
            editable_repair_layer = self._layers.get_editable_layer(state, repair_layer_identifier)
        except RuntimeError as exc:
            self._fail_repair_request(state, request, str(exc))

        repair_layer_key = OmniUrl(repair_layer_identifier).path.lower()
        if is_reference:
            if not authored_references:
                self._fail_repair_request(
                    state, request, f"Unable to find reference '{request.asset_path}' on prim '{request.prim_path}'"
                )
            if should_author_override:
                reference_repair_key = self._references.get_reference_group_repair_key(
                    request, request.layer_identifier, repair_layer_identifier
                )
                if reference_repair_key in state.reference_repair_keys:
                    return
                repair_applied = False
                repair_failed = False
                action_label = "replace" if request.action == PackagingRepairAction.REPLACE_ASSET else "remove"
                references_by_prim_path = {}
                for prim_path, reference in authored_references:
                    references_by_prim_path.setdefault(prim_path, []).append((prim_path, reference))
                for override_prim_path, override_references in references_by_prim_path.items():
                    prim_repair_applied = (
                        self._authoring.replace_reference_override(
                            editable_repair_layer,
                            repair_layer_identifier,
                            request.layer_identifier,
                            override_prim_path,
                            override_references,
                            request.asset_path,
                            request.fixed_asset_path,
                        )
                        if request.action == PackagingRepairAction.REPLACE_ASSET
                        else self._authoring.remove_reference_override(
                            editable_repair_layer,
                            repair_layer_identifier,
                            request.layer_identifier,
                            override_prim_path,
                            override_references,
                            request.asset_path,
                        )
                    )
                    if prim_repair_applied:
                        repair_applied = True
                    else:
                        repair_failed = True
                        carb.log_warn(
                            f"Unable to {action_label} unresolved reference "
                            f"'{request.asset_path}' on prim '{override_prim_path}'"
                        )
                if repair_applied and not repair_failed:
                    state.reference_repair_keys.add(reference_repair_key)
                if repair_applied and state.editable_layers is not None:
                    state.dirty_editable_layer_keys.add(repair_layer_key)
                if repair_failed or not repair_applied:
                    self._fail_repair_request(
                        state,
                        request,
                        f"Unable to {action_label} unresolved reference '{request.asset_path}' "
                        f"on prim '{request.prim_path}'",
                    )
                return

            if not should_author_override:
                state.reference_group_repair_keys.add(
                    self._references.get_reference_group_repair_key(
                        request, request.layer_identifier, repair_layer_identifier
                    )
                )
            for prim_path, current_ref in authored_references:
                reference_repair_key = self._references.get_reference_repair_key(
                    request, request.layer_identifier, repair_layer_identifier, prim_path, current_ref
                )
                if reference_repair_key in state.reference_repair_keys:
                    continue
                if request.action == PackagingRepairAction.REPLACE_ASSET:
                    repair_applied = self._authoring.replace_reference_opinion(
                        should_author_override,
                        editable_repair_layer,
                        repair_layer_identifier,
                        request.layer_identifier,
                        prim_path,
                        current_ref,
                        request.fixed_asset_path,
                    )
                else:
                    repair_applied = self._authoring.remove_reference_opinion(
                        should_author_override,
                        editable_repair_layer,
                        prim_path,
                        current_ref,
                    )
                if repair_applied:
                    state.reference_repair_keys.add(reference_repair_key)
                    if state.editable_layers is not None:
                        state.dirty_editable_layer_keys.add(repair_layer_key)
                else:
                    action_label = "replace" if request.action == PackagingRepairAction.REPLACE_ASSET else "remove"
                    self._fail_repair_request(
                        state,
                        request,
                        f"Unable to {action_label} unresolved reference '{current_ref.assetPath}' on prim '{prim_path}'",
                    )
            return

        texture_value = request.fixed_asset_path if request.action == PackagingRepairAction.REPLACE_ASSET else None
        texture_repair_key = (repair_layer_identifier, str(request.prim_path), texture_value)
        if texture_repair_key in state.texture_repair_keys:
            return
        state.texture_repair_keys.add(texture_repair_key)

        if request.action == PackagingRepairAction.REMOVE_REFERENCE:
            repair_applied = self._authoring.remove_texture_opinion(
                should_author_override,
                editable_repair_layer,
                Sdf.Path(str(request.prim_path)),
            )
            if repair_applied and state.editable_layers is not None:
                state.dirty_editable_layer_keys.add(repair_layer_key)
            if not repair_applied:
                self._fail_repair_request(
                    state, request, f"Unable to remove unresolved texture asset '{request.asset_path}'"
                )
            return

        repair_applied = self._authoring.replace_texture_opinion(
            editable_repair_layer,
            repair_layer_identifier,
            str(request.prim_path),
            texture_value,
        )
        if repair_applied and state.editable_layers is not None:
            state.dirty_editable_layer_keys.add(repair_layer_key)
        if not repair_applied:
            self._fail_repair_request(
                state,
                request,
                f"Unable to replace unresolved texture asset '{request.asset_path}' with '{request.fixed_asset_path}'",
            )

    @staticmethod
    def _fail_repair_request(state: RepairState, request: PackagingRepairRequest, message: str) -> NoReturn:
        carb.log_warn(message)
        state.add_failed_request(request, message)
        raise RepairRequestError(message)

    def _resolve_repair_request_data(
        self, state: RepairState, request: PackagingRepairRequest, is_reference: bool
    ) -> tuple[str, bool, list[tuple[Sdf.Path, Sdf.Reference]]]:
        target_layer_identifier = request.layer_identifier
        target_layer = self._layers.get_read_layer(state, target_layer_identifier)
        if not target_layer:
            self._fail_repair_request(
                state,
                request,
                f"Unable to open target layer '{target_layer_identifier}' for unresolved asset '{request.asset_path}'",
            )

        if OmniUrl(target_layer_identifier).path.lower() in self._layers.get_local_layers(state):
            if self._layers.is_repair_layer_blocked(target_layer):
                self._fail_repair_request(
                    state,
                    request,
                    f"Skipping unresolved asset repair: layer '{target_layer_identifier}' for prim "
                    f"'{request.prim_path}' is not editable.",
                )
            try:
                authored_references = (
                    self._references.find_authored_references(
                        state, request, target_layer_identifier, target_layer, False
                    )
                    if is_reference
                    else None
                )
            except RuntimeError as exc:
                self._fail_repair_request(state, request, str(exc))
            return target_layer_identifier, False, authored_references or []

        (
            introducing_layer_identifier,
            introducing_layer,
            target_local_prim_path,
            target_reference,
        ) = self._find_local_introducing_layer(state, request)
        if not introducing_layer_identifier or not introducing_layer:
            self._fail_repair_request(
                state,
                request,
                f"Unable to find a local layer-stack layer that introduces external layer "
                f"'{target_layer_identifier}' for prim '{request.prim_path}'",
            )
        if self._layers.is_repair_layer_blocked(introducing_layer):
            self._fail_repair_request(
                state,
                request,
                f"Skipping unresolved asset repair: layer '{introducing_layer_identifier}' for prim "
                f"'{request.prim_path}' is not editable.",
            )
        try:
            authored_references = (
                self._references.find_authored_references(
                    state,
                    request,
                    target_layer_identifier,
                    target_layer,
                    True,
                    target_local_prim_path,
                    target_reference,
                )
                if is_reference
                else None
            )
        except RuntimeError as exc:
            self._fail_repair_request(state, request, str(exc))
        return introducing_layer_identifier, True, authored_references or []

    def _find_local_introducing_layer(
        self, state: RepairState, request: PackagingRepairRequest
    ) -> tuple[str | None, Sdf.Layer | None, Sdf.Path | None, Sdf.Reference | None]:
        prim_path = request.prim_path.GetPrimPath()
        target_layer_key = OmniUrl(request.layer_identifier).path.lower()
        for (
            authored_prim_path,
            layer_identifier,
            layer,
            reference,
        ) in self._references.get_local_references_by_target_layer(state).get(target_layer_key, []):
            if prim_path == authored_prim_path or prim_path.HasPrefix(authored_prim_path):
                return layer_identifier, layer, authored_prim_path, reference

        for authored_prim_path, layer_identifier, layer, reference in self._references.get_local_references(state):
            target_local_prim_path, target_reference = self._references.find_reference_to_target_layer(
                state,
                layer_identifier,
                reference,
                request.layer_identifier,
                prim_path,
                authored_prim_path,
                set(),
            )
            if target_local_prim_path:
                return layer_identifier, layer, target_local_prim_path, target_reference

        return None, None, None, None

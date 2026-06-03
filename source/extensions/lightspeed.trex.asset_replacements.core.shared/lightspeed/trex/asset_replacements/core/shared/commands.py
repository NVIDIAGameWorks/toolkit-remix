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

from collections.abc import Sequence

import omni.kit.commands
from pxr import Sdf

from .setup import Setup


class TransferPropertySpecToLayerCommand(omni.kit.commands.Command):
    """Transfer one authored property spec group to another layer."""

    def __init__(
        self,
        property_path: str,
        source_layer_identifiers: Sequence[str],
        target_layer_identifier: str,
        usd_context: str = "",
    ):
        """Initialize the property transfer command.

        Args:
            property_path: USD property path to transfer.
            source_layer_identifiers: Explicit source layers to move; the caller scopes this so definition and
                modification transfers on the same path do not remove unrelated authored specs.
            target_layer_identifier: Layer that should receive the transferred property.
            usd_context: USD context name containing the stage.
        """
        self._core = Setup(usd_context)
        self._property_path = property_path
        self._source_layer_identifiers = source_layer_identifiers
        self._target_layer_identifier = target_layer_identifier
        self._layer_undos = []

    def do(self):
        """Transfer the selected property spec group to the target layer.

        Returns:
            True when the transfer succeeds; False when validation fails.
        """
        layer_undos = self._core.transfer_property_spec_to_layer(
            self._property_path, self._source_layer_identifiers, self._target_layer_identifier
        )
        if layer_undos is None:
            return False
        self._layer_undos = layer_undos
        return True

    def undo(self) -> None:
        """Restore every layer touched by the transfer."""
        self._core.undo_spec_transfer(self._layer_undos)


class TransferPrimDefinitionSpecToLayerCommand(omni.kit.commands.Command):
    """Transfer one authored prim-definition spec group to another layer."""

    def __init__(
        self,
        prim_path: str,
        source_layer_identifiers: Sequence[str],
        target_layer_identifier: str,
        usd_context: str = "",
    ):
        """Initialize the prim-definition transfer command.

        Args:
            prim_path: USD prim path to transfer.
            source_layer_identifiers: Explicit source layers to move; layer transfers pass one source layer while
                definition transfers can pass multiple layers for the same prim path.
            target_layer_identifier: Layer that should receive the transferred prim definition.
            usd_context: USD context name containing the stage.
        """
        self._core = Setup(usd_context)
        self._prim_path = prim_path
        self._source_layer_identifiers = source_layer_identifiers
        self._target_layer_identifier = target_layer_identifier
        self._layer_undos = []

    def do(self):
        """Transfer the selected prim-definition spec group to the target layer.

        Returns:
            True when the transfer succeeds; False when validation fails.
        """
        layer_undos = self._core.transfer_prim_definition_spec_to_layer(
            self._prim_path, self._source_layer_identifiers, self._target_layer_identifier
        )
        if layer_undos is None:
            return False
        self._layer_undos = layer_undos
        return True

    def undo(self) -> None:
        """Restore every layer touched by the transfer."""
        self._core.undo_spec_transfer(self._layer_undos)


class TransferReferenceSpecToLayerCommand(omni.kit.commands.Command):
    """Transfer one authored reference spec group to another layer."""

    def __init__(
        self,
        prim_path: str,
        reference: Sdf.Reference,
        source_layer_identifiers: Sequence[str],
        target_layer_identifier: str,
        usd_context: str = "",
    ):
        """Initialize the reference transfer command.

        Args:
            prim_path: USD prim path owning the reference edit.
            reference: Specific reference list edit to transfer; a prim path can author more than one reference.
            source_layer_identifiers: Explicit source layers whose matching reference edits should be moved.
            target_layer_identifier: Layer that should receive the transferred reference edit.
            usd_context: USD context name containing the stage.
        """
        self._core = Setup(usd_context)
        self._prim_path = prim_path
        self._reference = reference
        self._source_layer_identifiers = source_layer_identifiers
        self._target_layer_identifier = target_layer_identifier
        self._layer_undos = []

    def do(self):
        """Transfer the selected reference spec group to the target layer.

        Returns:
            True when the transfer succeeds; False when validation fails.
        """
        layer_undos = self._core.transfer_reference_spec_to_layer(
            self._prim_path,
            self._reference,
            self._source_layer_identifiers,
            self._target_layer_identifier,
        )
        if layer_undos is None:
            return False
        self._layer_undos = layer_undos
        return True

    def undo(self) -> None:
        """Restore every layer touched by the transfer."""
        self._core.undo_spec_transfer(self._layer_undos)

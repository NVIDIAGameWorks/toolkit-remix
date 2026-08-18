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

__all__ = ["REPLACE_TEXTURES_COMMAND", "ReplaceTexturesCommand"]

from collections.abc import Iterator
from dataclasses import dataclass

import omni.kit.commands
from lightspeed.common.constants import ROOTNODE
from omni.usd.commands import remove_prim_spec
from pxr import Sdf

from .data_models.models import TextureReplacement

REPLACE_TEXTURES_COMMAND = "ReplaceTexturesCommand"


@dataclass(frozen=True)
class _LayerState:
    """Exact target-property specs and relevant ancestor-spec presence."""

    layer: Sdf.Layer
    prim_paths: frozenset[Sdf.Path]


class ReplaceTexturesCommand(omni.kit.commands.Command):
    """Atomically author one validated texture batch with native USD state capture."""

    def __init__(
        self,
        replacements: list[TextureReplacement],
        target_layer_identifier: str,
        expected_replacements: list[TextureReplacement] | None = None,
    ):
        """Initialize a serializable replacement command.

        Args:
            replacements: Prepared target paths, authored values, and USD value type names.
            target_layer_identifier: Identifier of the layer receiving the authored opinions.
            expected_replacements: Exact target-layer values required before the first execution.
        """
        self._replacements = [
            TextureReplacement(replacement.property_path, replacement.value, replacement.value_type)
            for replacement in replacements
        ]
        self._expected_replacements = (
            [
                TextureReplacement(replacement.property_path, replacement.value, replacement.value_type)
                for replacement in expected_replacements
            ]
            if expected_replacements is not None
            else None
        )
        self._target_layer_identifier = target_layer_identifier
        self._property_paths: tuple[Sdf.Path, ...] = ()
        self._before: _LayerState | None = None
        self._after: _LayerState | None = None
        if self._expected_replacements is not None:
            self._verify_expected_values(self._resolve_target_layer())

    def _resolve_target_layer(self) -> Sdf.Layer:
        """Resolve the persisted target-layer identifier.

        Returns:
            The open target layer.

        Raises:
            RuntimeError: If the target layer is no longer open.
        """
        target_layer = Sdf.Layer.Find(self._target_layer_identifier)
        if target_layer is None:
            raise RuntimeError(f"The texture replacement target layer is unavailable: {self._target_layer_identifier}")
        return target_layer

    @staticmethod
    def _get_authored_value(replacement: TextureReplacement) -> str | Sdf.AssetPath | None:
        """Build the exact USD value expected in the target layer.

        Args:
            replacement: Prepared replacement definition.

        Returns:
            The expected String or Asset value, or None for property removal.

        Raises:
            RuntimeError: If a replacement declares an unsupported USD value type.
        """
        value = replacement.value
        if value is None:
            return None

        value_type = replacement.value_type
        if value_type == Sdf.ValueTypeNames.String:
            return value
        if value_type == Sdf.ValueTypeNames.Asset:
            return Sdf.AssetPath(value)
        raise RuntimeError(f"Unsupported texture replacement value type: {replacement.value_type}")

    def _validate_replacements(self) -> None:
        """Validate every path and value before capturing or mutating layer state.

        Raises:
            RuntimeError: If a path or value type is invalid.
        """
        property_paths = []
        for replacement in self._replacements:
            property_path = replacement.property_path
            if not property_path.IsPropertyPath():
                raise RuntimeError(f"Invalid texture replacement property path: {property_path}")
            self._get_authored_value(replacement)
            property_paths.append(property_path)
        if len(property_paths) != len(set(property_paths)):
            raise RuntimeError("Texture replacement target paths must be unique")
        self._property_paths = tuple(property_paths)

        if self._expected_replacements is None:
            return

        expected_paths = []
        for replacement in self._expected_replacements:
            property_path = replacement.property_path
            if not property_path.IsPropertyPath():
                raise RuntimeError(f"Invalid expected texture property path: {property_path}")
            self._get_authored_value(replacement)
            expected_paths.append(property_path)
        if len(expected_paths) != len(set(expected_paths)):
            raise RuntimeError("Expected texture target paths must be unique")
        if set(expected_paths) != set(self._property_paths):
            raise RuntimeError("Expected texture target paths must match the replacement batch")

    def _verify_expected_values(self, target_layer: Sdf.Layer) -> None:
        """Verify the caller-confirmed target-layer baseline before first mutation.

        Args:
            target_layer: Layer whose exact authored values must match.

        Raises:
            RuntimeError: If any target property differs from the confirmed baseline.
        """
        if self._expected_replacements is None:
            return
        for replacement in self._expected_replacements:
            property_path = replacement.property_path
            attribute_spec = target_layer.GetAttributeAtPath(property_path)
            expected_value = self._get_authored_value(replacement)
            if expected_value is None:
                matches = attribute_spec is None
            else:
                matches = attribute_spec is not None and attribute_spec.default == expected_value
            if not matches:
                raise ValueError(f"Texture target differs from its expected current value: {property_path}")

    def _iter_prim_paths(self) -> Iterator[Sdf.Path]:
        """Yield each relevant ancestor prim path once, deepest first."""
        prim_paths = set()
        for property_path in self._property_paths:
            prim_path = property_path.GetPrimPath()
            while prim_path != Sdf.Path.absoluteRootPath:
                prim_paths.add(prim_path)
                if str(prim_path) == ROOTNODE:
                    break
                prim_path = prim_path.GetParentPath()
        yield from sorted(prim_paths, key=lambda path: str(path).count("/"), reverse=True)

    def _capture_state(self, target_layer: Sdf.Layer) -> _LayerState:
        """Copy the exact target-property specs without serialized job or stage data.

        Args:
            target_layer: Layer whose relevant state is captured.

        Returns:
            An isolated property snapshot and the existing relevant prim-spec paths.

        Raises:
            RuntimeError: If USD cannot copy a property spec into the snapshot.
        """
        snapshot_layer = Sdf.Layer.CreateAnonymous("texture_replacements_state.usda")
        prim_paths = frozenset(path for path in self._iter_prim_paths() if target_layer.GetPrimAtPath(path) is not None)
        for property_path in self._property_paths:
            if target_layer.GetAttributeAtPath(property_path) is None:
                continue
            Sdf.CreatePrimInLayer(snapshot_layer, property_path.GetPrimPath())
            if not Sdf.CopySpec(target_layer, property_path, snapshot_layer, property_path):
                raise RuntimeError(f"Could not capture the texture property state: {property_path}")
        return _LayerState(snapshot_layer, prim_paths)

    def _state_matches(self, target_layer: Sdf.Layer, expected_state: _LayerState) -> bool:
        """Return whether all target property specs still match a captured state."""
        return self._capture_state(target_layer).layer.ExportToString() == expected_state.layer.ExportToString()

    def _remove_inert_prim_specs(self, target_layer: Sdf.Layer, retained_paths: frozenset[Sdf.Path]) -> None:
        """Remove only now-inert ancestor specs absent from the destination state."""
        for prim_path in self._iter_prim_paths():
            if prim_path in retained_paths:
                continue
            prim_spec = target_layer.GetPrimAtPath(prim_path)
            if prim_spec is not None and prim_spec.IsInert():
                remove_prim_spec(target_layer, prim_path)

    def _restore_state(self, target_layer: Sdf.Layer, state: _LayerState) -> None:
        """Restore captured property specs and remove newly empty ancestor specs.

        Args:
            target_layer: Layer receiving the captured state.
            state: Exact property and ancestor state to restore.

        Raises:
            RuntimeError: If USD cannot restore a captured property spec.
        """
        for property_path in self._property_paths:
            attribute_spec = target_layer.GetAttributeAtPath(property_path)
            if attribute_spec is not None:
                attribute_spec.owner.RemoveProperty(attribute_spec)

            if state.layer.GetAttributeAtPath(property_path) is None:
                continue
            Sdf.CreatePrimInLayer(target_layer, property_path.GetPrimPath())
            if not Sdf.CopySpec(state.layer, property_path, target_layer, property_path):
                raise RuntimeError(f"Could not restore the texture property state: {property_path}")
        self._remove_inert_prim_specs(target_layer, state.prim_paths)

    def _transition(self, target_layer: Sdf.Layer, destination: _LayerState, rollback: _LayerState) -> None:
        """Restore one complete state, rolling back the whole batch on failure."""
        try:
            self._restore_state(target_layer, destination)
            if not self._state_matches(target_layer, destination):
                raise RuntimeError("The texture replacement state did not match its expected postcondition")
        except Exception:
            self._restore_state(target_layer, rollback)
            raise

    def _apply_replacement(self, target_layer: Sdf.Layer, replacement: TextureReplacement) -> None:
        """Directly author or remove one prevalidated target-layer property."""
        property_path = replacement.property_path
        authored_value = self._get_authored_value(replacement)
        attribute_spec = target_layer.GetAttributeAtPath(property_path)
        if authored_value is None:
            if attribute_spec is not None:
                attribute_spec.owner.RemoveProperty(attribute_spec)
            return

        value_type = replacement.value_type
        if attribute_spec is None:
            prim_spec = Sdf.CreatePrimInLayer(target_layer, property_path.GetPrimPath())
            attribute_spec = Sdf.AttributeSpec(prim_spec, property_path.name, value_type)
        elif attribute_spec.typeName != value_type:
            raise RuntimeError(f"The texture property type does not match the requested value: {property_path}")
        attribute_spec.default = authored_value

    def _verify_authored_values(self, target_layer: Sdf.Layer) -> None:
        """Verify every target-layer opinion after the complete batch is applied."""
        for replacement in self._replacements:
            property_path = replacement.property_path
            attribute_spec = target_layer.GetAttributeAtPath(property_path)
            expected_value = self._get_authored_value(replacement)
            if expected_value is None:
                if attribute_spec is not None:
                    raise RuntimeError(f"The texture property was not removed from the target layer: {property_path}")
                continue
            if attribute_spec is None or attribute_spec.default != expected_value:
                raise RuntimeError(f"The texture property was not authored with the expected value: {property_path}")

    def do(self) -> None:
        """Apply the complete batch on first execution, or restore its captured redo state."""
        target_layer = self._resolve_target_layer()
        if self._after is not None:
            if self._before is None:
                raise RuntimeError("The texture replacement command has no captured pre-state")
            if not self._state_matches(target_layer, self._before):
                raise RuntimeError(
                    "Cannot redo texture replacements because a target property changed outside the command stack"
                )
            self._transition(target_layer, self._after, self._before)
            return

        self._validate_replacements()
        self._verify_expected_values(target_layer)
        self._before = self._capture_state(target_layer)
        try:
            for replacement in self._replacements:
                self._apply_replacement(target_layer, replacement)
            self._remove_inert_prim_specs(target_layer, self._before.prim_paths)
            self._verify_authored_values(target_layer)
            self._after = self._capture_state(target_layer)
        except Exception:
            self._restore_state(target_layer, self._before)
            raise

    def undo(self) -> None:
        """Restore the complete captured pre-state unless a target property now conflicts."""
        if self._before is None or self._after is None:
            return
        target_layer = self._resolve_target_layer()
        if not self._state_matches(target_layer, self._after):
            raise RuntimeError(
                "Cannot undo texture replacements because a target property changed outside the command stack"
            )
        self._transition(target_layer, self._before, self._after)


omni.kit.commands.register(ReplaceTexturesCommand)

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

import contextlib
from typing import Any

import omni.kit.commands
import omni.ui as ui
import omni.usd
from omni.flux.property_widget_builder.widget import ClaimResult, FieldBuilder, Item
from omni.flux.utils.widget.color_gradient import ColorGradientWidget
from pxr import Sdf, Tf, Usd

from ..extension import get_usd_listener_instance as _get_usd_listener_instance
from ..items import _BaseUSDAttributeItem
from ..listener import DisableAllListenersBlock as _DisableAllListenersBlock
from .base import _generate_identifier

__all__ = ("GRADIENT_FIELD_BUILDERS", "UsdColorGradientWidget")

_GRADIENT_SUFFIXES = frozenset({"times", "values"})
_PRIMARY_SUFFIX = "values"
_PRIMVAR_PREFIX = "primvars:"

_COLOR_ARRAY_TYPES = {
    Sdf.ValueTypeNames.Color3fArray,
    Sdf.ValueTypeNames.Color3dArray,
    Sdf.ValueTypeNames.Color3hArray,
    Sdf.ValueTypeNames.Color4fArray,
    Sdf.ValueTypeNames.Color4dArray,
    Sdf.ValueTypeNames.Color4hArray,
}


def _is_color_array(item: _BaseUSDAttributeItem) -> bool:
    """Check if the item's USD attribute is a color array type."""
    try:
        type_name = Sdf.ValueTypeNames.Find(item.value_models[0].metadata.get(Sdf.PrimSpec.TypeNameKey, ""))
    except (IndexError, AttributeError):
        return False
    return type_name in _COLOR_ARRAY_TYPES


def _claim_gradients(items: list[Item]) -> ClaimResult:
    """Bucket items by base name; satisfy only when both suffixes present and values is a color array."""
    groups: dict[str, dict[str, Item]] = {}
    for item in items:
        if not isinstance(item, _BaseUSDAttributeItem):
            continue
        attr_paths = getattr(item, "_attribute_paths", None)
        if not attr_paths:
            continue
        parts = attr_paths[0].name.rsplit(":", 1)
        if len(parts) != 2 or parts[1] not in _GRADIENT_SUFFIXES:
            continue
        if parts[1] == "values" and not _is_color_array(item):
            continue
        groups.setdefault(parts[0], {})[parts[1]] = item

    primary: list[Item] = []
    companions: list[Item] = []
    for collected in groups.values():
        if collected.keys() < _GRADIENT_SUFFIXES:
            continue
        for suffix, item in collected.items():
            (primary if suffix == _PRIMARY_SUFFIX else companions).append(item)

    return ClaimResult(primary=primary, companions=companions)


# ---------------------------------------------------------------------------
# USD helpers
# ---------------------------------------------------------------------------


def _read_gradient(context_name: str, prim_path: str, base_name: str):
    """Read times + color values from USD, return keyframes list."""
    stage = omni.usd.get_context(context_name).get_stage()
    prim = stage.GetPrimAtPath(prim_path)
    times_attr = prim.GetAttribute(f"{base_name}:times")
    values_attr = prim.GetAttribute(f"{base_name}:values")
    times = times_attr.Get() or []
    values = values_attr.Get() or []
    return [(float(t), tuple(float(c) for c in v)) for t, v in zip(times, values)]


def _snapshot_gradient(context_name: str, prim_path: str, base_name: str) -> dict[str, Any]:
    """Snapshot current times + values for undo."""
    stage = omni.usd.get_context(context_name).get_stage()
    prim = stage.GetPrimAtPath(prim_path)
    result = {}
    for suffix in ("times", "values"):
        attr = prim.GetAttribute(f"{base_name}:{suffix}")
        result[suffix] = attr.Get() if attr and attr.IsValid() else None
    return result


@contextlib.contextmanager
def _suppress_panel_listener():
    """Suppress the property panel's USD listener if available."""
    listener = _get_usd_listener_instance()
    if listener:
        try:
            with _DisableAllListenersBlock(listener):
                yield
        except AttributeError:
            yield
    else:
        yield


def _write_gradient_direct(context_name: str, prim_path: str, base_name: str, times, values):
    """Write gradient to USD directly (no command, no undo entry). Suppresses panel listener."""
    with _suppress_panel_listener():
        stage = omni.usd.get_context(context_name).get_stage()
        prim = stage.GetPrimAtPath(prim_path)
        prim.GetAttribute(f"{base_name}:times").Set(times)
        prim.GetAttribute(f"{base_name}:values").Set(values)


def _restore_gradient(context_name: str, prim_path: str, base_name: str, old_values: dict[str, Any]):
    """Restore snapshotted gradient values (for undo). Suppresses panel listener."""
    with _suppress_panel_listener():
        stage = omni.usd.get_context(context_name).get_stage()
        prim = stage.GetPrimAtPath(prim_path)
        for suffix, value in old_values.items():
            attr = prim.GetAttribute(f"{base_name}:{suffix}")
            if attr and attr.IsValid() and value is not None:
                attr.Set(value)


# ---------------------------------------------------------------------------
# Kit Command
# ---------------------------------------------------------------------------


class SetGradientPrimvarsCommand(omni.kit.commands.Command):
    """Atomically set gradient primvars (times + values) with undo support.

    Args:
        prim_path: USD prim path.
        base_name: Primvar base name (e.g. "primvars:particle:color").
        times: New time values.
        values: New color values.
        usd_context_name: USD context name.
        old_values: Pre-captured old values for undo (from drag snapshot).
    """

    def __init__(
        self,
        prim_path: str,
        base_name: str,
        times: list,
        values: list,
        usd_context_name: str = "",
        old_values: dict[str, Any] | None = None,
    ):
        self._prim_path = prim_path
        self._base_name = base_name
        self._times = times
        self._values = values
        self._usd_context_name = usd_context_name
        self._old_values: dict[str, Any] | None = old_values

    def do(self) -> None:
        if self._old_values is None:
            self._old_values = _snapshot_gradient(self._usd_context_name, self._prim_path, self._base_name)
        _write_gradient_direct(self._usd_context_name, self._prim_path, self._base_name, self._times, self._values)

    def undo(self) -> None:
        _restore_gradient(self._usd_context_name, self._prim_path, self._base_name, self._old_values)


omni.kit.commands.register(SetGradientPrimvarsCommand)


# ---------------------------------------------------------------------------
# USD-aware gradient widget
# ---------------------------------------------------------------------------


class UsdColorGradientWidget(ColorGradientWidget):
    """ColorGradientWidget with USD undo support.

    RAII: registers Tf.Notice on popup open, revokes on popup close.
    All USD writes go through Kit commands for undo/redo.
    Continuous edits (drag, color picker) are grouped into single undo entries.
    """

    def __init__(self, context_name: str, prim_path: str, base_name: str, **kwargs):
        self._usd_context_name = context_name
        self._usd_prim_path = prim_path
        self._usd_base_name = base_name
        self._usd_listener = None
        self._is_writing = False
        self._is_dragging = False
        self._drag_committed = False
        self._drag_snapshot: dict[str, Any] = {}

        keyframes = _read_gradient(context_name, prim_path, base_name)
        super().__init__(
            keyframes=keyframes,
            on_gradient_changed_fn=self._on_usd_changed_callback,
            **kwargs,
        )
        self.subscribe_drag_started_fn(self._on_usd_drag_started)
        self.subscribe_drag_ended_fn(self._on_usd_drag_ended)

    def _show_popup(self) -> None:
        super()._show_popup()
        if not self._usd_listener:
            self._usd_listener = Tf.Notice.Register(
                Usd.Notice.ObjectsChanged,
                self._on_usd_notice,
                omni.usd.get_context(self._usd_context_name).get_stage(),
            )

    def _hide_popup(self) -> None:
        super()._hide_popup()
        self._usd_listener = None

    def _on_usd_changed_callback(self, times, values):
        # The base widget fires _fire_changed() immediately after _fire_drag_ended().
        # Since drag-end already committed a command, suppress this redundant write.
        if self._drag_committed:
            self._drag_committed = False
            return
        if self._is_dragging:
            self._is_writing = True
            try:
                _write_gradient_direct(self._usd_context_name, self._usd_prim_path, self._usd_base_name, times, values)
            finally:
                self._is_writing = False
        else:
            self._is_writing = True
            try:
                omni.kit.commands.execute(
                    "SetGradientPrimvars",
                    prim_path=self._usd_prim_path,
                    base_name=self._usd_base_name,
                    times=times,
                    values=values,
                    usd_context_name=self._usd_context_name,
                )
            finally:
                self._is_writing = False

    def _on_usd_drag_started(self):
        self._is_dragging = True
        self._drag_snapshot = _snapshot_gradient(self._usd_context_name, self._usd_prim_path, self._usd_base_name)

    def _on_usd_drag_ended(self):
        self._is_dragging = False
        if not self._drag_snapshot:
            return
        current = _snapshot_gradient(self._usd_context_name, self._usd_prim_path, self._usd_base_name)
        self._is_writing = True
        try:
            omni.kit.commands.execute(
                "SetGradientPrimvars",
                prim_path=self._usd_prim_path,
                base_name=self._usd_base_name,
                times=current.get("times", []),
                values=current.get("values", []),
                usd_context_name=self._usd_context_name,
                old_values=self._drag_snapshot,
            )
        finally:
            self._is_writing = False
        self._drag_snapshot = {}
        self._drag_committed = True

    def _on_usd_notice(self, notice: Usd.Notice.ObjectsChanged, stage: Usd.Stage):
        if self._is_writing:
            return
        if stage != omni.usd.get_context(self._usd_context_name).get_stage():
            return
        prefix = f"{self._usd_prim_path}.{self._usd_base_name}"
        for path in notice.GetChangedInfoOnlyPaths():
            if str(path).startswith(prefix):
                self._reload_from_usd()
                return
        for path in notice.GetResyncedPaths():
            if str(path).startswith(prefix):
                self._reload_from_usd()
                return

    def _reload_from_usd(self):
        new_kfs = _read_gradient(self._usd_context_name, self._usd_prim_path, self._usd_base_name)
        self.set_keyframes(new_kfs)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def _gradient_builder(item):
    identifier = _generate_identifier(item)
    attr_path = item._attribute_paths[0]  # noqa: SLF001
    prim_path = str(attr_path.GetPrimPath())
    base_name = attr_path.name.rsplit(":", 1)[0]

    frame = ui.Frame(identifier=identifier)
    with frame:
        UsdColorGradientWidget(item.context_name, prim_path, base_name)
    return [frame]


GRADIENT_FIELD_BUILDERS = [
    FieldBuilder(claim_func=_claim_gradients, build_func=_gradient_builder),
]

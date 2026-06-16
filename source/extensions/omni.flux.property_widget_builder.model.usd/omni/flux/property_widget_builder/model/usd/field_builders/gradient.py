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

from typing import Any

import omni.ui as ui
from omni.flux.property_widget_builder.widget import ClaimResult, FieldBuilder, Item
from omni.flux.utils.common.interactive_usd_notices import InteractionToken
from omni.flux.utils.widget.color_gradient import ColorGradientWidget
from pxr import Sdf

from ..grouped_keys_primvar import PropertyGroupedKeysModel
from ..items import _BaseUSDAttributeItem
from ..logical_group_constants import GRADIENT_LOGICAL_GROUP_DEFINITION, GRADIENT_LOGICAL_SUFFIXES
from .base import _generate_identifier

__all__ = ("GRADIENT_FIELD_BUILDERS", "UsdColorGradientWidget")

_PRIMARY_SUFFIX = "values"
_FIELD_LEADING_SPACER_WIDTH = 8

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
    """Bucket items by base name; satisfy only when both suffixes present and values is a color array.

    Args:
        items: Property-panel items to scan for gradient suffix companions.

    Returns:
        Claim result containing the primary gradient rows and companion rows
        consumed by those primaries.
    """
    groups: dict[str, dict[str, Item]] = {}
    for item in items:
        if not isinstance(item, _BaseUSDAttributeItem):
            continue
        attr_paths = item.attribute_paths
        if not attr_paths:
            continue
        parts = attr_paths[0].name.rsplit(":", 1)
        if len(parts) != 2 or parts[1] not in GRADIENT_LOGICAL_SUFFIXES:
            continue
        if parts[1] == "values" and not _is_color_array(item):
            continue
        groups.setdefault(parts[0], {})[parts[1]] = item

    primary: list[Item] = []
    companions: list[Item] = []
    for collected in groups.values():
        if collected.keys() < GRADIENT_LOGICAL_SUFFIXES:
            continue
        logical_group_items = [collected[suffix] for suffix in sorted(GRADIENT_LOGICAL_SUFFIXES)]
        collected[_PRIMARY_SUFFIX].logical_group_items = logical_group_items
        collected[_PRIMARY_SUFFIX].logical_group_definition = GRADIENT_LOGICAL_GROUP_DEFINITION
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
        manager = _DisableAllListenersBlock(listener)
        try:
            manager.__enter__()
        except Exception:  # noqa: BLE001
            # __init__ appends before __enter__ can discover a stale listener. Keep the USD edit going, but
            # remove the half-open block so later listener suppression does not stay enabled forever.
            with contextlib.suppress(ValueError):
                manager.LIST_SELF.remove(manager)
            yield
            return

        try:
            yield
        finally:
            manager.__exit__(None, None, None)
    else:
        yield

def _write_gradient_direct(context_name: str, prim_path: str, base_name: str, times, values):
    """Write gradient to USD directly (no command, no undo entry). Suppresses panel listener."""
    stage = omni.usd.get_context(context_name).get_stage()
    with _defer_usd_notices(stage), _suppress_panel_listener():
        prim = stage.GetPrimAtPath(prim_path)
        prim.GetAttribute(f"{base_name}:times").Set(times)
        prim.GetAttribute(f"{base_name}:values").Set(values)

def _restore_gradient(context_name: str, prim_path: str, base_name: str, old_values: dict[str, Any]):
    """Restore snapshotted gradient values (for undo). Suppresses panel listener."""
    stage = omni.usd.get_context(context_name).get_stage()
    with _defer_usd_notices(stage), _suppress_panel_listener():
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
    """Thin ColorGradientWidget adapter that delegates USD behavior to its row item."""

    def __init__(self, model: PropertyGroupedKeysModel, **kwargs: Any) -> None:
        """Create a gradient widget bound to the row-owned USD grouped-key model.

        Args:
            model: USD grouped-key model that reads/writes the gradient payload.
            **kwargs: UI construction options forwarded to ``ColorGradientWidget``.
        """
        self._model = model
        group_ids = model.group_ids
        super().__init__(
            model=model,
            group_id=group_ids[0],
            **kwargs,
        )

    @property
    def _usd_notice_token(self) -> InteractionToken | None:
        """Return the row model's active USD notice token for compatibility with older tests.

        Returns:
            Active interaction token, or ``None`` when the popup edit session is closed.
        """
        return self._model.usd_notice_token

    def _show_popup(self) -> None:
        """Run any row pre-open work before showing the gradient popup."""
        if callable(self._model.pre_open_callback):
            self._model.pre_open_callback(self._show_popup_after_pre_open)
            return

        self._show_popup_impl()

    def _show_popup_after_pre_open(self) -> None:
        """Continue popup opening after pre-open work; the base popup path refreshes model data."""
        self._show_popup_impl()

    def _show_popup_impl(self) -> None:
        """Begin the row edit session and show the base gradient popup."""
        self._model.begin_session()
        try:
            super()._show_popup()
        except Exception:
            self._model.finish_session()
            raise

    def _on_window_close(self, visible: bool) -> None:
        """Finish the row edit session when the popup window becomes hidden.

        Args:
            visible: Current popup window visibility.
        """
        super()._on_window_close(visible)
        if not visible and self._model is not None:
            self._model.finish_session()

    def destroy(self) -> None:
        """Release callback references and row-owned edit listeners."""
        model = self._model
        try:
            super().destroy()
        finally:
            if model is not None:
                model.destroy()
            self._model = None


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def _gradient_builder(item: Item) -> list[ui.Widget]:
    """Build a USD-backed color gradient field for the primary gradient item.

    Args:
        item: Primary gradient item claimed by ``_claim_gradients``.

    Returns:
        Widgets to render in the value column.
    """
    identifier = _generate_identifier(item)
    if not item.attribute_paths:
        return []

    frame = ui.Frame(identifier=identifier)
    with frame:
        with ui.HStack(spacing=0):
            ui.Spacer(width=ui.Pixel(_FIELD_LEADING_SPACER_WIDTH))
            UsdColorGradientWidget(PropertyGroupedKeysModel.from_item(item))
    return [frame]


GRADIENT_FIELD_BUILDERS = [
    FieldBuilder(claim_func=_claim_gradients, build_func=_gradient_builder),
]

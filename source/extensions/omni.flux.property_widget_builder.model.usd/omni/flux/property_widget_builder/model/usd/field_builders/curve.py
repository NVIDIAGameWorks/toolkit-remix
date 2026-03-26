"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
* SPDX-License-Identifier: Apache-2.0

Curve field builders -- claims curve attribute groups and renders editor buttons.

Handles two modes:
- Edit-group outlets (USDAttributeEditGroupItem): multi-curve editor button.
- Standalone curves (_BaseUSDAttributeItem): single-curve editor button.
"""

from __future__ import annotations

import carb.input
import omni.usd
import omni.ui as ui
from omni.flux.curve_editor.widget import CurveEditorLayout, CurveEditorWidget, PrimvarCurveModel
from omni.flux.fcurve.widget import CurveBounds, FCurve, FCurveKey
from omni.flux.property_widget_builder.widget import ClaimResult, FieldBuilder, Item

from ..extension import get_usd_listener_instance as _get_usd_listener_instance
from ..items import USDAttributeEditGroupItem, _BaseUSDAttributeItem
from ..listener import DisableAllListenersBlock as _DisableAllListenersBlock
from .base import _generate_identifier


__all__ = ("CURVE_FIELD_BUILDERS",)

_CURVE_SUFFIXES = frozenset(
    {
        "times",
        "values",
        "inTangentTimes",
        "inTangentValues",
        "inTangentTypes",
        "outTangentTimes",
        "outTangentValues",
        "outTangentTypes",
        "tangentBrokens",
    }
)
_PRIMARY_SUFFIX = "values"
_PRIMVAR_PREFIX = "primvars:"
_EDITOR_WIDTH = 700
_EDITOR_HEIGHT = 400


# ---------------------------------------------------------------------------
# Claiming
# ---------------------------------------------------------------------------


def _claim_curves(items: list[Item]) -> ClaimResult:
    """Claim curve groups. Outlets become primary; tagged items become companions."""
    # Index outlets by layout identity
    outlets: dict[int, list[Item]] = {}
    for item in items:
        if isinstance(item, USDAttributeEditGroupItem):
            outlets.setdefault(id(item.edit_group_layout), []).append(item)

    # Bucket _BaseUSDAttributeItem by curve_id, validate 9 suffixes
    groups: dict[str, dict[str, _BaseUSDAttributeItem]] = {}
    for item in items:
        if not isinstance(item, _BaseUSDAttributeItem):
            continue
        paths = getattr(item, "_attribute_paths", None)
        if not paths:
            continue
        parts = paths[0].name.rsplit(":", 1)
        if len(parts) == 2 and parts[1] in _CURVE_SUFFIXES:
            groups.setdefault(parts[0], {})[parts[1]] = item

    primary: list[Item] = []
    companions: list[Item] = []

    for collected in groups.values():
        if collected.keys() < _CURVE_SUFFIXES:
            continue
        values_item = collected[_PRIMARY_SUFFIX]
        layout_id = id(values_item.edit_group_layout) if values_item.edit_group_layout else None

        if layout_id and layout_id in outlets:
            # Outlet handles this group -- all items are companions
            companions.extend(collected.values())
        else:
            # Standalone curve -- :values is primary
            for suffix, item in collected.items():
                (primary if suffix == _PRIMARY_SUFFIX else companions).append(item)

    # Outlets themselves are primaries
    for outlet_list in outlets.values():
        primary.extend(outlet_list)

    return ClaimResult(primary=primary, companions=companions)


# ---------------------------------------------------------------------------
# Panel layout -> CurveEditorLayout transform
# ---------------------------------------------------------------------------


def _panel_to_editor_layout(layout: dict) -> dict:
    """Transform a panel-level layout dict into a CurveEditorLayout for the editor."""
    curve_map: dict[str, str] = layout.get("curve_map", {})

    # Index curves by their parent path in the layout tree.
    # curve_map values: plain "path" string OR {"path": ..., "display_color": ..., "display_name": ...}
    curves_by_parent: dict[str, list[dict]] = {}
    for full_primvar, raw_entry in curve_map.items():
        entry = {"path": raw_entry} if isinstance(raw_entry, str) else raw_entry
        rel_path = entry["path"]
        parts = rel_path.rsplit("/", 1)
        parent_path = parts[0] if len(parts) > 1 else ""
        leaf_name = parts[-1]
        model_id = _strip_primvar_prefix(full_primvar)
        curve_entry = {
            "id": model_id,
            "display_name": entry.get("display_name", leaf_name.upper() if len(leaf_name) == 1 else leaf_name),
        }
        if "display_color" in entry:
            curve_entry["display_color"] = entry["display_color"]
        curves_by_parent.setdefault(parent_path, []).append(curve_entry)

    def _build_node(node: dict, path_prefix: str) -> dict:
        result: dict = {"display_name": node.get("display_name", "")}
        if "tooltip" in node:
            result["tooltip"] = node["tooltip"]
        if "display_color" in node:
            result["display_color"] = node["display_color"]
        result["curves"] = curves_by_parent.get(path_prefix, [])
        children = {}
        for child_id, child in node.get("children", {}).items():
            child_path = f"{path_prefix}/{child_id}" if path_prefix else child_id
            children[child_id] = _build_node(child, child_path)
        result["children"] = children
        return result

    return _build_node(layout, "")


# ---------------------------------------------------------------------------
# Editor window
# ---------------------------------------------------------------------------


class _QuietPrimvarCurveModel(PrimvarCurveModel):
    """Suppresses property panel USD listener during interactive writes."""

    def commit_curve(self, curve_id: str, curve: FCurve) -> None:
        with _DisableAllListenersBlock(_get_usd_listener_instance()):
            super().commit_curve(curve_id, curve)


def _create_default_curve(model: PrimvarCurveModel, curve_id: str) -> None:
    """Create a default linear curve with two keys."""
    default_curve = FCurve(
        id=curve_id,
        keys=[
            FCurveKey(time=0.0, value=0.0),
            FCurveKey(time=1.0, value=1.0),
        ],
    )
    model.commit_curve(curve_id, default_curve)


def _delete_curve(model: PrimvarCurveModel, curve_id: str) -> None:
    """Delete a curve by committing an empty FCurve."""
    model.commit_curve(curve_id, FCurve(id=curve_id, keys=[]))


def _open_curve_editor(
    prim_path: str,
    curve_ids: list[str],
    context_name: str,
    editor_layout: CurveEditorLayout | None = None,
    per_curve_bounds: dict[str, CurveBounds] | None = None,
):
    title = editor_layout.get("display_name", curve_ids[0]) if editor_layout else curve_ids[0]
    window = ui.Window(
        f"CurveEditor_{title}",
        width=_EDITOR_WIDTH,
        height=_EDITOR_HEIGHT,
        flags=ui.WINDOW_FLAGS_POPUP | ui.WINDOW_FLAGS_NO_SCROLLBAR | ui.WINDOW_FLAGS_NO_COLLAPSE,
        padding_x=0,
        padding_y=0,
        exclusive_keyboard=True,
    )
    window.set_key_pressed_fn(
        lambda key, mod, down: setattr(window, "visible", False)
        if key == int(carb.input.KeyboardInput.ESCAPE) and down
        else None
    )
    model = _QuietPrimvarCurveModel(
        prim_path=prim_path,
        curve_ids=curve_ids,
        usd_context_name=context_name,
    )
    with window.frame:
        widget = CurveEditorWidget(
            model=model,
            layout=editor_layout,
            per_curve_bounds=per_curve_bounds or {},
            on_create_curve=lambda cid: _create_default_curve(model, cid),
            on_delete_curve=lambda cid: _delete_curve(model, cid),
        )
    widget.fit_all()


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def _curve_builder(item):
    if isinstance(item, USDAttributeEditGroupItem):
        return _build_edit_group_button(item)
    return _build_single_curve_button(item)


def _strip_primvar_prefix(name: str) -> str:
    return name.removeprefix(_PRIMVAR_PREFIX)


def _read_per_curve_bounds(
    prim_path: str,
    curve_ids: list[str],
    context_name: str,
) -> dict[str, CurveBounds]:
    """Read per-curve value bounds from USD ``customData.limits``.

    Time bounds come from the ``:times`` attribute; value bounds from ``:values``.
    Returns one ``CurveBounds`` per curve_id that has schema metadata.
    """
    stage = omni.usd.get_context(context_name).get_stage()
    prim = stage.GetPrimAtPath(prim_path) if stage else None
    result: dict[str, CurveBounds] = {}
    if not prim or not prim.IsValid():
        return result

    for cid in curve_ids:
        t_min, t_max = 0.0, 1.0
        v_min, v_max = -1e6, 1e6

        times_attr = prim.GetAttribute(f"primvars:{cid}:times")
        if times_attr and times_attr.IsValid():
            custom = times_attr.GetCustomDataByKey("limits")
            if custom:
                hard = custom.get("hard", {})
                lo = hard.get("minimum")
                hi = hard.get("maximum")
                if isinstance(lo, (int, float)):
                    t_min = float(lo)
                if isinstance(hi, (int, float)):
                    t_max = float(hi)

        values_attr = prim.GetAttribute(f"primvars:{cid}:values")
        if values_attr and values_attr.IsValid():
            custom = values_attr.GetCustomDataByKey("limits")
            if custom:
                hard = custom.get("hard", {})
                lo = hard.get("minimum")
                hi = hard.get("maximum")
                if isinstance(lo, (int, float)):
                    v_min = float(lo)
                if isinstance(hi, (int, float)):
                    v_max = float(hi)

        result[cid] = CurveBounds(time_min=t_min, time_max=t_max, value_min=v_min, value_max=v_max)

    return result


def _build_edit_group_button(item: USDAttributeEditGroupItem):
    layout = item.edit_group_layout
    curve_ids = [_strip_primvar_prefix(k) for k in layout.get("curve_map", {})]
    editor_layout = _panel_to_editor_layout(layout)
    bounds = _read_per_curve_bounds(item.prim_path, curve_ids, item.context_name)

    return [
        ui.Button(
            layout.get("display_name", "Curves"),
            name="PropertiesWidgetField",
            tooltip=layout.get("tooltip", ""),
            clicked_fn=lambda: _open_curve_editor(
                item.prim_path,
                curve_ids,
                item.context_name,
                editor_layout,
                bounds,
            ),
        )
    ]


def _build_single_curve_button(item):
    identifier = _generate_identifier(item)
    attr_path = item._attribute_paths[0]  # noqa: SLF001
    prim_path = str(attr_path.GetPrimPath())
    curve_id = attr_path.name.rsplit(":", 1)[0]
    curve_id = curve_id.removeprefix(_PRIMVAR_PREFIX)
    context_name = item.context_name
    display_name = item.name_models[0].get_value_as_string() if item.name_models else curve_id
    bounds = _read_per_curve_bounds(prim_path, [curve_id], context_name)

    return [
        ui.Button(
            display_name,
            name="PropertiesWidgetField",
            identifier=identifier,
            clicked_fn=lambda: _open_curve_editor(
                prim_path,
                [curve_id],
                context_name,
                per_curve_bounds=bounds,
            ),
        )
    ]


CURVE_FIELD_BUILDERS = [
    FieldBuilder(claim_func=_claim_curves, build_func=_curve_builder),
]

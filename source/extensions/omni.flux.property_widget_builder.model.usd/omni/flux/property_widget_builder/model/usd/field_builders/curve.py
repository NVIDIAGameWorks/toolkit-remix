"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
* SPDX-License-Identifier: Apache-2.0

Curve field builders -- claims curve attribute groups and renders editor buttons.

Handles two modes:
- Logical group outlets (USDLogicalGroupOutletItem): multi-curve editor button.
- Standalone curves (_BaseUSDAttributeItem): single-curve editor button.
"""

from __future__ import annotations

from collections.abc import Callable

import carb.input
import omni.usd
import omni.ui as ui
from omni.flux.curve_editor.widget import CurveEditorLayout, CurveEditorWidget
from omni.flux.curve_editor.widget.payload import curve_to_payload
from omni.flux.fcurve.widget import CurveBounds, FCurve, FCurveKey
from omni.flux.property_widget_builder.widget import ClaimResult, FieldBuilder, Item

from ..curve_primvar import PropertyPrimvarCurveModel
from ..items import USDLogicalGroupOutletItem, _BaseUSDAttributeItem
from ..logical_group_constants import CURVE_LOGICAL_GROUP_DEFINITION, CURVE_LOGICAL_SUFFIXES, PRIMVAR_PREFIX
from ..logical_row import LogicalGroupDefinition
from ..logical_row import is_logical_group_mixed
from .base import _generate_identifier


__all__ = ("CURVE_FIELD_BUILDERS",)

_PRIMARY_SUFFIX = "values"
_FIELD_ROW_HEIGHT = 24
_FIELD_LEADING_SPACER_WIDTH = 8
_FIELD_VERTICAL_SPACER_HEIGHT = 2
_EDITOR_WIDTH = 700
_EDITOR_HEIGHT = 400


def _curve_attr_names(
    curve_id: str, logical_group_definition: LogicalGroupDefinition = CURVE_LOGICAL_GROUP_DEFINITION
) -> list[str]:
    """Return concrete primvar attr names for one curve id.

    Args:
        curve_id: Curve-editor id without the ``primvars:`` prefix.
        logical_group_definition: Suffix definition supported by the schema.

    Returns:
        Concrete USD attr names for the curve.
    """
    return [f"{PRIMVAR_PREFIX}{curve_id}:{suffix}" for suffix in logical_group_definition.suffixes]


# ---------------------------------------------------------------------------
# Claiming
# ---------------------------------------------------------------------------


def _claim_curves(items: list[Item]) -> ClaimResult:
    """Claim curve groups. Outlets become primary; tagged items become companions.

    Args:
        items: Candidate property tree items.

    Returns:
        Claim result with primary curve buttons and companion attrs hidden from regular rows.
    """
    # Index outlets by layout identity
    outlets: dict[int, list[USDLogicalGroupOutletItem]] = {}
    for item in items:
        if isinstance(item, USDLogicalGroupOutletItem):
            outlets.setdefault(id(item.edit_group_layout), []).append(item)

    # Bucket _BaseUSDAttributeItem by curve_id, validate the full curve payload.
    groups: dict[str, dict[str, _BaseUSDAttributeItem]] = {}
    for item in items:
        if not isinstance(item, _BaseUSDAttributeItem):
            continue
        paths = item.attribute_paths
        if not paths:
            continue
        parts = paths[0].name.rsplit(":", 1)
        if len(parts) == 2 and parts[1] in CURVE_LOGICAL_SUFFIXES:
            groups.setdefault(parts[0], {})[parts[1]] = item

    primary: list[Item] = []
    companions: list[Item] = []
    outlet_group_items: dict[int, list[Item]] = {}

    for collected in groups.values():
        if collected.keys() < CURVE_LOGICAL_SUFFIXES:
            continue
        values_item = collected[_PRIMARY_SUFFIX]
        layout_id = id(values_item.edit_group_layout) if values_item.edit_group_layout else None
        logical_group_items = [collected[suffix] for suffix in sorted(CURVE_LOGICAL_SUFFIXES)]

        if layout_id and layout_id in outlets:
            # Outlet handles this group -- all items are companions
            companions.extend(collected.values())
            outlet_group_items.setdefault(layout_id, []).extend(logical_group_items)
        else:
            # Standalone curve -- :values is primary
            values_item.logical_group_items = logical_group_items
            values_item.logical_group_definition = CURVE_LOGICAL_GROUP_DEFINITION
            for suffix, item in collected.items():
                (primary if suffix == _PRIMARY_SUFFIX else companions).append(item)

    # Outlets themselves are primaries
    for outlet_list in outlets.values():
        for outlet in outlet_list:
            outlet.logical_group_items = outlet_group_items.get(id(outlet.edit_group_layout), [])
        primary.extend(outlet_list)

    return ClaimResult(primary=primary, companions=companions)


# ---------------------------------------------------------------------------
# Panel layout -> CurveEditorLayout transform
# ---------------------------------------------------------------------------


def _panel_to_editor_layout(layout: dict) -> dict:
    """Transform a panel-level layout dict into a CurveEditorLayout for the editor.

    Args:
        layout: Property-panel edit-group layout metadata.

    Returns:
        Curve-editor layout dictionary with curve entries placed under their
        layout-tree parents.
    """
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
        """Build one editor-layout node from the panel layout tree.

        Args:
            node: Panel layout node.
            path_prefix: Slash-separated path to ``node`` within the panel layout.

        Returns:
            Curve editor layout node.
        """
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


def _create_default_curve(model: PropertyPrimvarCurveModel, curve_id: str) -> None:
    """Create a default linear curve with two keys.

    Args:
        model: USD-backed curve model that owns the curve payload.
        curve_id: Curve-editor id to populate.
    """
    default_curve = FCurve(
        id=curve_id,
        keys=[
            FCurveKey(time=0.0, value=0.0),
            FCurveKey(time=1.0, value=1.0),
        ],
    )
    model.commit_payload(curve_id, curve_to_payload(default_curve))


def _delete_curve(model: PropertyPrimvarCurveModel, curve_id: str) -> None:
    """Delete a curve by committing an empty FCurve.

    Args:
        model: USD-backed curve model that owns the curve payload.
        curve_id: Curve-editor id to clear.
    """
    model.commit_payload(curve_id, curve_to_payload(FCurve(id=curve_id, keys=[])))


def _open_curve_editor(
    target_paths: list[str],
    curve_ids: list[str],
    context_name: str,
    editor_layout: CurveEditorLayout | None = None,
    per_curve_bounds: dict[str, CurveBounds] | None = None,
    mixed_curve_ids: set[str] | None = None,
    logical_group_definition: LogicalGroupDefinition = CURVE_LOGICAL_GROUP_DEFINITION,
) -> None:
    """Open a curve editor window backed by a USD grouped-key model.

    Args:
        target_paths: Ordered prim paths controlled by the editor.
        curve_ids: Curve-editor ids to expose in the widget.
        context_name: USD context containing targets.
        editor_layout: Optional hierarchy and display metadata for multi-curve editors.
        per_curve_bounds: Optional value/time bounds keyed by curve id.
        mixed_curve_ids: Curve ids known to differ across selected targets.
        logical_group_definition: Suffix definition supported by the target schema.
    """
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

    def close_on_escape(key, _mod, down):
        if key == int(carb.input.KeyboardInput.ESCAPE) and down:
            window.visible = False

    window.set_key_pressed_fn(close_on_escape)
    try:
        model = PropertyPrimvarCurveModel(
            prim_paths=target_paths,
            curve_ids=curve_ids,
            usd_context_name=context_name,
            mixed_curve_ids=mixed_curve_ids,
            logical_group_definition=logical_group_definition,
        )
    except Exception:
        window.destroy()
        raise
    model_destroyed = False
    window_destroyed = False

    def destroy_model() -> None:
        """Destroy the grouped-key model once."""
        nonlocal model_destroyed
        if not model_destroyed:
            model_destroyed = True
            model.destroy()

    def destroy_window() -> None:
        """Destroy the editor window once."""
        nonlocal window_destroyed
        if not window_destroyed:
            window_destroyed = True
            window.destroy()

    def destroy_model_on_close(visible: bool) -> None:
        """Destroy the model/window after the editor window is hidden.

        Args:
            visible: Current window visibility.
        """
        if not visible:
            destroy_model()
            destroy_window()

    window.set_visibility_changed_fn(destroy_model_on_close)
    try:
        with window.frame:
            widget = CurveEditorWidget(
                model=model,
                layout=editor_layout,
                per_curve_bounds=per_curve_bounds or {},
                on_create_curve=lambda cid: _create_default_curve(model, cid),
                on_delete_curve=lambda cid: _delete_curve(model, cid),
            )
        widget.fit_all()
    except Exception:
        destroy_model()
        destroy_window()
        raise


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def _curve_builder(item: Item) -> list[ui.Widget]:
    """Build either a logical outlet curve button or a standalone curve button.

    Args:
        item: Claimed curve item.

    Returns:
        Widgets to render in the value column.
    """
    if isinstance(item, USDLogicalGroupOutletItem):
        return _build_edit_group_button(item)
    return _build_single_curve_button(item)


def _strip_primvar_prefix(name: str) -> str:
    """Remove the USD primvar namespace from a curve id.

    Args:
        name: Curve id or full primvar base name.

    Returns:
        Curve id without ``primvars:``.
    """
    return name.removeprefix(PRIMVAR_PREFIX)


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


def _build_edit_group_button(item: USDLogicalGroupOutletItem) -> list[ui.Widget]:
    """Build the multi-curve editor button for a logical outlet item.

    Args:
        item: Synthetic logical group outlet item.

    Returns:
        Button widgets for the row value column.
    """
    layout = item.edit_group_layout
    curve_ids = [_strip_primvar_prefix(k) for k in layout.get("curve_map", {})]
    editor_layout = _panel_to_editor_layout(layout)
    target_paths = item.get_target_paths()
    if not target_paths:
        return []
    source_path = target_paths[-1]
    bounds = _read_per_curve_bounds(source_path, curve_ids, item.context_name)

    def _open() -> None:
        """Open the multi-curve editor after pre-open callbacks run."""
        logical_group_definition = item.logical_group_definition
        mixed_curve_ids = {
            curve_id
            for curve_id in curve_ids
            if is_logical_group_mixed(
                item.context_name, target_paths, _curve_attr_names(curve_id, logical_group_definition)
            )
        }
        _open_curve_editor(
            target_paths,
            curve_ids,
            item.context_name,
            editor_layout,
            bounds,
            mixed_curve_ids,
            logical_group_definition,
        )

    with ui.HStack(height=ui.Pixel(_FIELD_ROW_HEIGHT)):
        ui.Spacer(width=ui.Pixel(_FIELD_LEADING_SPACER_WIDTH))
        with ui.VStack():
            ui.Spacer(height=ui.Pixel(_FIELD_VERTICAL_SPACER_HEIGHT))
            button = ui.Button(
                layout.get("display_name", "Curves"),
                style_type_name_override="PropertiesWidgetField",
                tooltip=layout.get("tooltip", ""),
                clicked_fn=_wrap_pre_open_callback(item, _open),
            )
            ui.Spacer(height=ui.Pixel(_FIELD_VERTICAL_SPACER_HEIGHT))
    return [button]


def _build_single_curve_button(item: _BaseUSDAttributeItem) -> list[ui.Widget]:
    """Build the single-curve editor button for a primary curve attr item.

    Args:
        item: Primary curve attr item.

    Returns:
        Button widgets for the row value column.
    """
    identifier = _generate_identifier(item)
    attr_paths = item.attribute_paths
    if not attr_paths:
        return []
    attr_path = attr_paths[0]
    target_paths = item.get_target_paths()
    if not target_paths:
        return []
    curve_id = attr_path.name.rsplit(":", 1)[0]
    curve_id = curve_id.removeprefix(PRIMVAR_PREFIX)
    context_name = item.context_name
    display_name = item.name_models[0].get_value_as_string() if item.name_models else curve_id
    bounds = _read_per_curve_bounds(target_paths[-1], [curve_id], context_name)

    def _open() -> None:
        """Open the single-curve editor after pre-open callbacks run."""
        mixed_curve_ids = (
            {curve_id} if is_logical_group_mixed(context_name, target_paths, _curve_attr_names(curve_id)) else set()
        )
        _open_curve_editor(
            target_paths,
            [curve_id],
            context_name,
            per_curve_bounds=bounds,
            mixed_curve_ids=mixed_curve_ids,
        )

    with ui.HStack(height=ui.Pixel(_FIELD_ROW_HEIGHT)):
        ui.Spacer(width=ui.Pixel(_FIELD_LEADING_SPACER_WIDTH))
        with ui.VStack():
            ui.Spacer(height=ui.Pixel(_FIELD_VERTICAL_SPACER_HEIGHT))
            button = ui.Button(
                display_name,
                style_type_name_override="PropertiesWidgetField",
                identifier=identifier,
                clicked_fn=_wrap_pre_open_callback(item, _open),
            )
            ui.Spacer(height=ui.Pixel(_FIELD_VERTICAL_SPACER_HEIGHT))
    return [button]


def _wrap_pre_open_callback(
    item: _BaseUSDAttributeItem | USDLogicalGroupOutletItem, action: Callable[[], None]
) -> Callable[[], None]:
    """Wrap an editor action with an optional pre-open callback.

    Args:
        item: Property widget item that owns pre-open callback behavior.
        action: Editor-opening action to run directly or after pre-open handling.

    Returns:
        Button click callback.
    """

    def _clicked() -> None:
        """Run the row pre-open callback when present, otherwise run the action directly."""
        item.run_pre_open_callback(action)

    return _clicked


CURVE_FIELD_BUILDERS = [
    FieldBuilder(claim_func=_claim_curves, build_func=_curve_builder),
]

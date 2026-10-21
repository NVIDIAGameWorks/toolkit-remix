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

import omni.usd
import omni.ui as ui
from carb.input import (
    KEYBOARD_MODIFIER_FLAG_ALT,
    KEYBOARD_MODIFIER_FLAG_CONTROL,
    KEYBOARD_MODIFIER_FLAG_SHIFT,
    KEYBOARD_MODIFIER_FLAG_SUPER,
    KeyboardInput,
)
from omni.flux.curve_editor.widget import CurveEditorLayout, CurveEditorWidget
from omni.flux.curve_editor.widget.payload import curve_to_payload
from omni.flux.fcurve.widget import CurveBounds, FCurve, FCurveKey
from omni.flux.property_widget_builder.delegates import FieldPopupWindow
from omni.flux.property_widget_builder.widget import ClaimResult, FieldBuilder, Item
from omni.kit.undo import group

from ..curve_primvar import PropertyPrimvarCurveModel
from ..items import USDLogicalGroupOutletItem, _BaseUSDAttributeItem
from ..logical_group_constants import CURVE_LOGICAL_GROUP_DEFINITION, CURVE_LOGICAL_SUFFIXES, PRIMVAR_PREFIX
from ..logical_row import LogicalGroupDefinition
from .base import _generate_identifier


__all__ = ("CURVE_FIELD_BUILDERS", "CurveFieldEditor")

_PRIMARY_SUFFIX = "values"
_FIELD_ROW_HEIGHT = 24
_FIELD_LEADING_SPACER_WIDTH = 8
_FIELD_VERTICAL_SPACER_HEIGHT = 2
_EDITOR_WIDTH = 700
_EDITOR_HEIGHT = 400


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
    curve_map: dict[str, str | dict] = layout.get("curve_map", {})

    # Index curves by their parent path in the layout tree.
    curves_by_parent: dict[str, list[dict]] = {}
    for full_primvar, raw_entry in curve_map.items():
        entry = {"path": raw_entry} if isinstance(raw_entry, str) else raw_entry
        rel_path = entry["path"]
        parts = rel_path.rsplit("/", 1)
        parent_path = parts[0] if len(parts) > 1 else ""
        leaf_name = parts[-1]
        model_id = full_primvar.removeprefix(PRIMVAR_PREFIX)
        curve_entry = {
            "id": model_id,
            "display_name": entry.get("display_name", leaf_name.upper() if len(leaf_name) == 1 else leaf_name),
        }
        if "display_color" in entry:
            curve_entry["display_color"] = entry["display_color"]
        if label_style_name := entry.get("label_style_name"):
            curve_entry["label_style_name"] = label_style_name
            normal_color = ui.Style.get_instance().default.get(f"Label::{label_style_name}", {}).get("color")
            if normal_color is not None:
                curve_entry["display_color"] = normal_color
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


class CurveFieldEditor(FieldPopupWindow):
    """Build Curve editing content with an owned model for each opening."""

    def __init__(
        self,
        *,
        target_paths: list[str],
        curve_ids: list[str],
        context_name: str,
        property_name: str,
        per_curve_bounds: dict[str, CurveBounds],
        pre_open_fn: Callable[[Callable[[], None]], None],
        editor_layout: CurveEditorLayout | None = None,
        logical_group_definition: LogicalGroupDefinition = CURVE_LOGICAL_GROUP_DEFINITION,
    ) -> None:
        """Construct a hidden Curve editor without acquiring its model or preparing row data.

        Args:
            target_paths: Ordered USD prim paths edited by this row.
            curve_ids: Curve-editor ids exposed by the content.
            context_name: Owning USD context for data and selection tracking.
            property_name: Friendly property name displayed in the window title.
            per_curve_bounds: Curve bounds captured while constructing the row.
            pre_open_fn: Row preparation that runs before acquiring the model.
            editor_layout: Optional hierarchy for multi-curve editors.
            logical_group_definition: Suffix definition supported by the target schema.
        """
        self._model: PropertyPrimvarCurveModel | None = None
        self._widget: CurveEditorWidget | None = None
        super().__init__(
            title=f"{property_name} - Curve Editor" if property_name else "Curve Editor",
            context_name=context_name,
            pre_open_fn=pre_open_fn,
        )
        self._target_paths = target_paths
        self._curve_ids = curve_ids
        self._context_name = context_name
        self._per_curve_bounds = per_curve_bounds
        self._editor_layout = editor_layout
        self._logical_group_definition = logical_group_definition

    def _build_content(self) -> None:
        """Build this opening's Curve controls after preparation."""
        model = self._model = PropertyPrimvarCurveModel(
            prim_paths=self._target_paths,
            curve_ids=self._curve_ids,
            usd_context_name=self._context_name,
            logical_group_definition=self._logical_group_definition,
            auto_begin_session=False,
        )

        if self._closing:
            return
        model.begin_session()
        if self._closing:
            return
        widget = self._widget = CurveEditorWidget(
            model=model,
            layout=self._editor_layout,
            per_curve_bounds=self._per_curve_bounds,
            on_create_curve=lambda curve_id: _create_default_curve(model, curve_id),
            on_delete_curve=lambda curve_id: model.commit_payload(
                curve_id, curve_to_payload(FCurve(id=curve_id, keys=[]))
            ),
            edit_context_factory=lambda: group(remove_if_empty=True),
            finalization_context_factory=model.create_finalization_context,
        )
        widget.fit_all()

    def _release_content(self) -> None:
        """Finish editor gestures before releasing this opening's storage model."""
        widget, self._widget = self._widget, None
        model, self._model = self._model, None
        try:
            if widget is not None:
                widget.destroy()
        finally:
            if model is not None:
                model.destroy()

    def _on_key_pressed(self, key: int, modifiers: int, is_down: bool) -> None:
        """Delete selected keys on a plain press while native text editing is inactive."""
        super()._on_key_pressed(key, modifiers, is_down)
        if (
            not self.is_open
            or self._widget is None
            or not is_down
            or key not in (int(KeyboardInput.DEL), int(KeyboardInput.NUMPAD_DEL))
            or modifiers
            & (
                KEYBOARD_MODIFIER_FLAG_CONTROL
                | KEYBOARD_MODIFIER_FLAG_SHIFT
                | KEYBOARD_MODIFIER_FLAG_ALT
                | KEYBOARD_MODIFIER_FLAG_SUPER
            )
        ):
            return
        fcurve_widget = self._widget.fcurve_widget
        # Native mouse gestures also set keyboard capture; the owned insertion can finish safely.
        if modifiers & ui.Widget.FLAG_WANT_CAPTURE_KEYBOARD and (
            fcurve_widget is None or not fcurve_widget.is_inserting_key
        ):
            return
        self._widget.delete_selected_keys()


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def _curve_builder(item: Item) -> list[ui.Widget] | None:
    """Build a Curve button for a logical outlet or standalone attribute.

    Args:
        item: Claimed curve item.
    Returns:
        Curve button for the value column, or ``None`` when unavailable.
    """
    if isinstance(item, USDLogicalGroupOutletItem):
        return _create_grouped_curve_button(item)
    return _create_single_curve_button(item)


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


def _create_grouped_curve_button(item: USDLogicalGroupOutletItem) -> list[ui.Widget] | None:
    """Build a multi-curve button for a logical outlet item.

    Args:
        item: Synthetic logical group outlet item.
    Returns:
        Curve button for the row value column, or ``None`` when unavailable.
    """
    layout = item.edit_group_layout
    curve_ids = [k.removeprefix(PRIMVAR_PREFIX) for k in layout.get("curve_map", {})]
    editor_layout = _panel_to_editor_layout(layout)
    logical_group_definition = item.logical_group_definition
    property_name = layout.get("display_name") or "Curves"

    return _create_curve_button(
        item,
        curve_ids=curve_ids,
        property_name=property_name,
        editor_layout=editor_layout,
        logical_group_definition=logical_group_definition,
        tooltip=layout.get("tooltip", ""),
    )


def _create_single_curve_button(item: _BaseUSDAttributeItem) -> list[ui.Widget] | None:
    """Build a single-curve button for a primary curve attribute item.

    Args:
        item: Primary curve attr item.
    Returns:
        Curve button for the row value column, or ``None`` when unavailable.
    """
    identifier = _generate_identifier(item)
    attr_paths = item.attribute_paths
    if not attr_paths:
        return None
    attr_path = attr_paths[0]
    curve_id = attr_path.name.rsplit(":", 1)[0]
    curve_id = curve_id.removeprefix(PRIMVAR_PREFIX)
    display_name = item.name_models[0].get_value_as_string() if item.name_models else ""
    display_name = display_name or curve_id

    return _create_curve_button(
        item,
        curve_ids=[curve_id],
        property_name=display_name,
        identifier=identifier,
    )


def _create_curve_button(
    item: _BaseUSDAttributeItem | USDLogicalGroupOutletItem,
    *,
    curve_ids: list[str],
    property_name: str,
    editor_layout: CurveEditorLayout | None = None,
    logical_group_definition: LogicalGroupDefinition = CURVE_LOGICAL_GROUP_DEFINITION,
    identifier: str = "",
    tooltip: str = "",
) -> list[ui.Widget] | None:
    """Build a Curve button with a lazy editor.

    Args:
        item: Property widget item that owns pre-open behavior.
        curve_ids: Curve-editor ids exposed by the widget.
        property_name: Friendly property name displayed in the window title.
        editor_layout: Optional hierarchy for multi-curve editors.
        logical_group_definition: Suffix definition supported by the target schema.
        identifier: Optional interactive-widget identifier.
        tooltip: Optional button tooltip.

    Returns:
        Curve button for the row value column, or ``None`` when unavailable.
    """
    target_paths = item.get_target_paths()
    if not target_paths:
        return None
    context_name = item.context_name
    per_curve_bounds = _read_per_curve_bounds(target_paths[-1], curve_ids, context_name)

    def open_editor() -> None:
        """Launch a fresh Curve editor using the button's current bounds."""
        anchor_rect = (
            button.screen_position_x,
            button.screen_position_y,
            button.computed_width,
            button.computed_height,
        )
        editor = CurveFieldEditor(
            target_paths=target_paths,
            curve_ids=curve_ids,
            property_name=property_name,
            context_name=context_name,
            per_curve_bounds=per_curve_bounds,
            pre_open_fn=item.run_pre_open_callback,
            editor_layout=editor_layout,
            logical_group_definition=logical_group_definition,
        )
        editor.open(
            preferred_size=(_EDITOR_WIDTH, _EDITOR_HEIGHT),
            anchor_rect=anchor_rect,
        )

    with ui.HStack(height=ui.Pixel(_FIELD_ROW_HEIGHT)):
        ui.Spacer(width=ui.Pixel(_FIELD_LEADING_SPACER_WIDTH))
        with ui.VStack():
            ui.Spacer(height=ui.Pixel(_FIELD_VERTICAL_SPACER_HEIGHT))
            button = ui.Button(
                property_name,
                identifier=identifier,
                tooltip=tooltip,
                style_type_name_override="PropertiesWidgetField",
                clicked_fn=open_editor,
            )
            ui.Spacer(height=ui.Pixel(_FIELD_VERTICAL_SPACER_HEIGHT))
    return [button]


CURVE_FIELD_BUILDERS = [
    FieldBuilder(claim_func=_claim_curves, build_func=_curve_builder),
]

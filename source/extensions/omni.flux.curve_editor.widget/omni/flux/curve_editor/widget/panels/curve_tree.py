"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
* SPDX-License-Identifier: Apache-2.0

Hierarchical curve tree panel built from a CurveEditorLayout dict.

Uses ScrollingTreeWidget with alternating rows, following the same
TreeView model/delegate pattern as the Stage Manager.
"""

from __future__ import annotations

from collections.abc import Callable

from omni import ui
from omni.flux.utils.widget.scrolling_tree_view import ScrollingTreeWidget
from omni.flux.utils.widget.tree_widget import TreeDelegateBase, TreeItemBase, TreeModelBase

from ..layout import CurveEditorLayout
from ..model import CurveModel

_ROW_HEIGHT = 24
_INDENT_PX = 12
_ICON_SIZE = 20
_DEFAULT_COLOR = 0xFFAAAAAA
_CHECKBOX_STYLE = {"background_color": 0xFF323232, "color": 0x4DFFFFFF, "border_radius": 2}


def _half_alpha(color: int) -> int:
    """Halve the alpha channel of an 0xAABBGGRR color."""
    alpha = (color >> 24) & 0xFF
    return (color & 0x00FFFFFF) | (((alpha >> 1) & 0xFF) << 24)


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------


class _CurveTreeItem(TreeItemBase):
    """A node in the curve hierarchy (group or leaf curve)."""

    def __init__(
        self,
        display_name: str,
        curve_id: str | None = None,
        color: int = _DEFAULT_COLOR,
        tooltip: str = "",
        has_data: bool = False,
        parent: TreeItemBase | None = None,
    ):
        super().__init__(parent=parent)
        self.display_name = display_name
        self.curve_id = curve_id
        self.color = color
        self.tooltip = tooltip
        self.visible = True
        self.has_data = has_data

    @property
    def is_curve(self) -> bool:
        return self.curve_id is not None

    @property
    def default_attr(self) -> dict[str, None]:
        return {**super().default_attr, "display_name": None, "curve_id": None, "color": None}

    @property
    def can_have_children(self) -> bool:
        return not self.is_curve


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


class CurveTreeModel(TreeModelBase[_CurveTreeItem]):
    """Builds a tree of _CurveTreeItem from a CurveEditorLayout dict."""

    def __init__(self, layout: CurveEditorLayout, curve_model: CurveModel | None = None):
        super().__init__()
        self._root_items: list[_CurveTreeItem] = []
        self._curve_model = curve_model
        self._build_from_layout(layout, inherited_color=_DEFAULT_COLOR, parent=None)

    @property
    def default_attr(self) -> dict[str, None]:
        return {"_root_items": None}

    def _has_curve_data(self, curve_id: str) -> bool:
        if not self._curve_model:
            return False
        curve = self._curve_model.get_curve(curve_id)
        return bool(curve and curve.keys)

    def _build_from_layout(
        self,
        node: dict,
        inherited_color: int,
        parent: _CurveTreeItem | None,
    ) -> None:
        color = node.get("display_color", inherited_color)

        for child_id, child in node.get("children", {}).items():
            child_color = child.get("display_color", color)
            group = _CurveTreeItem(
                display_name=child.get("display_name", child_id),
                color=child_color,
                tooltip=child.get("tooltip", ""),
                parent=parent,
            )
            if parent is None:
                self._root_items.append(group)
            self._build_from_layout(child, child_color, group)

        for curve in node.get("curves", []):
            cid = curve["id"]
            leaf = _CurveTreeItem(
                display_name=curve.get("display_name", cid),
                curve_id=cid,
                color=curve.get("display_color", color),
                has_data=self._has_curve_data(cid),
                parent=parent,
            )
            if parent is None:
                self._root_items.append(leaf)

    def refresh_has_data(self) -> None:
        """Re-check has_data on all leaf items and signal a redraw."""
        for item in self._iter_all(self._root_items):
            if item.is_curve:
                item.has_data = self._has_curve_data(item.curve_id)
        self._item_changed(None)

    def _iter_all(self, items):
        for item in items:
            yield item
            yield from self._iter_all(item.children)

    def get_item_children(self, item: _CurveTreeItem | None) -> list[_CurveTreeItem]:
        return self._root_items if item is None else item.children

    def get_item_value_model_count(self, item) -> int:
        return 1


# ---------------------------------------------------------------------------
# Delegate
# ---------------------------------------------------------------------------


class CurveTreeDelegate(TreeDelegateBase):
    """Renders each row: visibility checkbox + colored label + add/delete icon."""

    def __init__(
        self,
        on_visibility_changed: Callable[[str, bool], None] | None = None,
        on_create_curve: Callable[[str], None] | None = None,
        on_delete_curve: Callable[[str], None] | None = None,
    ):
        super().__init__()
        self._on_visibility_changed = on_visibility_changed
        self._on_create_curve = on_create_curve
        self._on_delete_curve = on_delete_curve

    @property
    def default_attr(self) -> dict[str, None]:
        return {
            **super().default_attr,
            "_on_visibility_changed": None,
            "_on_create_curve": None,
            "_on_delete_curve": None,
        }

    def build_branch(self, model, item, column_id, level, expanded):
        if column_id == 0:
            with ui.HStack(width=ui.Pixel(_INDENT_PX * (level + 2)), height=self.DEFAULT_IMAGE_ICON_SIZE):
                ui.Spacer()
                if model.can_item_have_children(item):
                    with ui.Frame(
                        width=0, mouse_released_fn=lambda x, y, b, m: self._item_expanded(b, item, not expanded)
                    ):
                        self._build_branch(model, item, column_id, level, expanded)

    def _build_widget(
        self,
        model: CurveTreeModel,
        item: _CurveTreeItem,
        column_id: int,
        level: int,
        expanded: bool,
    ) -> None:
        with ui.HStack(name="CurveEditorTreeRow", height=_ROW_HEIGHT, spacing=4):
            if item.is_curve:
                with ui.VStack(width=0):
                    ui.Spacer()
                    cb = ui.CheckBox(width=_ICON_SIZE, height=_ICON_SIZE, style=_CHECKBOX_STYLE)
                    cb.model.set_value(item.visible)
                    cb.model.add_value_changed_fn(
                        lambda m, it=item, mdl=model: self._toggle_visibility(it, m.get_value_as_bool(), mdl)
                    )
                    ui.Spacer()

            faint = item.is_curve and (not item.visible or not item.has_data)
            label_color = _half_alpha(item.color) if faint else item.color
            ui.Label(
                item.display_name,
                tooltip=item.tooltip,
                style={"font_size": 13, "color": label_color},
            )

            if item.is_curve:
                ui.Spacer()
                icon_name = "CurveEditorTreeDelete" if item.has_data else "CurveEditorTreeAdd"
                tip = "Delete curve data" if item.has_data else "Create default curve"
                fn = self._on_delete_curve if item.has_data else self._on_create_curve
                with ui.VStack(width=0):
                    ui.Spacer()
                    img = ui.Image(
                        "",
                        name=icon_name,
                        width=_ICON_SIZE,
                        height=_ICON_SIZE,
                        tooltip=tip,
                    )
                    img.set_mouse_pressed_fn(
                        lambda x, y, b, m, cid=item.curve_id, cb=fn: cb(cid) if cb else None,
                    )
                    ui.Spacer()

    def _toggle_visibility(self, item: _CurveTreeItem, visible: bool, model: CurveTreeModel) -> None:
        item.visible = visible
        model._item_changed(item)  # noqa: SLF001
        if self._on_visibility_changed and item.curve_id:
            self._on_visibility_changed(item.curve_id, visible)


# ---------------------------------------------------------------------------
# Public panel
# ---------------------------------------------------------------------------


class CurveTreePanel:
    """Hierarchical curve panel using ScrollingTreeWidget with alternating rows.

    Args:
        layout: CurveEditorLayout dict describing the hierarchy.
        curve_model: CurveModel to check authored state and create/delete curves.
        on_visibility_changed: Called with (curve_id, visible) when user toggles.
        on_create_curve: Called with curve_id when user clicks the add icon.
        on_delete_curve: Called with curve_id when user clicks the delete icon.
    """

    def __init__(
        self,
        layout: CurveEditorLayout,
        curve_model: CurveModel | None = None,
        on_visibility_changed: Callable[[str, bool], None] | None = None,
        on_create_curve: Callable[[str], None] | None = None,
        on_delete_curve: Callable[[str], None] | None = None,
    ):
        self._model = CurveTreeModel(layout, curve_model)
        self._delegate = CurveTreeDelegate(on_visibility_changed, on_create_curve, on_delete_curve)
        self._tree = ScrollingTreeWidget(
            self._model,
            self._delegate,
            alternating_rows=True,
            row_height=_ROW_HEIGHT,
            header_visible=False,
            root_visible=False,
        )

    def refresh(self):
        """Re-check curve data state and redraw icons."""
        self._model.refresh_has_data()
        self._tree.dirty_widgets()

    def destroy(self):
        self._tree = None
        if self._delegate:
            self._delegate.destroy()
            self._delegate = None

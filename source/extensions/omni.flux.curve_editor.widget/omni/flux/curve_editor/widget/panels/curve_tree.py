"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
* SPDX-License-Identifier: Apache-2.0

Hierarchical curve tree panel built from a CurveEditorLayout dict.

Uses ScrollingTreeWidget with alternating rows, following the same
TreeView model/delegate pattern as the Stage Manager.
"""

from __future__ import annotations

from asyncio import ensure_future
from collections.abc import Callable, Iterable

from omni import ui
from omni.flux.curve_editor.widget.payload import payload_to_curve
from omni.flux.utils.widget.scrolling_tree_view import ScrollingTreeWidget
from omni.flux.utils.widget.tree_widget import TreeDelegateBase, TreeItemBase, TreeModelBase
from omni.flux.utils.widget import GroupedKeysModel
from omni.kit.app import get_app

from ..layout import CurveEditorLayout

_ROW_HEIGHT = 24
_INDENT_PX = 12
_ICON_SIZE = 20
_DEFAULT_COLOR = 0xFFAAAAAA


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
        item_id: str,
        display_name: str,
        curve_id: str | None = None,
        color: int = _DEFAULT_COLOR,
        tooltip: str = "",
        has_data: bool = False,
        parent: TreeItemBase | None = None,
        label_style_name: str = "",
    ) -> None:
        """Create a group or channel row with its display metadata."""
        super().__init__(parent=parent)
        self.item_id = item_id
        self.display_name = display_name
        self.curve_id = curve_id
        self.color = color
        self.tooltip = tooltip
        self.has_data = has_data
        self.label_style_name = label_style_name

    @property
    def is_curve(self) -> bool:
        return self.curve_id is not None

    @property
    def default_attr(self) -> dict[str, None]:
        """Return attributes handled by inherited legacy cleanup."""
        return {**super().default_attr, "display_name": None, "curve_id": None, "color": None}

    def destroy(self) -> None:
        """Release the item identity and inherited tree state."""
        self.item_id = None
        super().destroy()

    @property
    def can_have_children(self) -> bool:
        return not self.is_curve


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


class CurveTreeModel(TreeModelBase[_CurveTreeItem]):
    """Builds a tree of _CurveTreeItem from a CurveEditorLayout dict."""

    def __init__(self, layout: CurveEditorLayout, curve_model: GroupedKeysModel | None = None) -> None:
        """Create a tree model from editor layout metadata.

        Args:
            layout: Curve editor hierarchy and curve display metadata.
            curve_model: Optional grouped-key model used to detect authored curve data.
        """
        super().__init__()
        self._root_items: list[_CurveTreeItem] = []
        self._curve_model = curve_model
        self._build_from_layout(layout, inherited_color=_DEFAULT_COLOR, parent=None)

    @property
    def default_attr(self) -> dict[str, None]:
        """Return attributes reset by the model cleanup helper."""
        return {"_root_items": None}

    def _has_curve_data(self, curve_id: str) -> bool:
        """Return whether one curve currently has authored keys.

        Args:
            curve_id: Curve id to inspect.

        Returns:
            ``True`` when the grouped-key payload converts to a curve with keys.
        """
        if not self._curve_model:
            return False
        curve = payload_to_curve(curve_id, self._curve_model.get_payload(curve_id))
        return bool(curve and curve.keys)

    def _build_from_layout(
        self,
        node: dict,
        inherited_color: int,
        parent: _CurveTreeItem | None,
    ) -> None:
        """Build hierarchy items with inherited colors and explicit leaf styles."""
        color = node.get("display_color", inherited_color)

        for child_id, child in node.get("children", {}).items():
            child_color = child.get("display_color", color)
            group = _CurveTreeItem(
                item_id=child_id,
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
                item_id=cid,
                display_name=curve.get("display_name", cid),
                curve_id=cid,
                color=curve.get("display_color", color),
                has_data=self._has_curve_data(cid),
                parent=parent,
                label_style_name=curve.get("label_style_name", ""),
            )
            if parent is None:
                self._root_items.append(leaf)

    def refresh_has_data(self) -> None:
        """Re-check has_data on all leaf items and signal a redraw."""
        for item in self._iter_all(self._root_items):
            if item.is_curve:
                item.has_data = self._has_curve_data(item.curve_id)
        self._item_changed(None)

    @property
    def curve_items(self) -> list[_CurveTreeItem]:
        """Return every curve leaf from the explicit model roots."""
        return [item for item in self._iter_all(self._root_items) if item.is_curve]

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
    """Render each tree row with its colored label and create/delete control."""

    def __init__(
        self,
        on_create_curve: Callable[[str], None] | None = None,
        on_delete_curve: Callable[[str], None] | None = None,
    ):
        super().__init__()
        self._on_create_curve = on_create_curve
        self._on_delete_curve = on_delete_curve
        self._channel_labels: dict[_CurveTreeItem, ui.Label] = {}

    @property
    def default_attr(self) -> dict[str, None]:
        return {
            **super().default_attr,
            "_on_create_curve": None,
            "_on_delete_curve": None,
        }

    @TreeDelegateBase.selection.setter
    def selection(self, value: Iterable[_CurveTreeItem]) -> None:
        """Update channel label states with native tree selection."""
        self._selection = list(value)
        selected_items = set(self.selection)
        for item, label in self._channel_labels.items():
            label.selected = item in selected_items

    def destroy(self) -> None:
        """Release channel labels and delegate callbacks."""
        self._channel_labels.clear()
        super().destroy()

    def build_branch(self, model, item, column_id, level, expanded):
        if column_id == 0:
            with ui.HStack(width=ui.Pixel(_INDENT_PX * (level + 2)), height=self.DEFAULT_IMAGE_ICON_SIZE):
                ui.Spacer()
                if item is not None and item.has_children:
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
        """Build a colored tree label with its current selection and authored state."""
        with ui.HStack(name="CurveEditorTreeRow", height=_ROW_HEIGHT, spacing=4):
            faint = item.is_curve and not item.has_data
            label_color = _half_alpha(item.color) if faint else item.color
            label_name = (item.label_style_name or "CurveEditorChannel") if item.is_curve else "CurveEditorGroup"
            label = ui.Label(
                item.display_name,
                name=label_name,
                identifier=f"CurveTree{'Channel' if item.is_curve else 'Group'}::{item.item_id}",
                tooltip=item.tooltip,
                selected=item.is_curve and item in self.selection,
                style={f"Label::{label_name}": {"font_size": 13, "color": label_color}},
            )

            if item.is_curve:
                self._channel_labels[item] = label
                ui.Spacer()
                icon_name = "CurveEditorTreeDelete" if item.has_data else "CurveEditorTreeAdd"
                tip = "Delete curve data" if item.has_data else "Create default curve"
                fn = self._on_delete_curve if item.has_data else self._on_create_curve
                with ui.VStack(width=0):
                    ui.Spacer()
                    img = ui.Image(
                        "",
                        name=icon_name,
                        identifier=f"{icon_name}::{item.curve_id}",
                        width=_ICON_SIZE,
                        height=_ICON_SIZE,
                        tooltip=tip,
                    )
                    img.set_mouse_pressed_fn(
                        lambda x, y, b, m, cid=item.curve_id, cb=fn: cb(cid) if cb else None,
                    )
                    ui.Spacer()


# ---------------------------------------------------------------------------
# Public panel
# ---------------------------------------------------------------------------


class CurveTreePanel:
    """Hierarchical curve panel using ScrollingTreeWidget with alternating rows.

    Args:
        layout: CurveEditorLayout dict describing the hierarchy.
        curve_model: GroupedKeysModel to check authored state and create/delete curves.
        on_curves_selected: Called with the selected curve ids when row selection changes.
        on_create_curve: Called with curve_id when user clicks the add icon.
        on_delete_curve: Called with curve_id when user clicks the delete icon.
    """

    def __init__(
        self,
        layout: CurveEditorLayout,
        curve_model: GroupedKeysModel | None = None,
        on_curves_selected: Callable[[set[str]], None] | None = None,
        on_create_curve: Callable[[str], None] | None = None,
        on_delete_curve: Callable[[str], None] | None = None,
    ) -> None:
        """Create a hierarchical curve tree panel.

        Args:
            layout: Curve editor hierarchy and curve display metadata.
            curve_model: Grouped-key model used to show authored state.
            on_curves_selected: Optional callback when selected curve rows change.
            on_create_curve: Optional callback when the add icon is clicked.
            on_delete_curve: Optional callback when the delete icon is clicked.
        """
        self._model = CurveTreeModel(layout, curve_model)
        self._delegate = CurveTreeDelegate(on_create_curve, on_delete_curve)
        self._on_curves_selected = on_curves_selected
        self._curve_items = self._model.curve_items
        self._tree = ScrollingTreeWidget(
            self._model,
            self._delegate,
            alternating_rows=True,
            row_height=_ROW_HEIGHT,
            header_visible=False,
            root_visible=False,
            identifier="CurveTreeChannels",
        )
        self._tree.set_expanded(None, True, True)
        self._selection_sub = self._tree.subscribe_selection_changed(self._on_tree_selection_changed)
        self._on_tree_selection_changed(self._curve_items)
        self._initial_selection_task = ensure_future(self._initialize_selection())

    async def _initialize_selection(self) -> None:
        """Select the initial channels after the native tree initializes its item cache."""
        await get_app().next_update_async()
        self._tree.selection = self._curve_items

    def _on_tree_selection_changed(self, items: list[_CurveTreeItem]) -> None:
        """Normalize native group selection to curve leaves and publish their ids."""
        selected_curves = [item for item in items if item.is_curve]
        if len(selected_curves) != len(items):
            self._tree.selection = selected_curves
        if self._on_curves_selected:
            self._on_curves_selected({item.curve_id for item in selected_curves if item.curve_id is not None})

    def refresh(self) -> None:
        """Re-check curve data state and redraw icons."""
        self._model.refresh_has_data()
        self._tree.dirty_widgets()

    def destroy(self) -> None:
        """Release the selection task, callbacks, and tree references."""
        if self._initial_selection_task:
            self._initial_selection_task.cancel()
            self._initial_selection_task = None
        self._selection_sub = None
        self._on_curves_selected = None
        self._curve_items.clear()
        if self._tree:
            self._tree.destroy()
            self._tree = None
        if self._delegate:
            self._delegate.destroy()
            self._delegate = None

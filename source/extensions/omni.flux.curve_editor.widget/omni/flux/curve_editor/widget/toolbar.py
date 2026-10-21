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

CurveEditorToolbar - Icon-based toolbar for curve editing actions.

Layout:
    KEYFRAME            LEFT TANGENT - AUTO           RIGHT TANGENT - LINEAR         FRAME
    [+] [-] [lock]     [lin][stp][flt][aut][smo][cst]  [lin][stp][flt][aut][smo][cst]  [time][value]

Labels on top, buttons below. Active tangent shows white background.

Button names select icon URLs, hover colors, and active backgrounds from the
name-based stylesheet. The tangent toggle exposes its lock state through
``checked`` and switches between the linked and broken icon names.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from math import isfinite
from typing import TYPE_CHECKING

from omni import ui

if TYPE_CHECKING:
    from omni.flux.fcurve.widget import FCurve, FCurveKey, FCurveWidget

from omni.flux.fcurve.widget import KeyReference, TangentType, evaluate_curve

__all__ = ["CurveEditorToolbar"]

_BTN_SIZE = ui.Pixel(32)
_SECTION_SPACING = ui.Pixel(16)
_BTN_SPACING = ui.Pixel(2)
_LABEL_HEIGHT = ui.Pixel(18)
_LABEL_BTN_GAP = ui.Pixel(2)
_TOOLBAR_BOTTOM_MARGIN = ui.Pixel(4)
_TOOLBAR_PADDING = ui.Pixel(8)

# (TangentType, button ID suffix, tooltip label)
_TANGENT_BUTTONS: tuple[tuple[TangentType, str, str], ...] = (
    (TangentType.LINEAR, "TangentLinear", "Linear"),
    (TangentType.STEP, "TangentStep", "Step"),
    (TangentType.FLAT, "TangentFlat", "Flat"),
    (TangentType.AUTO, "TangentAuto", "Auto"),
    (TangentType.SMOOTH, "TangentSmooth", "Smooth"),
    (TangentType.CUSTOM, "TangentCustom", "Custom"),
)

_TANGENT_BTN_IDS: dict[TangentType, str] = {tt: bid for tt, bid, _ in _TANGENT_BUTTONS}


def _btn_name(btn_id: str, active: bool = False) -> str:
    """Build the widget name for a toolbar button."""
    return f"CurveEditorBtn{btn_id}Active" if active else f"CurveEditorBtn{btn_id}"


def _selected_editable_keys(fcurve_widget: FCurveWidget) -> list[tuple[FCurve, FCurveKey]]:
    """Resolve editable selected references to their curves and keys."""
    curves = fcurve_widget.curves
    return [
        (curves[reference.curve_id], curves[reference.curve_id].keys[reference.key_index])
        for reference in fcurve_widget.editable_selected_keys
    ]


def _delete_selected_keys(
    fcurve_widget: FCurveWidget, edit_context_factory: Callable[[], AbstractContextManager]
) -> None:
    """Delete eligible selected keys in one action after finishing any active insertion."""
    if not any(len(curve.keys) > 1 for curve, _ in _selected_editable_keys(fcurve_widget)):
        return
    # Keep the held insertion's undo entry separate from this deletion.
    fcurve_widget.update_insertion(None)
    with edit_context_factory():
        fcurve_widget.delete_selected_keys()


class CurveEditorToolbar:
    """
    Icon-based toolbar for curve editor actions.

    Build in constructor (omni.ui style) -- instantiate within a UI context.
    Visual appearance cascades from the parent's name-based style via
    per-button names (``CurveEditorBtn{Id}``).

    Args:
        fcurve_widget: The FCurveWidget to control.
        edit_context_factory: Create a context grouping one modifying toolbar action.
        on_frame_time: Optional action to fit the visible time range.
        on_frame_value: Optional action to fit the visible value range.
    """

    def __init__(
        self,
        fcurve_widget: FCurveWidget,
        edit_context_factory: Callable[[], AbstractContextManager] = nullcontext,
        *,
        on_frame_time: Callable[[], None] | None = None,
        on_frame_value: Callable[[], None] | None = None,
    ):
        """Build the toolbar with optional caller-owned edit grouping and framing actions."""
        self._fcurve_widget = fcurve_widget
        self._edit_context_factory = edit_context_factory

        self._add_key_btn: ui.Button | None = None
        self._delete_key_btn: ui.Button | None = None
        self._link_tangents_btn: ui.Button | None = None

        self._left_tangent_btns: dict[TangentType, ui.Button] = {}
        self._right_tangent_btns: dict[TangentType, ui.Button] = {}

        self._left_tangent_label: ui.Label | None = None
        self._right_tangent_label: ui.Label | None = None

        self._tangents_broken: bool | None = None
        self._has_selection = False
        self._current_in_tangent: TangentType | None = None
        self._current_out_tangent: TangentType | None = None

        self._build_ui(on_frame_time, on_frame_value)
        self.update_selection_state(False)

    def _build_ui(self, on_frame_time: Callable[[], None] | None, on_frame_value: Callable[[], None] | None) -> None:
        """Build editing controls and any supplied axis framing actions."""
        self._frame = ui.Frame()
        with self._frame:
            with ui.HStack(spacing=0):
                ui.Spacer(width=_TOOLBAR_PADDING, height=0)
                with ui.HStack(name="CurveEditorToolbar", spacing=_SECTION_SPACING):
                    self._build_keyframe_section()

                    self._build_separator()

                    self._build_tangent_section(is_left=True)

                    self._build_separator()

                    self._build_tangent_section(is_left=False)

                    if on_frame_time is not None or on_frame_value is not None:
                        self._build_separator()

                        with ui.VStack(width=0, spacing=_LABEL_BTN_GAP):
                            ui.Label("FRAME", name="CurveEditorToolbarLabel", height=_LABEL_HEIGHT)
                            with ui.HStack(spacing=_BTN_SPACING):
                                for button_id, callback, tooltip in (
                                    ("FrameTime", on_frame_time, "Frame Time"),
                                    ("FrameValue", on_frame_value, "Frame Value"),
                                ):
                                    if callback is not None:
                                        ui.Button(
                                            "",
                                            name=_btn_name(button_id),
                                            identifier=f"CurveEditorBtn{button_id}",
                                            width=_BTN_SIZE,
                                            height=_BTN_SIZE,
                                            clicked_fn=callback,
                                            tooltip=tooltip,
                                        )
                ui.Spacer(width=_TOOLBAR_PADDING, height=0)

    # ─────────────────────────────────────────────────────────────────────────
    # Build Sections
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_separator() -> None:
        """Build a toolbar section separator with its existing spacing."""
        with ui.HStack(spacing=0):
            ui.Spacer()
            with ui.VStack(width=0, spacing=_LABEL_BTN_GAP):
                ui.Spacer(height=_LABEL_HEIGHT)
                ui.Rectangle(name="CurveEditorToolbarSep", width=ui.Pixel(1))
                ui.Spacer(height=_TOOLBAR_BOTTOM_MARGIN)
            ui.Spacer()

    def _build_keyframe_section(self) -> None:
        """Build keyframe actions and the tangent lock toggle."""
        with ui.VStack(width=0, spacing=_LABEL_BTN_GAP):
            ui.Label("KEYFRAME", name="CurveEditorToolbarLabel", height=_LABEL_HEIGHT)

            with ui.HStack(spacing=_BTN_SPACING):
                self._add_key_btn = ui.Button(
                    "",
                    name=_btn_name("AddKey"),
                    identifier="CurveEditorBtnAddKey",
                    width=_BTN_SIZE,
                    height=_BTN_SIZE,
                    mouse_pressed_fn=lambda x, y, b, m: self._on_add_key(),
                    tooltip="Add Keyframe (to right of selection)",
                )

                self._delete_key_btn = ui.Button(
                    "",
                    name=_btn_name("DeleteKey"),
                    identifier="CurveEditorBtnDeleteKey",
                    width=_BTN_SIZE,
                    height=_BTN_SIZE,
                    mouse_pressed_fn=lambda x, y, b, m: self._on_delete_key(),
                    tooltip="Delete Keyframe",
                )

                self._link_tangents_btn = ui.Button(
                    "",
                    name=_btn_name("Broken"),
                    identifier="CurveEditorBtnLink",
                    width=_BTN_SIZE,
                    height=_BTN_SIZE,
                    clicked_fn=self._on_toggle_link_mode,
                    tooltip="Tangents unlocked — click to lock.",
                )

    def _build_tangent_section(self, is_left: bool) -> None:
        """Build the tangent type actions for one side of the selected keys."""
        with ui.VStack(width=0, spacing=_LABEL_BTN_GAP):
            label_text = "LEFT TANGENT" if is_left else "RIGHT TANGENT"
            label = ui.Label(label_text, name="CurveEditorToolbarLabel", height=_LABEL_HEIGHT)
            if is_left:
                self._left_tangent_label = label
            else:
                self._right_tangent_label = label

            with ui.HStack(spacing=_BTN_SPACING):
                btn_dict = self._left_tangent_btns if is_left else self._right_tangent_btns

                for tangent_type, btn_id, tooltip_name in _TANGENT_BUTTONS:
                    btn = ui.Button(
                        "",
                        name=_btn_name(btn_id),
                        identifier=f"CurveEditorBtn{'Left' if is_left else 'Right'}{btn_id}",
                        width=_BTN_SIZE,
                        height=_BTN_SIZE,
                        mouse_pressed_fn=lambda x, y, b, m, tt=tangent_type, left=is_left: self._on_tangent_clicked(
                            tt, left
                        ),
                        tooltip=f"{tooltip_name} Tangent",
                    )
                    btn_dict[tangent_type] = btn

    # ─────────────────────────────────────────────────────────────────────────
    # Button Callbacks
    # ─────────────────────────────────────────────────────────────────────────

    def _prepare_add_keys(self) -> tuple[list[tuple[str, float, float, int | None]], str]:
        """Prepare shared-time insertions or return the reason Add is unavailable.

        Returns:
            Curve ID, time, value, and existing key index for each target, plus an
            unavailable reason. A missing index means a new key must be inserted.
        """
        curves = {
            curve_id: curve
            for curve_id, curve in self._fcurve_widget.curves.items()
            if curve.visible and not curve.locked and curve.keys
        }
        if not curves:
            return [], "Select an unlocked channel with curve data. Use Create for empty channels."

        anchor_curve = next(iter(curves.values()))
        anchor_index = 0
        for reference in self._fcurve_widget.editable_selected_keys:
            anchor_curve = curves[reference.curve_id]
            anchor_index = reference.key_index
            break

        anchor = anchor_curve.keys[anchor_index]
        if anchor_index + 1 < len(anchor_curve.keys):
            new_time = (anchor.time + anchor_curve.keys[anchor_index + 1].time) / 2
        else:
            new_time = anchor.time + 0.1
        if not isfinite(new_time):
            return [], "The shared key time must be finite."

        prepared = []
        for curve_id, curve in curves.items():
            bounds = self._fcurve_widget.bounds_for(curve_id)
            if not bounds.time_min <= new_time <= bounds.time_max:
                return [], "The shared key time is outside a selected curve's bounds."
            existing_index = next((index for index, key in enumerate(curve.keys) if key.time == new_time), None)
            if existing_index is None and any(
                abs(key.time - new_time) < self._fcurve_widget.keyframe_clamp_threshold for key in curve.keys
            ):
                return [], "The shared key time is too close to an existing key on a selected curve."
            new_value = (
                curve.keys[existing_index].value if existing_index is not None else evaluate_curve(curve, new_time)
            )
            if not isfinite(new_value) or not bounds.value_min <= new_value <= bounds.value_max:
                return [], "The sampled value is outside a selected curve's bounds or is not finite."
            prepared.append((curve_id, new_time, new_value, existing_index))
        return prepared, ""

    def _on_add_key(self) -> None:
        """Add or reuse one key on every eligible displayed curve at a shared time."""
        prepared, reason = self._prepare_add_keys()
        if reason:
            self.update_selection_state(
                self._has_selection,
                self._current_in_tangent,
                self._current_out_tangent,
                tangents_broken=self._tangents_broken,
            )
            return

        if any(index is None for _, _, _, index in prepared):
            inserted_keys = {}
            # Insertion changes indices, so old references must not survive notifications.
            self._fcurve_widget.clear_selection()
            with self._edit_context_factory():
                for curve_id, time, value, existing_index in prepared:
                    if existing_index is None:
                        inserted_keys[curve_id] = self._fcurve_widget.add_key(curve_id, time, value)
            curves = self._fcurve_widget.curves
            selected = [
                KeyReference(
                    curve_id,
                    curves[curve_id].keys.index(inserted_keys[curve_id]) if existing_index is None else existing_index,
                )
                for curve_id, _, _, existing_index in prepared
            ]
        else:
            selected = [KeyReference(curve_id, index) for curve_id, _, _, index in prepared]
        self._fcurve_widget.select_keys(selected)

    def _on_delete_key(self) -> None:
        """Delete selected editable keys in one action, preserving each curve's last key."""
        _delete_selected_keys(self._fcurve_widget, self._edit_context_factory)

    def _on_toggle_link_mode(self) -> None:
        """Toggle the current editable keys' tangent lock in one modifying action."""
        selected_keys = _selected_editable_keys(self._fcurve_widget)
        if not selected_keys:
            self._has_selection = False
            self._tangents_broken = None
            self._update_link_button()
            return

        broken = all(not key.tangent_broken for _, key in selected_keys)
        with self._edit_context_factory():
            self._fcurve_widget.set_selected_keys_tangent_broken(broken)
        selected_keys = _selected_editable_keys(self._fcurve_widget)
        broken_states = {key.tangent_broken for _, key in selected_keys}
        self._has_selection = bool(selected_keys)
        self._tangents_broken = broken_states.pop() if len(broken_states) == 1 else None
        self._update_link_button()

    def _on_tangent_clicked(self, tangent_type: TangentType, is_left: bool) -> None:
        """Apply the clicked tangent type in one action, honoring each selected key's link state."""
        if not any(
            ((is_left or not key.tangent_broken) and key.in_tangent_type != tangent_type)
            or ((not is_left or not key.tangent_broken) and key.out_tangent_type != tangent_type)
            for _, key in _selected_editable_keys(self._fcurve_widget)
        ):
            return
        with self._edit_context_factory():
            self._fcurve_widget.set_selected_keys_tangent_type(
                tangent_type, in_tangent=is_left, out_tangent=not is_left
            )

    # ─────────────────────────────────────────────────────────────────────────
    # State Updates
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _set_button_active(btn: ui.Button, btn_id: str, active: bool) -> None:
        """Toggle a button between active and default by swapping its name."""
        btn.name = _btn_name(btn_id, active=active)

    def _update_link_button(self) -> None:
        """Show the selected keys' tangent lock state and the next toggle action."""
        if self._link_tangents_btn:
            linked = self._has_selection and self._tangents_broken is False
            self._link_tangents_btn.checked = linked
            self._link_tangents_btn.enabled = self._has_selection
            self._set_button_active(self._link_tangents_btn, "Link" if linked else "Broken", linked)
            if not self._has_selection:
                self._link_tangents_btn.tooltip = "Select editable keys to lock or unlock tangents."
            elif self._tangents_broken is None:
                self._link_tangents_btn.tooltip = "Mixed tangent states — click to lock all selected tangents."
            elif linked:
                self._link_tangents_btn.tooltip = "Tangents locked — click to unlock."
            else:
                self._link_tangents_btn.tooltip = "Tangents unlocked — click to lock."

    def update_selection_state(
        self,
        has_selection: bool,
        in_tangent_type: TangentType | None = None,
        out_tangent_type: TangentType | None = None,
        tangents_broken: bool | None = None,
    ) -> None:
        """Refresh operation availability and tangent state for the editable selection.

        Args:
            has_selection: Whether any selected keys are editable and displayed.
            in_tangent_type: Shared incoming tangent type, or None for mixed types.
            out_tangent_type: Shared outgoing tangent type, or None for mixed types.
            tangents_broken: Shared broken state, or None for mixed or unknown state.
        """
        self._has_selection = has_selection
        self._current_in_tangent = in_tangent_type
        self._current_out_tangent = out_tangent_type

        self._tangents_broken = tangents_broken

        if self._delete_key_btn:
            self._delete_key_btn.enabled = any(
                len(curve.keys) > 1 for curve, _ in _selected_editable_keys(self._fcurve_widget)
            )

        if self._add_key_btn:
            prepared, reason = self._prepare_add_keys()
            self._add_key_btn.enabled = bool(prepared)
            self._add_key_btn.tooltip = reason or "Add a key to selected channels at one shared time."

        self._update_tangent_buttons()
        self._update_link_button()

    def _update_tangent_buttons(self) -> None:
        for ttype, btn in self._left_tangent_btns.items():
            self._set_button_active(btn, _TANGENT_BTN_IDS[ttype], ttype == self._current_in_tangent)

        for ttype, btn in self._right_tangent_btns.items():
            self._set_button_active(btn, _TANGENT_BTN_IDS[ttype], ttype == self._current_out_tangent)

        if self._left_tangent_label:
            type_name = self._current_in_tangent.name if self._current_in_tangent is not None else "MIXED"
            self._left_tangent_label.text = f"LEFT TANGENT - {type_name}"

        if self._right_tangent_label:
            type_name = self._current_out_tangent.name if self._current_out_tangent is not None else "MIXED"
            self._right_tangent_label.text = f"RIGHT TANGENT - {type_name}"

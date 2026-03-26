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
    KEYFRAME                    LEFT TANGENT - AUTO              RIGHT TANGENT - LINEAR
    [+] [-] [link] [broken]     [lin][stp][flt][aut][smo][cst]   [lin][stp][flt][aut][smo][cst]

Labels on top, buttons below. Active tangent shows white background.

Each button has a unique widget name (``CurveEditorBtn{Id}``) so its icon URL,
hover color, and active state are driven entirely by the name-based stylesheet
— no inline ``style=`` overrides needed.  Toggling active state is a pure
``btn.name`` swap between ``CurveEditorBtn{Id}`` and ``CurveEditorBtn{Id}Active``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from omni import ui

if TYPE_CHECKING:
    from omni.flux.fcurve.widget import FCurveWidget

from omni.flux.fcurve.widget import TangentType

__all__ = ["CurveEditorToolbar"]

_BTN_SIZE = 32
_SECTION_SPACING = 20
_BTN_SPACING = 2
_LABEL_HEIGHT = 18
_LABEL_BTN_GAP = 2
_TOOLBAR_BOTTOM_MARGIN = 4

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


class CurveEditorToolbar:
    """
    Icon-based toolbar for curve editor actions.

    Build in constructor (omni.ui style) -- instantiate within a UI context.
    Visual appearance cascades from the parent's name-based style via
    per-button names (``CurveEditorBtn{Id}``).

    Args:
        fcurve_widget: The FCurveWidget to control.
    """

    def __init__(self, fcurve_widget: FCurveWidget):
        self._fcurve_widget = fcurve_widget

        self._add_key_btn: ui.Button | None = None
        self._delete_key_btn: ui.Button | None = None
        self._link_tangents_btn: ui.Button | None = None
        self._broken_tangents_btn: ui.Button | None = None

        self._left_tangent_btns: dict[TangentType, ui.Button] = {}
        self._right_tangent_btns: dict[TangentType, ui.Button] = {}

        self._left_tangent_label: ui.Label | None = None
        self._right_tangent_label: ui.Label | None = None

        self._tangents_linked = True
        self._has_selection = False
        self._current_in_tangent: TangentType | None = None
        self._current_out_tangent: TangentType | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        self._frame = ui.Frame()
        with self._frame:
            with ui.HStack(name="CurveEditorToolbar", spacing=_SECTION_SPACING):
                self._build_keyframe_section()

                with ui.VStack(width=0, spacing=_LABEL_BTN_GAP):
                    ui.Spacer(height=ui.Pixel(_LABEL_HEIGHT))
                    ui.Rectangle(name="CurveEditorToolbarSep", width=ui.Pixel(1))
                    ui.Spacer(height=ui.Pixel(_TOOLBAR_BOTTOM_MARGIN))

                self._build_tangent_section(is_left=True)

                with ui.VStack(width=0, spacing=_LABEL_BTN_GAP):
                    ui.Spacer(height=ui.Pixel(_LABEL_HEIGHT))
                    ui.Rectangle(name="CurveEditorToolbarSep", width=ui.Pixel(1))
                    ui.Spacer(height=ui.Pixel(_TOOLBAR_BOTTOM_MARGIN))

                self._build_tangent_section(is_left=False)

                ui.Spacer()

    # ─────────────────────────────────────────────────────────────────────────
    # Build Sections
    # ─────────────────────────────────────────────────────────────────────────

    def _build_keyframe_section(self) -> None:
        with ui.VStack(width=0, spacing=_LABEL_BTN_GAP):
            ui.Label("KEYFRAME", name="CurveEditorToolbarLabel", height=ui.Pixel(_LABEL_HEIGHT))

            with ui.HStack(spacing=_BTN_SPACING):
                self._add_key_btn = ui.Button(
                    "",
                    name=_btn_name("AddKey"),
                    width=_BTN_SIZE,
                    height=_BTN_SIZE,
                    mouse_pressed_fn=lambda x, y, b, m: self._on_add_key(),
                    tooltip="Add Keyframe (to right of selection)",
                )

                self._delete_key_btn = ui.Button(
                    "",
                    name=_btn_name("DeleteKey"),
                    width=_BTN_SIZE,
                    height=_BTN_SIZE,
                    mouse_pressed_fn=lambda x, y, b, m: self._on_delete_key(),
                    tooltip="Delete Keyframe",
                )

                self._link_tangents_btn = ui.Button(
                    "",
                    name=_btn_name("Link"),
                    width=_BTN_SIZE,
                    height=_BTN_SIZE,
                    mouse_pressed_fn=lambda x, y, b, m: self._on_set_link_mode(True),
                    tooltip="Link Tangents (edit both sides together)",
                )

                self._broken_tangents_btn = ui.Button(
                    "",
                    name=_btn_name("Broken"),
                    width=_BTN_SIZE,
                    height=_BTN_SIZE,
                    mouse_pressed_fn=lambda x, y, b, m: self._on_set_link_mode(False),
                    tooltip="Break Tangents (edit sides independently)",
                )

    def _build_tangent_section(self, is_left: bool) -> None:
        with ui.VStack(width=0, spacing=_LABEL_BTN_GAP):
            label_text = "LEFT TANGENT" if is_left else "RIGHT TANGENT"
            label = ui.Label(label_text, name="CurveEditorToolbarLabel", height=ui.Pixel(_LABEL_HEIGHT))
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

    def _on_add_key(self) -> None:
        if not self._fcurve_widget:
            return

        curves = self._fcurve_widget.curves
        if not curves:
            return

        selected = self._fcurve_widget.selected_keys

        target_curve_id: str | None = None
        target_curve = None

        if selected:
            target_curve_id = selected[0].curve_id
            target_curve = curves.get(target_curve_id)
        else:
            for curve_id, curve in curves.items():
                target_curve_id = curve_id
                target_curve = curve
                break

        if not target_curve or not target_curve_id or len(target_curve.keys) == 0:
            return

        new_time = 0.5
        new_value = 0.5

        if selected:
            key_ref = selected[0]
            if key_ref.key_index < len(target_curve.keys):
                ref_key = target_curve.keys[key_ref.key_index]
                if key_ref.key_index + 1 < len(target_curve.keys):
                    next_key = target_curve.keys[key_ref.key_index + 1]
                    new_time = (ref_key.time + next_key.time) / 2
                    new_value = (ref_key.value + next_key.value) / 2
                else:
                    new_time = ref_key.time + 0.1
                    new_value = ref_key.value
        elif len(target_curve.keys) >= 2:
            key0 = target_curve.keys[0]
            key1 = target_curve.keys[1]
            new_time = (key0.time + key1.time) / 2
            new_value = (key0.value + key1.value) / 2
        elif len(target_curve.keys) == 1:
            key0 = target_curve.keys[0]
            new_time = key0.time + 0.1
            new_value = key0.value

        self._fcurve_widget.add_key(target_curve_id, new_time, new_value)

    def _on_delete_key(self) -> None:
        if self._fcurve_widget and self._has_selection:
            self._fcurve_widget.delete_selected_keys()

    def _on_set_link_mode(self, linked: bool) -> None:
        self._tangents_linked = linked
        self._update_link_buttons()

        if self._fcurve_widget and self._has_selection:
            self._fcurve_widget.set_selected_keys_tangent_broken(not linked)

    def _on_tangent_clicked(self, tangent_type: TangentType, is_left: bool) -> None:
        if not self._fcurve_widget or not self._has_selection:
            return

        if self._tangents_linked:
            self._fcurve_widget.set_selected_keys_tangent_type(tangent_type, in_tangent=True, out_tangent=True)
        else:
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

    def _update_link_buttons(self) -> None:
        link_active = self._has_selection and self._tangents_linked
        broken_active = self._has_selection and not self._tangents_linked

        if self._link_tangents_btn:
            self._set_button_active(self._link_tangents_btn, "Link", link_active)
        if self._broken_tangents_btn:
            self._set_button_active(self._broken_tangents_btn, "Broken", broken_active)

    def update_selection_state(
        self,
        has_selection: bool,
        in_tangent_type: TangentType | None = None,
        out_tangent_type: TangentType | None = None,
        tangents_broken: bool | None = None,
    ) -> None:
        self._has_selection = has_selection
        self._current_in_tangent = in_tangent_type
        self._current_out_tangent = out_tangent_type

        if tangents_broken is not None:
            self._tangents_linked = not tangents_broken

        if self._delete_key_btn:
            self._delete_key_btn.enabled = has_selection

        self._update_tangent_buttons()
        self._update_link_buttons()

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

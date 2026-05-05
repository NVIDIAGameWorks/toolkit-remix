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

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import carb.settings
import omni.ui as ui
from omni.flux.utils.common.prims import get_proto_from_prim
from omni.flux.utils.widget.resources import get_fonts
from pxr import Sdf, Usd

__all__ = ["GLOBAL_SHOW_NICKNAMES_SETTING", "UsdPrimNameField"]


def _make_read_only_style(font_name: str) -> dict:
    """Build a read-only label style, resolving the font lazily to avoid import-time font directory access."""
    return {
        "background_color": 0x00000000,
        "font": get_fonts(font_name),
        "font_size": 16,
        ":hovered": {
            "color": 0xFFFFFFFF,
        },
    }


FIELD_EDITABLE_STYLE = {
    "background_color": 0xFF303030,
    "border_width": 1,
    "border_color": 0x66FFC700,
}

NICKNAME_INDICATOR_COLOR = 0xFF3CA0D2
NICKNAME_INDICATOR_COLOR_INACTIVE = 0xFF5A5A5A

GLOBAL_SHOW_NICKNAMES_SETTING = "/UsdPrimNameField/DisplayNickNames"


def _get_nickname_string_field_style(nickname: bool = False) -> dict:
    if nickname:
        return _make_read_only_style("NVIDIASans_A_It")

    return _make_read_only_style("NVIDIASans_A_Rg")


class UsdPrimNameField:
    """
    A widget that displays text as a Label and supports inline editing via StringField.

    Features:
    - Displays text as a ui.Label with nickname-aware styling (italic for nicknames)
    - Shows a visual indicator (circle) when a nickname is present
    - Supports double-click to edit (switches to ui.StringField)
    - Uses callable functions for display_text and tooltip to allow fresh queries from prim

    Args:
        prim: The USD prim to display the name for (required)
        identifier: The identifier for the widget
        display_text_fn: Callable that returns display text from prim. Defaults to prim.GetName()
        tooltip_fn: Callable that returns tooltip from prim. Defaults to str(prim.GetPath())
        editable_check_fn: A function that returns True if the prim is editable, False otherwise. Defaults to None.
        field_id: Optional id for this field; when set, force_prim_name state persists across widget rebuilds.
            Defaults to None.
        show_display_name_ancestor: Whether to show the display name ancestor before the name. Defaults to False.
    """

    NICKNAME_ATTR = "nickname"
    NAME = "PropertiesPaneSectionTreeFieldItem"
    _force_prim_name_states: dict[str, bool] = {}
    _editing_states: dict[str, bool] = {}

    @classmethod
    def clear_force_prim_name_states(cls) -> None:
        cls._force_prim_name_states.clear()

    @classmethod
    def clear_editing_states(cls) -> None:
        cls._editing_states.clear()

    def __init__(
        self,
        prim: Usd.Prim,
        identifier: str | None = None,
        display_text_fn: Callable[[Usd.Prim], str] | None = None,
        tooltip_fn: Callable[[Usd.Prim], str] | None = None,
        editable_check_fn: Callable[[Usd.Prim], bool] | None = None,
        field_id: str | None = None,
        show_display_name_ancestor: bool = False,
    ):
        # Store prim reference and stage (for save_nickname root-layer authoring)
        self._prim = prim
        if prim.IsValid():
            self._stage = prim.GetStage()
        else:
            self._stage = None

        # Store callable functions for fresh queries
        self._display_text_fn = display_text_fn if display_text_fn else lambda p: p.GetName()
        self._tooltip_fn = tooltip_fn if tooltip_fn else lambda p: str(p.GetPath())

        self._editable_check_fn = editable_check_fn if editable_check_fn else lambda p: True
        self._show_display_name_ancestor = show_display_name_ancestor

        self._container: ui.Frame | None = None
        self._label: ui.Label | None = None
        self._field: ui.StringField | None = None
        self._circle: ui.Circle | None = None

        # Get nickname from prim attribute
        self._nickname = None
        attr = get_proto_from_prim(self._prim).GetAttribute(self.NICKNAME_ATTR)
        if attr.IsValid() and attr.HasValue():
            self._nickname = str(attr.Get())

        self._settings = carb.settings.get_settings()
        self._settings.set_default_bool(GLOBAL_SHOW_NICKNAMES_SETTING, True)

        self._field_id = field_id
        self._show_nickname = self._settings.get_as_bool(GLOBAL_SHOW_NICKNAMES_SETTING)
        self._is_editing = (
            False if self._field_id is None else UsdPrimNameField._editing_states.get(self._field_id, False)
        )

        self._settings_global_sub = self._settings.subscribe_to_node_change_events(
            GLOBAL_SHOW_NICKNAMES_SETTING, self._on_global_toggle_changed
        )

        self._identifier = identifier if identifier else "nickname_field"
        if self._nickname:
            self._show_indicator = True
            self._indicator_active = self.show_nickname
        else:
            self._show_indicator = False
            self._indicator_active = False

        # Build the container
        self._build()

    def _get_display_text(self) -> str:
        """Get the appropriate display text based on show_nickname state.

        When not showing nickname, fetches fresh value from prim via the display_text_fn.
        """
        if self.show_nickname and self._nickname:
            return self._nickname
        return self.original_display_name

    def _get_display_name_ancestor(self) -> str | None:
        """Get the display name ancestor from the parent prim's path."""
        parent = self._prim.GetParent()
        if parent and parent.IsValid():
            return parent.GetPath().name
        return None

    def _on_global_toggle_changed(self, item: Any, event: carb.settings.ChangeEventType) -> None:
        if event != carb.settings.ChangeEventType.CHANGED:
            return

        UsdPrimNameField.clear_force_prim_name_states()
        UsdPrimNameField.clear_editing_states()

        new_value = self._settings.get_as_bool(GLOBAL_SHOW_NICKNAMES_SETTING)
        if new_value != self._show_nickname:
            self.show_nickname = new_value

    @property
    def prim_supports_nickname(self) -> bool:
        """Whether the prim supports nickname functionality."""
        return self._editable_check_fn(self._prim)

    @property
    def field_id(self) -> str | None:
        """The id for this field; when set, force_prim_name state persists across rebuilds."""
        return self._field_id

    @property
    def container(self) -> ui.Frame | None:
        """Get the container widget."""
        return self._container

    @property
    def field(self) -> ui.StringField | None:
        """The underlying StringField widget (only available in edit mode)."""
        return self._field

    @property
    def label(self) -> ui.Label | None:
        """The underlying Label widget (only available in display mode)."""
        return self._label

    @property
    def circle(self) -> ui.Circle | None:
        """The nickname indicator circle widget."""
        return self._circle

    @property
    def is_editing(self) -> bool:
        """Whether the widget is currently in edit mode."""
        return self._is_editing

    @property
    def text(self) -> str:
        """Get the current text value.

        When in edit mode, returns the field value.
        Otherwise, returns fresh display text (nickname or prim-derived).
        """
        if self._is_editing and self._field:
            return self._field.model.get_value_as_string()
        # Always get fresh display text
        return self._get_display_text()

    @property
    def show_nickname(self) -> bool:
        """Whether to show the nickname (if available) or the original display name."""
        if self.force_prim_name:
            return False
        return self._show_nickname

    @show_nickname.setter
    def show_nickname(self, value: bool):
        """Set whether to show the nickname (if available) or the original display name."""
        # NOTE: we shouldn't need this setter but removing it now requires
        # a good amount of refactoring of the build method that we shouldn't do at this time
        # show nick name should be able to drive all the indicator logic, and the carb setting callback  or the
        # force_prim_name should trigger the rebuilds

        self._show_nickname = value
        self._indicator_active = self.show_nickname and bool(self._nickname)
        if self._container and not self._is_editing:
            self._container.rebuild()
        self._update_indicator()

    @property
    def force_prim_name(self) -> bool:
        """True = always show raw prim name, False = show nickname if available."""
        if self._field_id:
            return UsdPrimNameField._force_prim_name_states.get(self._field_id, False)
        return False

    @force_prim_name.setter
    def force_prim_name(self, value: bool):
        if self._field_id:
            match value:
                case False:
                    UsdPrimNameField._force_prim_name_states.pop(self._field_id, None)  # cleanup
                case True:
                    UsdPrimNameField._force_prim_name_states[self._field_id] = True

        self._indicator_active = self.show_nickname and bool(self._nickname)
        if self._container and not self._is_editing:
            self._container.rebuild()
        self._update_indicator()

    @property
    def original_display_name(self) -> str:
        """Get fresh original display name from prim (non-nickname)."""
        return self._display_text_fn(self._prim)

    @property
    def nickname(self) -> str | None:
        """Get the nickname value if set."""
        return self._nickname

    @property
    def prim(self) -> Usd.Prim:
        """Get the USD prim associated with this field."""
        return self._prim

    @property
    def tooltip(self) -> str:
        """Get fresh tooltip value from prim."""
        return self._tooltip_fn(self._prim)

    def is_valid_nickname_edit(self, new_value: str) -> bool:
        """
        Validate if a new nickname value is valid for saving.

        Args:
            new_value: The new nickname value to validate

        Returns:
            True if the value is valid and different from display name, False otherwise
        """
        # Check for empty/whitespace
        if not new_value or not new_value.strip():
            return False

        # Check if same as display name (no change needed) - uses fresh query
        if new_value == self.original_display_name:
            return False

        return self._prim.IsValid()

    def save_nickname(self, new_value: str) -> bool:
        """
        Validate and save a new nickname value to the USD prim attribute.

        This method handles:
        - Validation (empty check, display name comparison, prim validity)
        - Getting/creating the nickname attribute
        - Setting the attribute value
        - Updating internal state (_nickname)

        Args:
            new_value: The new nickname value to save

        Returns:
            True if the nickname was saved successfully, False otherwise
        """
        if not self.is_valid_nickname_edit(new_value):
            return False
        if not self._stage:
            return False
        proto_prim = get_proto_from_prim(self._prim)
        root_layer = self._stage.GetRootLayer()

        # Author only on the root layer: CreateAttribute uses the current edit target,
        # so we must set it before GetAttribute/CreateAttribute to avoid creating
        # the attribute on e.g. the replacement layer (mod.usda).
        with Usd.EditContext(self._stage, root_layer):
            attr = proto_prim.GetAttribute(self.NICKNAME_ATTR)
            if not attr:
                attr = proto_prim.CreateAttribute(self.NICKNAME_ATTR, Sdf.ValueTypeNames.String)
            if not attr:
                return False
            attr.Set(new_value)

        # Update internal state
        self._nickname = new_value
        self._show_indicator = True
        self._indicator_active = self.show_nickname

        # Rebuild to reflect changes
        if self._container and not self._is_editing:
            self._container.rebuild()

        return True

    def _update_indicator(self) -> None:
        """Update the indicator circle color."""
        if self._circle:
            color = NICKNAME_INDICATOR_COLOR if self._indicator_active else NICKNAME_INDICATOR_COLOR_INACTIVE
            self._circle.style = {"background_color": color}

    def set_indicator_active(self, active: bool) -> None:
        """Set whether the indicator is active (blue) or inactive (gray)."""
        self._indicator_active = active
        self._update_indicator()

    def _build(self) -> None:
        """
        Build the container widget with a Label.

        Called automatically during initialization.
        """
        self._container = ui.Frame(build_fn=self._build_content)

    def _build_content(self) -> None:
        """Build the appropriate content based on current mode."""
        # If the prim is not editable, build a read-only label
        if not self._editable_check_fn(self._prim):
            self._build_label()
            return

        # If editing, we use the StringField, but for display, we use the Label
        # This allows for a more consistent placement of the indicator circle
        # relative to the label.
        if self._is_editing:
            self._build_field()
        else:
            self._build_label()

    def _build_ancestor_label(self) -> None:
        """Build the ancestor label if enabled."""
        if self._show_display_name_ancestor:
            ancestor_text = self._get_display_name_ancestor()
            if ancestor_text:
                ui.Label(ancestor_text, name="FadedLabel", width=0)
                ui.Label("/", name="FadedLabel", width=0)

    def _build_label(self) -> None:
        """Build the Label for display mode."""
        self._field = None
        with ui.HStack(width=0):
            self._build_ancestor_label()
            with ui.VStack(height=ui.Pixel(24), width=0):
                ui.Spacer(height=ui.Pixel(4))
                self._label = ui.Label(
                    self.text,
                    name=self.NAME,
                    identifier=self._identifier,
                    style=_get_nickname_string_field_style(bool(self._nickname)),
                    width=0,
                    tooltip=self.tooltip,
                )
                ui.Spacer()
            if not self._editable_check_fn(self._prim):
                return
            # Build indicator circle if needed
            if self._show_indicator and bool(self._nickname):
                ui.Spacer(width=ui.Pixel(2))
                self._build_indicator()
                ui.Spacer()

            # Set up double-click handler for editing
            self._label.set_mouse_double_clicked_fn(lambda x, y, b, m: self._on_double_click(b))

    def _build_field(self) -> None:
        """Build the StringField for edit mode."""
        self._label = None
        # Using a computed width to ensure the field is the same width as the label.
        # There are some instances where the field wasn't wide enough to be visible with ui.Fraction(1.0).
        with ui.HStack(width=(self._container.computed_width + 12.0)):
            self._build_ancestor_label()
            display_text = self.text
            self._field = ui.StringField(
                read_only=False,
                name=self.NAME,
                identifier=self._identifier,
                style=FIELD_EDITABLE_STYLE,
            )
            self._field.model.set_value(display_text)
            self._field.model.add_end_edit_fn(self._on_end_edit)
            self._field.focus_keyboard()

    def _build_indicator(self) -> None:
        """Build the nickname indicator circle."""
        color = NICKNAME_INDICATOR_COLOR if self._indicator_active else NICKNAME_INDICATOR_COLOR_INACTIVE
        with ui.VStack(height=ui.Pixel(24), width=ui.Pixel(12), spacing=4):
            ui.Spacer(height=ui.Pixel(6))
            self._circle = ui.Circle(
                radius=1, style={"background_color": color}, identifier="has_nickname_state_widget_image"
            )
            ui.Spacer(height=ui.Pixel(4))

    def _on_double_click(self, button: int) -> None:
        """Handle double-click to enter edit mode."""
        if button != 0:  # Only left-click
            return

        self.enter_edit_mode()

    def enter_edit_mode(self) -> None:
        """Programmatically enter edit mode."""
        if not self._container or self._is_editing:
            return

        self._is_editing = True
        if self._field_id:
            UsdPrimNameField._editing_states[self._field_id] = True
        self._container.rebuild()

    def _on_end_edit(self, model: ui.AbstractValueModel):
        """Handle edit completion."""
        # Guard against being called multiple times (e.g., from both Enter key and focus loss)
        if not self._is_editing:
            return

        if self._field_id:
            UsdPrimNameField._editing_states.pop(self._field_id, None)

        new_value = model.get_value_as_string()

        # Switch back to label mode
        self._is_editing = False

        # Save the nickname to the prim attribute (this rebuilds on success)
        saved = self.save_nickname(new_value)

        # Rebuild if save didn't (e.g., validation failed) to exit edit mode
        if not saved and self._container:
            self._container.rebuild()

    def __del__(self):
        """Clean up resources."""
        self._container = None
        self._label = None
        self._field = None
        self._circle = None
        if self._settings_global_sub is not None:
            self._settings_global_sub.destroy()
            self._settings_global_sub = None

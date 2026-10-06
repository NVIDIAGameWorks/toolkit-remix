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

__all__ = ("ColorField",)

from functools import partial

import omni.ui as ui
from omni.kit.undo import begin_group, end_group
from pxr import Gf

from ..base import AbstractField


class ColorValueModel(ui.AbstractValueModel):
    """
    Wrapper value model that allows for tweaking how the value is displayed as a string.
    """

    def __init__(self, parent: ui.AbstractValueModel, display_precision: int = 2):
        super().__init__()
        self._parent = parent
        self.display_precision = display_precision
        # Echo any value changes to ensure the widget updates
        self._sub = parent.subscribe_value_changed_fn(lambda _: self._value_changed())

    def __getattr__(self, attr):
        if attr in self.__dict__:
            return getattr(self, attr)
        return getattr(self._parent, attr)

    def get_value_as_string(self):
        return f"{self._parent.get_value_as_float():.{self.display_precision}f}"


class ColorField(AbstractField):
    """Delegate of the tree"""

    def __init__(self, display_precision: int = 2, style_name: str = "ColorsWidgetFieldRead"):
        super().__init__(style_name=style_name)

        self.display_precision = display_precision

        # The color widget is a bit unique as the provided item's model is not used directly within the widget. We
        # instead connect change events between the two models to ensure that updates properly flow both ways.
        self._color_widget_changed_sub = None
        self._color_widget_component_subscriptions = []
        self._value_model_value_changed_sub = None
        self._unsubscribe_property_edit_cancel = None
        self._value_model = None

        # Used to supress redundant change events.
        self._ignore_value_change_events = False
        # Set while the item value model pushes its value into the color widget so it is not echoed back as an edit.
        self._syncing_from_value_model = False
        # True while a live color picker session owns an open undo group (one undo step per picker session).
        self._undo_group_open = False

    def build_ui(self, item, *, register_cleanup=None) -> list[ui.Widget]:
        """Build the color field and connect its cleanup to the owning property row.

        Args:
            item: Property row whose value model stores the color vector.
            register_cleanup: Optional callback that registers field cleanup with the owning delegate.
        """
        if len(item.value_models) != 1:
            raise ValueError("Expected 1 value_model that holds the vector values")

        self.destroy()
        value_model = item.value_models[0]
        self._value_model = value_model
        vec = value_model.get_attributes_raw_value(0)
        if vec is None:
            vec = Gf.Vec3f(0, 0, 0)

        widgets = []

        with ui.HStack(height=ui.Pixel(24)):
            ui.Spacer(width=ui.Pixel(8))
            with ui.VStack():
                ui.Spacer(height=ui.Pixel(2))
                color_widget = ui.ColorWidget(*vec, name=self.style_name, enabled=not value_model.read_only)
                widgets.append(color_widget)
                ui.Spacer(height=ui.Pixel(2))

            ui.Spacer(width=ui.Pixel(4))

            for index, child in enumerate(color_widget.model.get_item_children()):
                child_model = color_widget.model.get_item_value_model(child)
                ui.Spacer(width=ui.Pixel(4))
                with ui.VStack():
                    ui.Spacer(height=ui.Pixel(2))
                    widgets.append(
                        ui.StringField(
                            model=ColorValueModel(child_model, display_precision=self.display_precision),
                            style_type_name_override=self.style_name,
                            read_only=True,
                        )
                    )
                    ui.Spacer(height=ui.Pixel(2))
                if index < len(vec) - 1:
                    ui.Spacer(width=ui.Pixel(4))
                    with ui.VStack(width=ui.Pixel(1)):
                        ui.Spacer(height=ui.Pixel(4))
                        ui.Rectangle(name="ColorsWidgetSeparator")
                        ui.Spacer(height=ui.Pixel(4))

            # Apply every component edit immediately so the viewport updates while the color picker is still open.
            self._color_widget_component_subscriptions = [
                color_widget.model.get_item_value_model(child).subscribe_value_changed_fn(
                    partial(self._color_widget_component_changed, type(vec), value_model, color_widget.model)
                )
                for child in color_widget.model.get_item_children()
            ]
            # Closing the picker commits the final value and closes the undo group opened by the live edits.
            self._color_widget_changed_sub = color_widget.model.subscribe_end_edit_fn(
                partial(self._color_widget_changed, type(vec), value_model)
            )

        self._value_model_value_changed_sub = value_model.subscribe_value_changed_fn(
            partial(self._value_model_changed, color_widget.model)
        )
        self._unsubscribe_property_edit_cancel = value_model.subscribe_property_edit_cancel_fn(self.destroy)
        if register_cleanup is not None:
            register_cleanup(self.destroy)

        return widgets

    def destroy(self) -> None:
        """Release field subscriptions and close any active picker undo group."""
        if self._unsubscribe_property_edit_cancel is not None:
            self._unsubscribe_property_edit_cancel()
            self._unsubscribe_property_edit_cancel = None
        self._color_widget_component_subscriptions.clear()
        self._color_widget_changed_sub = None
        self._value_model_value_changed_sub = None
        self._close_undo_group()
        self._value_model = None

    def _value_model_changed(self, color_model, value_model):
        """Synchronize the picker components with the backing property value."""
        if self._ignore_value_change_events:
            return
        vec = value_model.get_attributes_raw_value(0)
        if vec is None:
            vec = Gf.Vec3f(0, 0, 0)
        children = color_model.get_item_children()
        assert len(children) == len(vec), f"{vec} does not match expected length for ColorWidget"
        self._syncing_from_value_model = True
        try:
            for child, value in zip(children, vec):
                child_value_model = color_model.get_item_value_model(child)
                child_value_model.set_value(value)
        finally:
            self._syncing_from_value_model = False

    def _color_widget_component_changed(self, vec_type, value_model, model, _component_model):
        """Live-apply a color picker edit without waiting for the picker to close."""
        if self._syncing_from_value_model or value_model.read_only:
            return
        if not self._undo_group_open:
            if value_model.supports_batch_edit:
                value_model.begin_batch_edit(live=True)
            else:
                begin_group()
            self._undo_group_open = True
        self._apply_color(vec_type, value_model, model)

    def _color_widget_changed(self, vec_type, value_model, model, _):
        """Commit the final color when the picker closes and close the live-edit undo group."""
        try:
            self._apply_color(vec_type, value_model, model)
        finally:
            self._close_undo_group()

    def _close_undo_group(self) -> None:
        """Close the picker undo group at most once after dismissal or cancellation."""
        if self._undo_group_open:
            self._undo_group_open = False
            if self._value_model.supports_batch_edit:
                self._value_model.end_batch_edit()
            else:
                end_group(remove_if_empty=True)

    def _apply_color(self, vec_type, value_model, model):
        """Write the picker color to the backing value model without echoing the update.

        Args:
            vec_type: Vector constructor matching the backing color value.
            value_model: Destination property value model that receives the color.
            model: Source color widget item model that provides the component values.
        """
        new_value = vec_type(*[model.get_item_value_model(c).get_value_as_float() for c in model.get_item_children()])
        self._ignore_value_change_events = True
        try:
            value_model.set_value(new_value)
        finally:
            self._ignore_value_change_events = False
            if value_model.supports_batch_edit and not value_model.is_batch_editing:
                self._undo_group_open = False
                self._value_model_changed(model, value_model)

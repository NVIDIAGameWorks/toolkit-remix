"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = ["RemixBackdropDelegate", "clear_edit_triggers", "trigger_backdrop_rename"]

import weakref
from functools import partial
from collections.abc import Callable

import omni.ui as ui
from omni.kit.graph.delegate.modern import HEADER, HIGHLIGHT_THICKNESS, PORT_VISIBLE_MIN
from omni.kit.graph.delegate.modern.backdrop_delegate import BackdropDelegate, color_to_hex, darker_color, hex_to_color
from omni.kit.widget.graph.abstract_graph_node_delegate import GraphNodeDescription
from pxr import Sdf

# Registry of inline edit trigger callbacks, keyed by prim path.
# Uses weak references to UI widgets to allow garbage collection.
_edit_triggers: dict[Sdf.Path, tuple[weakref.ref, Callable]] = {}


def trigger_backdrop_rename(prim_path: Sdf.Path) -> bool:
    """Trigger inline rename for a backdrop at the given path. Returns True if successful."""
    if prim_path not in _edit_triggers:
        return False

    widget_ref, trigger_fn = _edit_triggers[prim_path]
    if widget_ref() is None:
        # Widget was garbage collected, clean up the stale entry
        del _edit_triggers[prim_path]
        return False

    trigger_fn()
    return True


def clear_edit_triggers():
    """Clear all edit triggers. Call on extension shutdown to prevent memory leaks."""
    _edit_triggers.clear()


class RemixBackdropDelegate(BackdropDelegate):
    """
    Custom BackdropDelegate that fixes the inline rename field styling.
    The original BackdropDelegate creates a StringField with no background,
    making it unreadable when overlapping the label.
    """

    def node_header(self, model, node_desc: GraphNodeDescription):
        """Override to add proper background styling to the rename StringField."""
        border_default = 0xFFD8B74B

        def set_color(model, node, item_model):
            sub_models = item_model.get_item_children()
            rgb = (
                item_model.get_item_value_model(sub_models[0]).as_float,
                item_model.get_item_value_model(sub_models[1]).as_float,
                item_model.get_item_value_model(sub_models[2]).as_float,
            )
            model[node].display_color = rgb
            model.selection = []
            model._item_changed(None)  # noqa: SLF001

        header = ui.VStack()
        with header:
            node = node_desc.node
            node_name = model[node].name
            node_category = str(model[node].type)

            display_color = model[node].display_color
            if display_color:
                style = {
                    f"Graph.Node.Category::{node_category}": {"background_color": color_to_hex(display_color)},
                    f"Graph.Node.Secondary::{node_category}": {"background_color": darker_color(display_color)},
                }
                field_bg = darker_color(display_color)
            else:
                style = {}
                field_bg = 0xFF303030

            ui.Spacer(height=HIGHLIGHT_THICKNESS)
            with ui.ZStack():
                self.build_tooltip([node_name, node_category])
                with ui.VStack():
                    with ui.ZStack(height=HEADER["sec_height"]):
                        ui.Rectangle(style=style, name=node_category, style_type_name_override="Graph.Node.Secondary")
                        with ui.VStack():
                            ui.Spacer()
                            with ui.HStack(height=14):
                                ui.Spacer(width=3)
                                color_widget = ui.ColorWidget(height=14, width=14)

                                sub_models = color_widget.model.get_item_children()
                                border_color = model[node].display_color or hex_to_color(border_default)

                                color_widget.model.get_item_value_model(sub_models[0]).as_float = border_color[0]
                                color_widget.model.get_item_value_model(sub_models[1]).as_float = border_color[1]
                                color_widget.model.get_item_value_model(sub_models[2]).as_float = border_color[2]
                                color_widget.model.add_end_edit_fn(lambda m, i: set_color(model, node, m))

                                with ui.ZStack():
                                    label = ui.Label(
                                        node_name,
                                        visible_min=PORT_VISIBLE_MIN,
                                        style_type_name_override="Graph.Node.Label",
                                        style={"margin_width": HEADER["margin_to_left"]},
                                    )

                                    # Styled rename field - key fix: add background color
                                    label_field = ui.StringField(
                                        style={
                                            "background_color": field_bg,
                                            "border_radius": 2,
                                            "padding": 2,
                                        }
                                    )
                                    label_field.visible = False

                                    def show_edit_field(field, label_widget, name, *args):
                                        field.model.set_value(name)
                                        field.visible = True
                                        label_widget.visible = False
                                        field.focus_keyboard()

                                    trigger_fn = partial(show_edit_field, label_field, label, node_name)
                                    label.set_mouse_double_clicked_fn(trigger_fn)

                                    # Register trigger for context menu access
                                    # (with weak ref to detect widget destruction)
                                    prim_path = node.GetPath()
                                    _edit_triggers[prim_path] = (weakref.ref(label_field), trigger_fn)

                                    def label_edited(field, label_widget, *args):
                                        field.visible = False
                                        label_widget.visible = True
                                        model[node].name = field.model.as_string
                                        model._item_changed(None)  # noqa: SLF001

                                    label_field.model.add_end_edit_fn(partial(label_edited, label_field, label))
                                ui.Spacer()
                            ui.Spacer()
                    ui.Rectangle(
                        height=HEADER["height"],
                        style=style,
                        name=node_category,
                        style_type_name_override="Graph.Node.Category",
                    )
            ui.Spacer(height=HIGHLIGHT_THICKNESS)
        return header

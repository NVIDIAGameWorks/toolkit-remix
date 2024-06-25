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

from typing import Dict, List, Tuple

import carb.input
import omni.appwindow
from omni import ui
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

try:
    from shapely.geometry import Point, Polygon
    from shapely.strtree import STRtree
except ImportError:
    pass  # for the docs to build


class NavigatorWidget:
    def __init__(self):
        self._default_attr = {"_widgets": None, "_current_selected_id": None}
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._widgets = {}

    def register_widgets(self, widgets: Dict[str, ui.Widget]):
        """
        Register the navigable widgets.

        **The registered widgets must have at least 1 pixel spacing between each other, or the nearest neighbor will
        be filtered out.**

        Args:
            widgets: dictionary of widget ids and widgets to register to the navigator
        """
        self._widgets.update(widgets)

    def unregister_widgets(self, ids: List[str] = None):
        """
        Unregister the navigable widgets.

        Args:
            ids: list of widget ids to unregister from the navigator, if None all the widgets will be unregistered
        """
        if ids is None:
            self._current_selected_id = None
            self._widgets.clear()
            return

        for widget_id in ids:
            if widget_id not in self._widgets:
                continue
            if self._current_selected_id == widget_id:
                self._current_selected_id = None
            del self._widgets[widget_id]

    def get_widgets(self):
        """
        Get the dictionary of registered widgets
        """
        return self._widgets

    def get_current_selected_id(self):
        """
        Get the ID of the currently selected widget
        """
        return self._current_selected_id

    def set_current_selected_id(self, widget_id):
        """
        Set the ID of the currently selected widget
        """
        self._current_selected_id = widget_id

    def go_left(self):
        """
        Select the nearest widget to the left of the current selected item.

        **The registered widgets must have at least 1 pixel spacing between each other, or the nearest neighbor will
        be filtered out.**

        Returns:
            The id of the new selected object
        """
        if self._current_selected_id is None:
            self._current_selected_id = self._get_closest_from_point()
        else:
            # get the closest from the middle of the top of the models
            self._current_selected_id = self._get_closest_from_point(
                point=(
                    self._widgets[self._current_selected_id].screen_position_x,
                    self._widgets[self._current_selected_id].screen_position_y
                    + (self._widgets[self._current_selected_id].computed_height / 2),
                ),
                under_x=self._widgets[self._current_selected_id].screen_position_x,
            )
        return self._current_selected_id

    def go_right(self):
        """
        Select the nearest widget to the right of the current selected item.

        **The registered widgets must have at least 1 pixel spacing between each other, or the nearest neighbor will
        be filtered out.**

        Returns:
            The id of the new selected object
        """
        if self._current_selected_id is None:
            self._current_selected_id = self._get_closest_from_point()
        else:
            # get the closest from the middle of the top of the models
            self._current_selected_id = self._get_closest_from_point(
                point=(
                    self._widgets[self._current_selected_id].screen_position_x
                    + self._widgets[self._current_selected_id].computed_width,
                    self._widgets[self._current_selected_id].screen_position_y
                    + (self._widgets[self._current_selected_id].computed_height / 2),
                ),
                over_x=self._widgets[self._current_selected_id].screen_position_x
                + self._widgets[self._current_selected_id].computed_width,
            )
        return self._current_selected_id

    def go_down(self):
        """
        Select the nearest widget under the current selected item.

        **The registered widgets must have at least 1 pixel spacing between each other, or the nearest neighbor will
        be filtered out.**

        Returns:
            The id of the new selected object
        """
        if self._current_selected_id is None:
            self._current_selected_id = self._get_closest_from_point()
        else:
            # get the closest from the middle of the top of the models
            self._current_selected_id = self._get_closest_from_point(
                point=(
                    self._widgets[self._current_selected_id].screen_position_x
                    + (self._widgets[self._current_selected_id].computed_width / 2),
                    self._widgets[self._current_selected_id].screen_position_y
                    + self._widgets[self._current_selected_id].computed_height,
                ),
                over_y=self._widgets[self._current_selected_id].screen_position_y
                + self._widgets[self._current_selected_id].computed_height,
            )
        return self._current_selected_id

    def go_up(self):
        """
        Select the nearest widget over the current selected item.

        **The registered widgets must have at least 1 pixel spacing between each other, or the nearest neighbor will
        be filtered out.**

        Returns:
            The id of the new selected object
        """
        if self._current_selected_id is None:
            self._current_selected_id = self._get_closest_from_point()
        else:
            # get the closest from the middle of the top of the models
            self._current_selected_id = self._get_closest_from_point(
                point=(
                    self._widgets[self._current_selected_id].screen_position_x
                    + (self._widgets[self._current_selected_id].computed_width / 2),
                    self._widgets[self._current_selected_id].screen_position_y,
                ),
                under_y=self._widgets[self._current_selected_id].screen_position_y,
            )
        return self._current_selected_id

    def _get_current_mouse_coords(self):
        app_window = omni.appwindow.get_default_app_window()
        input_interface = carb.input.acquire_input_interface()
        dpi_scale = ui.Workspace.get_dpi_scale()
        pos_x, pos_y = input_interface.get_mouse_coords_pixel(app_window.get_mouse())
        return pos_x / dpi_scale, pos_y / dpi_scale

    def _get_closest_from_point(
        self,
        point: Tuple[int, int] = None,
        over_x=None,
        over_y=None,
        under_x=None,
        under_y=None,
    ):
        if point is None:
            point = self._get_current_mouse_coords()
        geo_point = Point(point)

        polys = []
        active_ids = []
        for widget_id, widget in self._widgets.items():
            if not widget.visible or not widget.enabled:
                continue
            if self._current_selected_id is not None and widget_id == self._current_selected_id:
                continue
            if over_x is not None and widget.screen_position_x + widget.computed_width <= over_x:
                continue
            if over_y is not None and widget.screen_position_y + widget.computed_height <= over_y:
                continue
            if under_x is not None and under_x <= widget.screen_position_x + widget.computed_width:
                continue
            if under_y is not None and under_y <= widget.screen_position_y + widget.computed_height:
                continue
            active_ids.append(widget_id)
            polys.append(
                Polygon(
                    [
                        [widget.screen_position_x, widget.screen_position_y + widget.computed_height],
                        [
                            widget.screen_position_x + widget.computed_width,
                            widget.screen_position_y + widget.computed_height,
                        ],
                        [widget.screen_position_x + widget.computed_width, widget.screen_position_y],
                        [widget.screen_position_x, widget.screen_position_y],
                    ]
                )
            )
        if not polys:
            return self._current_selected_id

        tree = STRtree(polys)
        nearest_poly = tree.nearest(geo_point)
        return active_ids[polys.index(tree.geometries.take(nearest_poly))]

    def destroy(self):
        _reset_default_attrs(self)

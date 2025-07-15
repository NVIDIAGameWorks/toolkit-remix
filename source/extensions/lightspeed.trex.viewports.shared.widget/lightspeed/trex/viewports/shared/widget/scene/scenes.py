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

from typing import Any, Dict

__all__ = ["SimpleGrid", "SimpleOrigin", "CameraAxisLayer"]

# Simple scene items that don't yet warrant a devoted extension

import omni.ui
from omni.ui import color as cl
from omni.ui import scene as sc
from pxr import UsdGeom

from .utils import flatten_rot_matrix as _flatten_rot_matrix


def _check_legacy_display_option(flag):
    import carb

    display_options = carb.settings.get_settings().get("/persistent/app/viewport/displayOptions")
    return bool(display_options & flag) if display_options is not None else False


class SimpleGrid:

    _DEFAULT_COLOR: cl = cl(0.25)

    def __init__(
        self,
        viewport_api,
        line_count: float = 100,
        line_step: float = 10,
        thickness: float = 1,
        color: cl = _DEFAULT_COLOR,
    ):
        self.__transform = sc.Transform()
        with self.__transform:
            for i in range(line_count * 2 + 1):
                sc.Line(
                    ((i - line_count) * line_step, 0, -line_count * line_step),
                    ((i - line_count) * line_step, 0, line_count * line_step),
                    color=color,
                    thickness=thickness,
                )
                sc.Line(
                    (-line_count * line_step, 0, (i - line_count) * line_step),
                    (line_count * line_step, 0, (i - line_count) * line_step),
                    color=color,
                    thickness=thickness,
                )

        self.__vc_change = viewport_api.subscribe_to_view_change(self.__view_changed)

        self.visible = _check_legacy_display_option(1 << 6)

    def __del__(self):
        self.destroy()

    def __view_changed(self, viewport_api):
        stage = viewport_api.stage
        up = UsdGeom.GetStageUpAxis(stage) if stage else None
        if up == UsdGeom.Tokens.z:
            self.__transform.transform = [0, 1, 0, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 1]
        elif up == UsdGeom.Tokens.x:
            self.__transform.transform = [0, 0, 1, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1]
        else:
            self.__transform.transform = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]

    @property
    def name(self):
        return "Grid"

    @property
    def categories(self):
        return ["guide"]

    @property
    def visible(self):
        return self.__transform.visible

    @visible.setter
    def visible(self, value):
        self.__transform.visible = bool(value)

    def destroy(self):
        if self.__vc_change:
            self.__vc_change.destroy()
            self.__vc_change = None


class SimpleOrigin:
    def __init__(self, viewport_api, visible: bool = False, length: float = 5, thickness: float = 4):
        origin = (0, 0, 0)
        self._transform = sc.Transform(visible=visible)
        with self._transform:
            sc.Line(origin, (length, 0, 0), color=cl.red, thickness=thickness)
            sc.Line(origin, (0, length, 0), color=cl.green, thickness=thickness)
            sc.Line(origin, (0, 0, length), color=cl.blue, thickness=thickness)

    @property
    def name(self):
        return "Origin"

    @property
    def categories(self):
        return ["guide"]

    @property
    def visible(self):
        return self._transform.visible

    @visible.setter
    def visible(self, value):
        self._transform.visible = bool(value)


class CameraAxisLayer:
    def __init__(self, viewport_api):
        self.__transform = None
        self.__scene_view = None
        self.__vc_change = None
        self.__root = None

        visible = _check_legacy_display_option(1 << 1)
        width, height = 60, 60
        alignment = omni.ui.Alignment.LEFT_BOTTOM
        direction = omni.ui.Direction.BOTTOM_TO_TOP
        self.__root = omni.ui.Stack(direction, visible=visible)
        with self.__root:
            self.__scene_view = sc.SceneView(alignment=alignment, width=width, height=height)
            omni.ui.Spacer()

        thickness = 2
        length = 0.5
        text_offset = length + 0.25
        text_size = 14
        colors = (
            (0.6666, 0.3765, 0.3765, 1.0),
            (0.4431, 0.6392, 0.4627, 1.0),
            (0.3098, 0.4901, 0.6274, 1.0),
        )
        labels = ("X", "Y", "Z")
        with self.__scene_view.scene:
            origin = (0, 0, 0)
            self.__transform = sc.Transform()
            with self.__transform:
                for i in range(3):
                    color = colors[i]
                    vector = [0, 0, 0]
                    vector[i] = length
                    sc.Line(origin, vector, color=color, thickness=thickness)

                    vector[i] = text_offset
                    with sc.Transform(transform=sc.Matrix44.get_translation_matrix(vector[0], vector[1], vector[2])):
                        sc.Label(labels[i], color=color, alignment=omni.ui.Alignment.CENTER, size=text_size)

        self.__vc_change = viewport_api.subscribe_to_view_change(self.__view_changed)

    def __view_changed(self, viewport_api):
        self.__transform.transform = _flatten_rot_matrix(viewport_api.view.GetOrthonormalized().ExtractRotationMatrix())

    def destroy(self):
        if self.__vc_change:
            self.__vc_change.destroy()
            self.__vc_change = None
        if self.__transform:
            self.__transform.clear()
            self.__transform = None
        if self.__scene_view:
            self.__scene_view.destroy()
            self.__scene_view = None
        if self.__root:
            self.__root.clear()
            self.__root.destroy()
            self.__root = None

    @property
    def visible(self):
        return self.__root.visible

    @visible.setter
    def visible(self, value):
        self.__root.visible = value

    @property
    def categories(self):
        return ["guide"]

    @property
    def name(self):
        return "Axis"


def grid_default_factory(desc: Dict[str, Any]):
    manip = SimpleGrid(desc.get("viewport_api"))
    return manip


def origin_default_factory(desc: Dict[str, Any]):
    manip = SimpleOrigin(desc.get("viewport_api"))
    return manip


def camera_axis_default_factory(desc: Dict[str, Any]):
    manip = CameraAxisLayer(desc.get("viewport_api"))
    return manip

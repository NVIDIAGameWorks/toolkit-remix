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

import functools
from enum import Enum
from typing import Callable

import omni.kit.commands
import omni.kit.undo
import omni.kit.usd.layers
import omni.ui as ui
import omni.usd
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.widget.background_pattern import create_widget_with_pattern as _create_widget_with_pattern
from pxr import UsdGeom, UsdLux


class LightType(Enum):
    CYLINDER_LIGHT = "CylinderLight"
    DISK_LIGHT = "DiskLight"
    DISTANT_LIGHT = "DistantLight"
    RECT_LIGHT = "RectLight"
    SPHERE_LIGHT = "SphereLight"


class LightCreatorWidget:
    def __init__(self, context_name: str, create_under_path: str = None, callback: Callable[[str], None] = None):
        """
        Create the light creator widget

        Args:
            context_name: the context to use when we create the light(s)
            create_under_path: the path of the parent prim
            callback: executed at the end of the creation of the light(s)
        """
        self._default_attr = {"_root_frame": None}
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._create_under_path = create_under_path
        self._callback = callback
        self._context_name = context_name
        self._context = omni.usd.get_context(context_name)

        self.__create_ui()

    def __create_ui(self):
        self._root_frame = ui.Frame()
        with self._root_frame:
            with ui.VStack():
                ui.Spacer(height=ui.Pixel(8))
                with ui.HStack():
                    size = 56
                    ui.Spacer(height=0)
                    _create_widget_with_pattern(
                        functools.partial(
                            ui.Button,
                            "Cylinder",
                            name="LightCylinder",
                            clicked_fn=functools.partial(self.__create_light, LightType.CYLINDER_LIGHT),
                        ),
                        "BackgroundButton",
                        height=ui.Pixel(size),
                        width=ui.Pixel(size),
                        background_margin=(2, 2),
                    )
                    ui.Spacer(width=ui.Pixel(8), height=0)
                    _create_widget_with_pattern(
                        functools.partial(
                            ui.Button,
                            "Disk",
                            name="LightDisk",
                            clicked_fn=functools.partial(self.__create_light, LightType.DISK_LIGHT),
                        ),
                        "BackgroundButton",
                        height=ui.Pixel(size),
                        width=ui.Pixel(size),
                        background_margin=(2, 2),
                    )
                    ui.Spacer(width=ui.Pixel(8), height=0)
                    _create_widget_with_pattern(
                        functools.partial(
                            ui.Button,
                            "Distant",
                            name="LightDistant",
                            clicked_fn=functools.partial(self.__create_light, LightType.DISTANT_LIGHT),
                        ),
                        "BackgroundButton",
                        height=ui.Pixel(size),
                        width=ui.Pixel(size),
                        background_margin=(2, 2),
                    )
                    ui.Spacer(width=ui.Pixel(8), height=0)
                    _create_widget_with_pattern(
                        functools.partial(
                            ui.Button,
                            "Rect",
                            name="LightRect",
                            clicked_fn=functools.partial(self.__create_light, LightType.RECT_LIGHT),
                        ),
                        "BackgroundButton",
                        height=ui.Pixel(size),
                        width=ui.Pixel(size),
                        background_margin=(2, 2),
                    )
                    ui.Spacer(width=ui.Pixel(8), height=0)
                    _create_widget_with_pattern(
                        functools.partial(
                            ui.Button,
                            "Sphere",
                            name="LightSphere",
                            clicked_fn=functools.partial(self.__create_light, LightType.SPHERE_LIGHT),
                        ),
                        "BackgroundButton",
                        height=ui.Pixel(size),
                        width=ui.Pixel(size),
                        background_margin=(2, 2),
                    )
                    ui.Spacer(height=0)

    def __create_light(self, light_type: LightType):
        stage = self._context.get_stage()
        if stage:
            meters_per_unit = UsdGeom.GetStageMetersPerUnit(stage)
        else:
            meters_per_unit = 0.01

        geom_base = 5.0 / meters_per_unit
        geom_base_double = geom_base * 2
        attributes = {
            LightType.DISTANT_LIGHT: {UsdLux.Tokens.inputsAngle: 1.0, UsdLux.Tokens.inputsIntensity: 25},
            LightType.SPHERE_LIGHT: {UsdLux.Tokens.inputsRadius: geom_base, UsdLux.Tokens.inputsIntensity: 100},
            LightType.RECT_LIGHT: {
                UsdLux.Tokens.inputsWidth: geom_base_double,
                UsdLux.Tokens.inputsHeight: geom_base_double,
                UsdLux.Tokens.inputsIntensity: 400,
            },
            LightType.DISK_LIGHT: {UsdLux.Tokens.inputsRadius: geom_base, UsdLux.Tokens.inputsIntensity: 500},
            LightType.CYLINDER_LIGHT: {
                UsdLux.Tokens.inputsLength: geom_base_double,
                UsdLux.Tokens.inputsRadius: geom_base,
                UsdLux.Tokens.inputsIntensity: 140,
            },
        }

        if self._create_under_path is not None:
            prim_path = omni.usd.get_stage_next_free_path(
                stage, self._create_under_path + f"/{light_type.value}", False
            )
        else:
            selection = self._context.get_selection().get_selected_prim_paths()
            if selection:
                prim_path = omni.usd.get_stage_next_free_path(stage, selection[0] + f"/{light_type.value}", False)
            else:
                prim_path = omni.usd.get_stage_next_free_path(stage, f"/{light_type.value}", False)

        with omni.kit.undo.group():
            omni.kit.commands.execute(
                "CreatePrim",
                prim_type=light_type.value,
                prim_path=prim_path,
                attributes=attributes[light_type],
                context_name=self._context_name,
                select_new_prim=False,
            )
            if self._callback:
                self._callback(prim_path)

    def show(self, value):
        """
        Show the widget or not

        Args:
            value: visible or not
        """
        self._root_frame.visible = value

    def destroy(self):
        if self._root_frame:
            self._root_frame.clear()
        _reset_default_attrs(self)

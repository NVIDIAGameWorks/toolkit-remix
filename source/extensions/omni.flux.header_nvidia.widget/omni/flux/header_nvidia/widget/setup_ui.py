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

import carb.settings
import omni.ui as ui
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.widget.color import hex_to_color as _hex_to_color
from omni.flux.utils.widget.gradient import create_gradient as _create_gradient
from omni.flux.utils.widget.label import create_label_with_font as _create_label_with_font

_APP_NAME = "/app/name"


class HeaderWidget:
    def __init__(self):
        """
        Create the header widget

        Returns:
            The header object
        """

        self._default_attr = {
            "_image_provider": None,
            "_gradient_image_provider": None,
            "_gradient_image_with_provider": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)
        self.__update_default_style()
        self.__create_ui()

    def __update_default_style(self):
        """
        We need default color value for the gradient
        """
        style = ui.Style.get_instance()
        current_dict = style.default
        if "ImageWithProvider::HeaderNvidiaBackground" not in current_dict:
            current_dict["ImageWithProvider::HeaderNvidiaBackground"] = {
                "background_color": 0x33000000,
                "background_gradient_color": 0x00000000,
            }
        style.default = current_dict

    def __create_ui(self):
        style = ui.Style.get_instance()
        with ui.ZStack(height=ui.Pixel(144)):
            # gradient
            color1 = _hex_to_color(style.default["ImageWithProvider::HeaderNvidiaBackground"]["background_color"])
            color2 = _hex_to_color(
                style.default["ImageWithProvider::HeaderNvidiaBackground"]["background_gradient_color"]
            )
            width_image = 1024
            height_image = 144
            array = _create_gradient(width_image, height_image, color1, color2, (True, True, True, True))
            self._gradient_image_provider = ui.ByteImageProvider()
            self._gradient_image_with_provider = ui.ImageWithProvider(
                self._gradient_image_provider,
                height=height_image,
                fill_policy=ui.IwpFillPolicy.IWP_STRETCH,
                name="HeaderNvidiaBackground",
            )
            self._gradient_image_provider.set_bytes_data(array.ravel().tolist(), [width_image, height_image])

            with ui.HStack():
                ui.Spacer()
                # nvidia logo
                with ui.VStack(width=ui.Percent(15)):
                    ui.Spacer(height=ui.Pixel(40))
                    ui.Image("", name="NvidiaShort", height=ui.Pixel(40))
                ui.Spacer(width=ui.Percent(1))
                # line
                with ui.VStack(width=ui.Percent(1.5)):
                    ui.Spacer(height=ui.Pixel(16))
                    with ui.ZStack(height=ui.Pixel(87)):
                        with ui.VStack():
                            with ui.HStack():
                                ui.Spacer()
                                rect1 = ui.Rectangle(width=0, height=0)
                            rect2 = ui.Rectangle(width=0, height=0)
                        ui.FreeBezierCurve(
                            rect1,
                            rect2,
                            start_tangent_width=ui.Percent(1),
                            end_tangent_width=ui.Percent(1),
                            name="HeaderNvidiaLine",
                        )

                ui.Spacer(width=ui.Percent(1))
                with ui.VStack(width=ui.Percent(29)):
                    ui.Spacer(height=ui.Pixel(48))

                    height_image = ui.Pixel(24)
                    settings = carb.settings.get_settings()
                    name = settings.get(_APP_NAME)
                    if not name:
                        name = "App name"
                    style = ui.Style.get_instance()
                    current_dict = style.default
                    if "ImageWithProvider::HeaderNvidiaTitle" not in current_dict:
                        # use regular labels
                        ui.Label(name.upper())
                    else:
                        # use custom styled font
                        self._image_provider, _, _ = _create_label_with_font(
                            name.upper(), "HeaderNvidiaTitle", custom_image_height=height_image
                        )

                    ui.Spacer(height=ui.Pixel(72))
                ui.Spacer(width=ui.Percent(10))

    def destroy(self):
        _reset_default_attrs(self)

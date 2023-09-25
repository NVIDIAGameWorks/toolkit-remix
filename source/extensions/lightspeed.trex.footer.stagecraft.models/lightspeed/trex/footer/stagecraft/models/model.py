"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import webbrowser
from functools import partial
from typing import Callable, Dict, Tuple

import carb.settings
import omni.kit.app
import omni.ui as ui
from omni.flux.footer.widget.model import FooterModel
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs


class StageCraftFooterModel(FooterModel):
    def __init__(self):
        super().__init__()
        self._default_attr = {}
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        settings = carb.settings.get_settings()
        self.__kit_version = omni.kit.app.get_app().get_build_version()
        self.__app_version = settings.get("/app/version")

    def content(self) -> Dict[int, Tuple[Callable]]:
        """Get the data
        First int if the column number, Tuple of Callable that wiull create the UI
        """
        return {
            0: (),
            1: (partial(ui.Spacer, height=ui.Pixel(24)), self.__about_sdg, self.__account, self.__license_agreement),
            2: (
                partial(ui.Spacer, height=ui.Pixel(24)),
                self.__technical_support,
                self.__report_issue,
                self.__help,
                self.__documentation,
            ),
        }

    def __about_sdg(self):
        with ui.VStack(height=ui.Pixel(24)):
            ui.Spacer()
            ui.Label("About RTX Remix", name="FooterLabel")
            ui.Spacer()

    def __account(self):
        with ui.VStack(height=ui.Pixel(24)):
            ui.Spacer()
            ui.Label("Account", name="FooterLabel")
            ui.Spacer()

    def __license_agreement(self):
        with ui.VStack(height=ui.Pixel(24)):
            ui.Spacer()
            label = ui.Label("License agreement", name="FooterLabel")
            ui.Spacer()

        label.set_mouse_pressed_fn(lambda x, y, b, m: self.__open_nvidia_url())

    def __open_nvidia_url(self):
        url = "https://www.nvidia.com/"
        webbrowser.open(url, new=0, autoraise=True)

    def __technical_support(self):
        with ui.HStack(height=ui.Pixel(24)):
            with ui.VStack():
                ui.Spacer()
                ui.Label("Technical Support", name="FooterLabel")
                ui.Spacer()
            ui.Spacer()
            with ui.VStack(width=ui.Pixel(0)):
                ui.Spacer()
                ui.Label(str(self.__kit_version), name="FooterLabel")
                ui.Spacer()

    def __report_issue(self):
        with ui.HStack(height=ui.Pixel(24)):
            with ui.VStack():
                ui.Spacer()
                ui.Label("Report an issue", name="FooterLabel")
                ui.Spacer()
            ui.Spacer()
            with ui.VStack(width=ui.Pixel(0)):
                ui.Spacer()
                ui.Label(str(self.__app_version), name="FooterLabel")
                ui.Spacer()

    def __help(self):
        with ui.VStack(height=ui.Pixel(24)):
            ui.Spacer()
            ui.Label("Help", name="FooterLabel")
            ui.Spacer()

    def __documentation(self):
        with ui.VStack(height=ui.Pixel(24)):
            ui.Spacer()
            ui.Label("Documentation", name="FooterLabel")
            ui.Spacer()

    def destroy(self):
        _reset_default_attrs(self)

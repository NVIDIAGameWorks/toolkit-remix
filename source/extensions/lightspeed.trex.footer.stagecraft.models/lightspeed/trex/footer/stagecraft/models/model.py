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
from lightspeed.common.constants import (
    COMMUNITY_SUPPORT_URL,
    CREDITS,
    DOCUMENTATION_URL,
    GITHUB_URL,
    LICENSE_AGREEMENT_URL,
    RELEASE_NOTES_URL,
    REPORT_ISSUE_URL,
    TUTORIALS_URL,
)
from omni.flux.footer.widget.model import FooterModel
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs


class CreditsWindow(ui.Window):
    def hide(self):
        self.visible = False


class StageCraftFooterModel(FooterModel):
    def __init__(self):
        super().__init__()
        self._default_attr = {"_popup": None}
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
            1: (
                partial(ui.Spacer, height=ui.Pixel(24)),
                self.__about_sdg,
                self.__license_agreement,
                self.__release_notes,
                self.__documentation,
            ),
            2: (
                partial(ui.Spacer, height=ui.Pixel(24)),
                self.__tutorials,
                self.__community_support,
                self.__github,
                self.__report_issue,
            ),
        }

    def __open_nvidia_url(self, url):
        webbrowser.open(url, new=0, autoraise=True)

    def __credits(self):

        self._popup = CreditsWindow(
            "Credits",
            visible=True,
            width=300,
            height=500,
            dockPreference=ui.DockPreference.DISABLED,
            flags=(
                ui.WINDOW_FLAGS_NO_COLLAPSE
                | ui.WINDOW_FLAGS_NO_MOVE
                | ui.WINDOW_FLAGS_NO_RESIZE
                | ui.WINDOW_FLAGS_NO_CLOSE
                | ui.WINDOW_FLAGS_MODAL
            ),
        )

        with self._popup.frame:
            with ui.VStack():
                ui.Spacer(width=0, height=ui.Pixel(8))
                with ui.HStack():
                    ui.Spacer(width=ui.Pixel(8), height=0)
                    with ui.ScrollingFrame(height=ui.Percent(100)):
                        ui.StringField(multiline=True, read_only=True).model.set_value(CREDITS)
                    ui.Spacer(width=ui.Pixel(8), height=0)
                ui.Spacer(width=0, height=ui.Pixel(8))
                with ui.HStack(height=24):
                    ui.Spacer(height=0)
                    ui.Button("Okay", width=ui.Pixel(100), clicked_fn=self._popup.hide)
                    ui.Spacer(height=0)
                ui.Spacer(width=0, height=ui.Pixel(8))

    def __about_sdg(self):
        with ui.VStack(height=ui.Pixel(24)):
            ui.Spacer()
            label = ui.Label("About RTX Remix", name="FooterLabel")
            ui.Spacer()

        label.set_mouse_pressed_fn(lambda x, y, b, m: self.__credits())

    def __license_agreement(self):
        with ui.VStack(height=ui.Pixel(24)):
            ui.Spacer()
            label = ui.Label("License Agreement", name="FooterLabel")
            ui.Spacer()

        label.set_mouse_pressed_fn(lambda x, y, b, m: self.__open_nvidia_url(LICENSE_AGREEMENT_URL))

    def __release_notes(self):
        with ui.VStack(height=ui.Pixel(24)):
            ui.Spacer()
            label = ui.Label("Release Notes", name="FooterLabel")
            ui.Spacer()

        label.set_mouse_pressed_fn(lambda x, y, b, m: self.__open_nvidia_url(RELEASE_NOTES_URL))

    def __documentation(self):
        with ui.VStack(height=ui.Pixel(24)):
            ui.Spacer()
            label = ui.Label("Documentation", name="FooterLabel")
            ui.Spacer()

        label.set_mouse_pressed_fn(lambda x, y, b, m: self.__open_nvidia_url(DOCUMENTATION_URL))

    def __community_support(self):
        with ui.HStack(height=ui.Pixel(24)):
            with ui.VStack():
                ui.Spacer()
                label = ui.Label("Community", name="FooterLabel")
                ui.Spacer()
            with ui.VStack(width=0):
                ui.Spacer()
                ui.Label(str(self.__kit_version), name="FooterLabel")
                ui.Spacer()

        label.set_mouse_pressed_fn(lambda x, y, b, m: self.__open_nvidia_url(COMMUNITY_SUPPORT_URL))

    def __tutorials(self):
        with ui.HStack(height=ui.Pixel(24)):
            with ui.VStack():
                ui.Spacer()
                label = ui.Label("Tutorials", name="FooterLabel")
                ui.Spacer()
            with ui.VStack(width=0):
                ui.Spacer()
                ui.Label(str(self.__app_version), name="FooterLabel")
                ui.Spacer()

        label.set_mouse_pressed_fn(lambda x, y, b, m: self.__open_nvidia_url(TUTORIALS_URL))

    def __github(self):
        with ui.VStack(height=ui.Pixel(24)):
            ui.Spacer()
            label = ui.Label("GitHub", name="FooterLabel")
            ui.Spacer()

        label.set_mouse_pressed_fn(lambda x, y, b, m: self.__open_nvidia_url(GITHUB_URL))

    def __report_issue(self):
        with ui.VStack(height=ui.Pixel(24)):
            ui.Spacer()
            label = ui.Label("Report an Issue", name="FooterLabel")
            ui.Spacer()

        label.set_mouse_pressed_fn(lambda x, y, b, m: self.__open_nvidia_url(REPORT_ISSUE_URL))

    def destroy(self):
        _reset_default_attrs(self)

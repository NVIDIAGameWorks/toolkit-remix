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
from omni.flux.utils.widget.label import create_label_with_font


class StageCraftFooterModel(FooterModel):
    def __init__(self):
        super().__init__()
        self._default_attr = {
            "_image_provider_about_trex": None,
            "_image_provider_account": None,
            "_image_provider_app_build_number": None,
            "_image_provider_documentation": None,
            "_image_provider_help": None,
            "_image_provider_kit_build_number": None,
            "_image_provider_license_agreement": None,
            "_image_provider_report_issue": None,
            "_image_provider_technical_support": None,
        }
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
            self._image_provider_about_trex, _, _ = create_label_with_font(
                "About Trex", "FooterLabel", remove_offset=True, quality_multiplier=1
            )
            ui.Spacer()

    def __account(self):
        with ui.VStack(height=ui.Pixel(24)):
            ui.Spacer()
            self._image_provider_account, _, _ = create_label_with_font(
                "Account", "FooterLabel", remove_offset=True, quality_multiplier=1
            )
            ui.Spacer()

    def __license_agreement(self):
        with ui.VStack(height=ui.Pixel(24)):
            ui.Spacer()
            self._image_provider_license_agreement, image, _ = create_label_with_font(
                "License agreement", "FooterLabel", remove_offset=True, quality_multiplier=1
            )
            ui.Spacer()

        image.set_mouse_pressed_fn(lambda x, y, b, m: self.__open_nvidia_url())

    def __open_nvidia_url(self):
        url = "https://www.nvidia.com/"
        webbrowser.open(url, new=0, autoraise=True)

    def __technical_support(self):
        with ui.HStack(height=ui.Pixel(24)):
            with ui.VStack():
                ui.Spacer()
                self._image_provider_technical_support, _, _ = create_label_with_font(
                    "Technical Support", "FooterLabel", remove_offset=True, quality_multiplier=1
                )
                ui.Spacer()
            ui.Spacer()
            with ui.VStack(width=ui.Pixel(0)):
                ui.Spacer()
                self._image_provider_kit_build_number, _, _ = create_label_with_font(
                    self.__kit_version, "FooterLabel", remove_offset=True, quality_multiplier=1
                )
                ui.Spacer()

    def __report_issue(self):
        with ui.HStack(height=ui.Pixel(24)):
            with ui.VStack():
                ui.Spacer()
                self._image_provider_report_issue, _, _ = create_label_with_font(
                    "Report an issue", "FooterLabel", remove_offset=True, quality_multiplier=1
                )
                ui.Spacer()
            ui.Spacer()
            with ui.VStack(width=ui.Pixel(0)):
                ui.Spacer()
                self._image_provider_app_build_number, _, _ = create_label_with_font(
                    self.__app_version, "FooterLabel", remove_offset=True, quality_multiplier=1
                )
                ui.Spacer()

    def __help(self):
        with ui.VStack(height=ui.Pixel(24)):
            ui.Spacer()
            self._image_provider_help, _, _ = create_label_with_font(
                "Help", "FooterLabel", remove_offset=True, quality_multiplier=1
            )
            ui.Spacer()

    def __documentation(self):
        with ui.VStack(height=ui.Pixel(24)):
            ui.Spacer()
            self._image_provider_documentation, _, _ = create_label_with_font(
                "Documentation", "FooterLabel", remove_offset=True, quality_multiplier=1
            )
            ui.Spacer()

    def destroy(self):
        _reset_default_attrs(self)

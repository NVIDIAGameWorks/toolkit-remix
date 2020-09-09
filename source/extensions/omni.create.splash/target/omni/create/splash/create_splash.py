# Copyright (c) 2018-2020, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.
#
import omni.ext
import asyncio

import omni.ui as ui
import carb.settings
import omni.kit.app
import carb.windowing
import omni.appwindow

from omni.kit.controlport import main as controlport

from pathlib import Path


class CreateSplashExtension(omni.ext.IExt):
    """"""

    def __init__(self):
        self._settings = carb.settings.get_settings()

    def _updateLog(self, data):
        self._log.text = "UPDATED"

    def on_startup(self, ext_id):
        extension_path = omni.kit.app.get_app().get_extension_manager().get_extension_path(ext_id)
        self._window = ui.Window("Splash", style={"Window": {"padding":0}})
        with self._window.frame:
            with ui.VStack():
                splash_path = f"{extension_path}/icons/create_splash.jpg"
                ui.Image(splash_path)
                ui.Label("Create is Starting....", height=0, alignment=ui.Alignment.CENTER, style={"font_size":30})
                self._log = ui.Label("LOG", height=0, alignment=ui.Alignment.CENTER, style={"font_size":22})

        controlport.register_endpoint("post", "/update-log", self._updateLog)

        self.__build_task = asyncio.ensure_future(self.__build_layout())

    async def __build_layout(self):
        frames = 2
        splash_handle = None
        while frames > 0:
            splash_handle = ui.Workspace.get_window("Splash")
            if splash_handle:
                break

            frames = frames - 1
            await omni.kit.app.get_app().next_update_async()

        if splash_handle is None:
            print("FAILED TO FIND Splash Window")
            return

        # setup the docking Space
        main_dockspace = ui.Workspace.get_window("DockSpace")

        splash_handle.dock_in(main_dockspace, ui.DockPosition.SAME)
        splash_handle.dock_tab_bar_visible = False

        app_window = omni.appwindow.get_default_app_window()
        oswindow = app_window.get_window()

        iwindowing = carb.windowing.acquire_windowing_interface()
        pos_x = 1600
        pos_y = 600
        iwindowing.set_window_position(oswindow, (pos_x, pos_y))

    def on_shutdown(self):
        self._window = None

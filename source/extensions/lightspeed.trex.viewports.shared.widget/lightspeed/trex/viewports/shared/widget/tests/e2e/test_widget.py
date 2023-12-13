"""
* Copyright (c) 2023, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import carb.settings
import omni.ui as ui
import omni.usd
from lightspeed.trex.viewports.shared.widget import create_instance as _create_viewport_instance
from omni.flux.utils.widget.resources import get_test_data as _get_test_data
from omni.kit import ui_test
from omni.kit.test.async_unittest import AsyncTestCase
from omni.kit.test_suite.helpers import open_stage, wait_stage_loading

WINDOW_HEIGHT = 1000
WINDOW_WIDTH = 1436


class TestSharedViewportWidget(AsyncTestCase):

    # Before running each test
    async def setUp(self):
        await open_stage(_get_test_data("usd/project_example/combined.usda"))

    # After running each test
    async def tearDown(self):
        await wait_stage_loading()

    async def __setup_widget(
        self, width=WINDOW_WIDTH, height=WINDOW_HEIGHT
    ) -> (ui.Window, list[_create_viewport_instance]):
        window = ui.Window("TestSharedViewportUI", width=width, height=height)
        with window.frame:
            with omni.ui.HStack():
                widget1 = _create_viewport_instance("")
                widget2 = _create_viewport_instance("")

        await ui_test.human_delay(human_delay_speed=1)

        return window, [widget1, widget2]

    async def __destroy(self, window, widgets):
        # if we destroy viewports before the stage is fully loaded than it will be stuck in loading state.
        await wait_stage_loading()

        for widget in widgets:
            widget.destroy()
        window.destroy()

    async def test_always_one_vp_enabled(self):
        """Test global viewport events that ensure only one viewport is active"""
        # setup
        _window, _widgets = await self.__setup_widget()  # Keep in memory during test

        self.assertTrue(len(_widgets) == 2)

        # make sure they were built
        viewports = ui_test.find_all(f"{_window.title}//Frame/**/.identifier == 'viewport'")
        self.assertTrue(len(viewports) == len(_widgets))

        # last created viewport should be enabled
        self.assertTrue(_widgets[0].viewport_api.updates_enabled is False)
        self.assertTrue(_widgets[1].viewport_api.updates_enabled is True)

        # after clicking on viewport 1, it should be enabled
        await viewports[0].click()
        self.assertTrue(_widgets[0].viewport_api.updates_enabled is True)
        self.assertTrue(_widgets[1].viewport_api.updates_enabled is False)

        # after clicking on viewport 2, it should be enabled and True disabled
        await viewports[1].click()
        self.assertTrue(_widgets[0].viewport_api.updates_enabled is False)
        self.assertTrue(_widgets[1].viewport_api.updates_enabled is True)

        await self.__destroy(_window, _widgets)

    async def test_deactivate_when_minimized(self):
        # setup
        carb.settings.get_settings().set("/app/renderer/skipWhileMinimized", True)
        _window, _widgets = await self.__setup_widget()  # Keep in memory during test
        app_window = omni.appwindow.get_default_app_window()
        minimize_event_stream = app_window.get_window_minimize_event_stream()
        viewports = ui_test.find_all(f"{_window.title}//Frame/**/.identifier == 'viewport'")

        # after clicking on viewport 1, it should be enabled
        await viewports[0].click()
        self.assertTrue(_widgets[0].viewport_api.updates_enabled is True)
        self.assertTrue(_widgets[1].viewport_api.updates_enabled is False)

        # while minimized, viewports should pause
        minimize_event_stream.push(payload={"isMinimized": True})
        await ui_test.wait_n_updates()
        self.assertTrue(_widgets[0].viewport_api.updates_enabled is False)
        self.assertTrue(_widgets[1].viewport_api.updates_enabled is False)

        # while restoring, last active viewport should unpause
        minimize_event_stream.push(payload={"isMinimized": False})
        await ui_test.wait_n_updates()
        self.assertTrue(_widgets[0].viewport_api.updates_enabled is True)
        self.assertTrue(_widgets[1].viewport_api.updates_enabled is False)

        # check that it will respect this preference and keep updating viewport 1
        carb.settings.get_settings().set("/app/renderer/skipWhileMinimized", False)
        minimize_event_stream.push(payload={"isMinimized": True})
        await ui_test.wait_n_updates()
        self.assertTrue(_widgets[0].viewport_api.updates_enabled is True)
        self.assertTrue(_widgets[1].viewport_api.updates_enabled is False)

        # while restoring, last active viewport should unpause
        minimize_event_stream.push(payload={"isMinimized": False})
        await ui_test.wait_n_updates()
        self.assertTrue(_widgets[0].viewport_api.updates_enabled is True)
        self.assertTrue(_widgets[1].viewport_api.updates_enabled is False)

        # after clicking on viewport 2, it should be enabled, and after minimizing and
        # restoring it should still be the one that is enabled.
        await viewports[1].click()
        carb.settings.get_settings().set("/app/renderer/skipWhileMinimized", True)
        self.assertTrue(_widgets[0].viewport_api.updates_enabled is False)
        self.assertTrue(_widgets[1].viewport_api.updates_enabled is True)
        minimize_event_stream.push(payload={"isMinimized": True})
        await ui_test.wait_n_updates()
        self.assertTrue(_widgets[0].viewport_api.updates_enabled is False)
        self.assertTrue(_widgets[1].viewport_api.updates_enabled is False)
        minimize_event_stream.push(payload={"isMinimized": False})
        await ui_test.wait_n_updates()
        self.assertTrue(_widgets[0].viewport_api.updates_enabled is False)
        self.assertTrue(_widgets[1].viewport_api.updates_enabled is True)

        await self.__destroy(_window, _widgets)
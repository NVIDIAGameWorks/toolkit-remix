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

from typing import TYPE_CHECKING

import carb.input
import carb.settings
import omni.appwindow
import omni.ui as ui
import omni.usd
from lightspeed.trex.contexts.setup import Contexts as _TrexContext
from lightspeed.trex.viewports.shared.widget import create_instance as _create_viewport_instance
from omni.flux.utils.widget.resources import get_test_data as _get_test_data
from omni.kit import ui_test
from omni.kit.test_suite.helpers import open_stage, wait_stage_loading
from omni.kit.ui_test import Vec2
from omni.ui.tests.test_base import OmniUiTest
from pxr import UsdGeom

if TYPE_CHECKING:
    from lightspeed.trex.viewports.shared.widget.setup_ui import SetupUI as _ViewportSetupUI

WINDOW_HEIGHT = 1000
WINDOW_WIDTH = 1436

_CONTEXT_NAME = ""
_CONTEXT_2_NAME = _TrexContext.STAGE_CRAFT.value


class TestSharedViewportWidget(OmniUiTest):
    # Before running each test
    async def setUp(self):
        await super().setUp()
        usd_context_1 = omni.usd.get_context(_CONTEXT_NAME)
        await open_stage(_get_test_data("usd/project_example/combined.usda"), usd_context=usd_context_1)
        usd_context_2 = omni.usd.create_context(_CONTEXT_2_NAME)
        await open_stage(
            _get_test_data("usd/project_example/ingested_assets/source/cube.usda"), usd_context=usd_context_2
        )

    # After running each test
    async def tearDown(self):
        await super().tearDown()
        await self.release_hydra_engines_workaround()

    async def release_hydra_engines_workaround(self, usd_context_name: str = ""):
        # copied from omni/kit/widget/viewport/tests/test_ray_query.py
        await self.wait_n_updates(10)
        omni.usd.release_all_hydra_engines(omni.usd.get_context(usd_context_name))
        await self.wait_n_updates(10)

    async def __setup_widget(self, width=WINDOW_WIDTH, height=WINDOW_HEIGHT) -> (ui.Window, list["_ViewportSetupUI"]):
        window = ui.Window("TestSharedViewportUI", width=width, height=height)
        with window.frame:
            with omni.ui.HStack():
                widget1 = _create_viewport_instance(_CONTEXT_NAME)
                widget2 = _create_viewport_instance(_CONTEXT_2_NAME)

        await ui_test.human_delay(human_delay_speed=1)

        return window, [widget1, widget2]

    async def __destroy(self, window, widgets):
        for widget in widgets:
            widget.destroy()
        window.destroy()

    async def test_always_one_vp_enabled(self):
        """Test global viewport events that ensure only one viewport is active."""

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
        await wait_stage_loading()  # make sure the stage gets a chance to load before minimizing

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
        await wait_stage_loading()  # make sure the stage gets a chance to load before minimizing

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
        carb.settings.get_settings().set("/app/renderer/skipWhileMinimized", True)
        await viewports[1].click()
        self.assertTrue(_widgets[0].viewport_api.updates_enabled is False)
        self.assertTrue(_widgets[1].viewport_api.updates_enabled is True)
        await wait_stage_loading(
            usd_context=omni.usd.get_context(_CONTEXT_2_NAME)
        )  # make sure the stage gets a chance to load before minimizing
        minimize_event_stream.push(payload={"isMinimized": True})
        await ui_test.wait_n_updates()
        self.assertTrue(_widgets[0].viewport_api.updates_enabled is False)
        self.assertTrue(_widgets[1].viewport_api.updates_enabled is False)
        minimize_event_stream.push(payload={"isMinimized": False})
        await ui_test.wait_n_updates()
        self.assertTrue(_widgets[0].viewport_api.updates_enabled is False)
        self.assertTrue(_widgets[1].viewport_api.updates_enabled is True)

        await self.__destroy(_window, _widgets)

    async def test_mouse_wheel_zoom_changes_active_viewport_camera(self):
        # Build the real shared viewport widgets with real USD stages so the event delegate is connected as it is in
        # app.
        window, widgets = await self.__setup_widget()
        try:
            viewports = ui_test.find_all(f"{window.title}//Frame/**/.identifier == 'viewport'")
            self.assertEqual(len(widgets), len(viewports))

            # Click the first viewport to make it active, then snapshot its active camera transform before scrolling.
            await wait_stage_loading(usd_context=omni.usd.get_context(_CONTEXT_NAME))
            await viewports[0].click()
            await ui_test.human_delay(human_delay_speed=2)
            viewport_api = widgets[0].viewport_api
            stage = omni.usd.get_context(viewport_api.usd_context_name).get_stage()
            camera_prim = stage.GetPrimAtPath(viewport_api.camera_path)
            self.assertTrue(camera_prim.IsValid())

            def camera_matrix() -> tuple[float, ...]:
                return tuple(
                    component
                    for row in UsdGeom.Xformable(camera_prim).GetLocalTransformation(viewport_api.time)
                    for component in row
                )

            initial_camera_matrix = camera_matrix()

            # Scroll over the viewport like a user would; the delegate should route this to the shared zoom operation.
            await ui_test.input.emulate_mouse_move(viewports[0].center)
            await ui_test.input.emulate_mouse_scroll(Vec2(0, -1200))

            # Wait for the viewport camera to settle after the discrete wheel event.
            for _ in range(60):
                if camera_matrix() != initial_camera_matrix:
                    break
                await ui_test.wait_n_updates()
            else:
                self.fail("Mouse-wheel zoom did not update the active viewport camera")
        finally:
            await self.__destroy(window, widgets)

    async def test_mouse_wheel_does_not_zoom_while_regular_key_is_held(self):
        # Build a real viewport so keyboard and wheel events go through the same delegate wiring as a user session.
        window, widgets = await self.__setup_widget()
        keyboard = omni.appwindow.get_default_app_window().get_keyboard()
        input_provider = carb.input.acquire_input_provider()
        key = carb.input.KeyboardInput.B
        key_is_down = False
        try:
            viewports = ui_test.find_all(f"{window.title}//Frame/**/.identifier == 'viewport'")
            self.assertEqual(len(widgets), len(viewports))

            # Activate the viewport and snapshot the camera before sending the key-held wheel event.
            await wait_stage_loading(usd_context=omni.usd.get_context(_CONTEXT_NAME))
            await viewports[0].click()
            await ui_test.human_delay(human_delay_speed=2)
            viewport_api = widgets[0].viewport_api
            stage = omni.usd.get_context(viewport_api.usd_context_name).get_stage()
            camera_prim = stage.GetPrimAtPath(viewport_api.camera_path)
            self.assertTrue(camera_prim.IsValid())

            def camera_matrix() -> tuple[float, ...]:
                return tuple(
                    component
                    for row in UsdGeom.Xformable(camera_prim).GetLocalTransformation(viewport_api.time)
                    for component in row
                )

            initial_camera_matrix = camera_matrix()

            # Hold a normal key while scrolling; the delegate should treat this as a tool shortcut and ignore zoom.
            input_provider.buffer_keyboard_key_event(keyboard, carb.input.KeyboardEventType.KEY_PRESS, key, 0)
            key_is_down = True
            await ui_test.wait_n_updates()
            await ui_test.input.emulate_mouse_move(viewports[0].center)
            await ui_test.input.emulate_mouse_scroll(Vec2(0, -1200))
            await ui_test.human_delay(human_delay_speed=4)
            self.assertEqual(initial_camera_matrix, camera_matrix())

            # Release the key and scroll again; zoom should be active once no regular key is held down.
            input_provider.buffer_keyboard_key_event(keyboard, carb.input.KeyboardEventType.KEY_RELEASE, key, 0)
            key_is_down = False
            await ui_test.wait_n_updates()
            await ui_test.input.emulate_mouse_scroll(Vec2(0, -1200))
            for _ in range(60):
                if camera_matrix() != initial_camera_matrix:
                    break
                await ui_test.wait_n_updates()
            else:
                self.fail("Mouse-wheel zoom did not resume after the held key was released")
        finally:
            if key_is_down:
                input_provider.buffer_keyboard_key_event(keyboard, carb.input.KeyboardEventType.KEY_RELEASE, key, 0)
                await ui_test.wait_n_updates()
            await self.__destroy(window, widgets)

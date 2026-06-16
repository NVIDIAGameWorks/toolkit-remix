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
import omni.kit.widget.toolbar as _toolbar_module
import omni.ui as ui
import omni.usd
from lightspeed.trex.contexts.extension import get_instance as _get_context_manager
from lightspeed.trex.contexts.setup import Contexts as _TrexContext
from lightspeed.trex.viewports.shared.widget import create_instance as _create_viewport_instance
from lightspeed.trex.viewports.shared.widget.tools import teleport as _teleport_tool
from omni.flux.utils.widget.resources import get_test_data as _get_test_data
from omni.kit import ui_test
from omni.kit.ui_test import Vec2
from omni.ui.tests.test_base import OmniUiTest
from pxr import UsdGeom

if TYPE_CHECKING:
    from lightspeed.trex.viewports.shared.widget.setup_ui import SetupUI as _ViewportSetupUI

WINDOW_HEIGHT = 1000
WINDOW_WIDTH = 1436

_CONTEXT_NAME = "TestSharedViewportContextA"
_CONTEXT_2_NAME = "TestSharedViewportContextB"


class TestSharedViewportWidget(OmniUiTest):
    # Before running each test
    async def setUp(self):
        await super().setUp()
        usd_context_1 = self.__ensure_context(_CONTEXT_NAME)
        await usd_context_1.open_stage_async(_get_test_data("usd/project_example/combined.usda"))
        await self.__wait_stage_loading(usd_context_1)
        usd_context_2 = self.__ensure_context(_CONTEXT_2_NAME)
        await usd_context_2.open_stage_async(_get_test_data("usd/project_example/ingested_assets/source/cube.usda"))
        await self.__wait_stage_loading(usd_context_2)

    # After running each test
    async def tearDown(self):
        await self.release_hydra_engines_workaround(_CONTEXT_NAME)
        await self.release_hydra_engines_workaround(_CONTEXT_2_NAME)
        await super().tearDown()

    async def release_hydra_engines_workaround(self, usd_context_name: str = ""):
        # copied from omni/kit/widget/viewport/tests/test_ray_query.py
        await self.wait_n_updates(10)
        usd_context = omni.usd.get_context(usd_context_name)
        if usd_context:
            omni.usd.release_all_hydra_engines(usd_context)
        await self.wait_n_updates(10)

    def __ensure_context(self, usd_context_name: str):
        usd_context = omni.usd.get_context(usd_context_name)
        if not usd_context:
            usd_context = omni.usd.create_context(usd_context_name)
        return usd_context

    async def __setup_widget(self, width=WINDOW_WIDTH, height=WINDOW_HEIGHT) -> (ui.Window, list["_ViewportSetupUI"]):
        window = ui.Window("TestSharedViewportUI", width=width, height=height)
        with window.frame:
            with omni.ui.HStack():
                widget1 = _create_viewport_instance(_CONTEXT_NAME)
                widget2 = _create_viewport_instance(_CONTEXT_2_NAME)

        await self.__wait_for_viewports(window.title, 2, [widget1, widget2])

        return window, [widget1, widget2]

    async def __setup_single_widget(self, width=WINDOW_WIDTH, height=WINDOW_HEIGHT) -> (ui.Window, "_ViewportSetupUI"):
        window = ui.Window("TestSharedViewportSingleUI", width=width, height=height)
        with window.frame:
            widget = _create_viewport_instance(_CONTEXT_NAME)

        await self.__wait_for_viewports(window.title, 1, [widget])

        return window, widget

    async def __wait_stage_loading(self, usd_context, wait_frames: int = 2, timeout: int = 1000):
        maxloops = timeout
        while True:
            _, files_loaded, total_files = usd_context.get_stage_loading_status()
            if not files_loaded and not total_files:
                break
            await ui_test.wait_n_updates()
            maxloops -= 1
            if maxloops == 0:
                self.fail(f"Timed out waiting for stage loading in context {usd_context.get_name()!r}")

        usd_context.reset_renderer_accumulation()
        for _ in range(wait_frames):
            await ui_test.wait_n_updates()

    async def __wait_widget_stage_loading(self, widget):
        await self.__wait_stage_loading(widget.viewport_api.usd_context)

    async def __wait_for_viewports(self, window_title: str, count: int, widgets):
        viewports = []
        all_viewports = []
        for _ in range(60):
            viewports = ui_test.find_all(f"{window_title}//Frame/**/.identifier == 'viewport'")
            if len(viewports) == count:
                return
            all_viewports = ui_test.find_all("**/.identifier == 'viewport'")
            await ui_test.wait_n_updates()
        widget_details = []
        for widget in widgets:
            viewport_frame = widget.viewport_frame()
            viewport_api = widget.viewport_api
            widget_details.append(
                (
                    widget.viewport_id,
                    viewport_api.usd_context_name,
                    viewport_api.updates_enabled,
                    widget.viewport_layers.viewport_widget.visible,
                    viewport_frame.computed_width,
                    viewport_frame.computed_height,
                )
            )
        self.fail(
            f"Expected {count} viewports in {window_title!r}; found {len(viewports)} scoped, "
            f"{len(all_viewports)} total; widgets={widget_details!r}"
        )

    async def __destroy(self, window, widgets):
        for widget in widgets:
            widget.destroy()
        window.destroy()

    def __count_snap_toolbar_groups(self) -> int:
        toolbar = _toolbar_module.get_instance()
        groups = list(getattr(toolbar, "_toolbar_widget_groups", []))
        count = 0
        for _priority, widget_group in groups:
            widget_type = type(widget_group)
            widget_name = f"{widget_type.__module__}.{widget_type.__name__}".lower()
            if "snap" in widget_name:
                count += 1
        return count

    async def test_always_one_vp_enabled(self):
        """Test global viewport events that ensure only one viewport is active."""

        # setup
        _window, _widgets = await self.__setup_widget()  # Keep in memory during test
        try:
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
        finally:
            await self.__destroy(_window, _widgets)

    async def test_deactivate_when_minimized(self):
        # setup
        carb.settings.get_settings().set("/app/renderer/skipWhileMinimized", True)
        _window, _widgets = await self.__setup_widget()  # Keep in memory during test
        app_window = omni.appwindow.get_default_app_window()
        minimize_event_stream = app_window.get_window_minimize_event_stream()
        viewports = ui_test.find_all(f"{_window.title}//Frame/**/.identifier == 'viewport'")
        try:
            # after clicking on viewport 1, it should be enabled
            await viewports[0].click()
            self.assertTrue(_widgets[0].viewport_api.updates_enabled is True)
            self.assertTrue(_widgets[1].viewport_api.updates_enabled is False)
            await self.__wait_widget_stage_loading(_widgets[0])

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
            await self.__wait_widget_stage_loading(_widgets[0])

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
            await self.__wait_widget_stage_loading(_widgets[1])
            minimize_event_stream.push(payload={"isMinimized": True})
            await ui_test.wait_n_updates()
            self.assertTrue(_widgets[0].viewport_api.updates_enabled is False)
            self.assertTrue(_widgets[1].viewport_api.updates_enabled is False)
            minimize_event_stream.push(payload={"isMinimized": False})
            await ui_test.wait_n_updates()
            self.assertTrue(_widgets[0].viewport_api.updates_enabled is False)
            self.assertTrue(_widgets[1].viewport_api.updates_enabled is True)
        finally:
            await self.__destroy(_window, _widgets)

    async def test_mouse_wheel_zoom_changes_active_viewport_camera(self):
        # Build the real shared viewport widgets with real USD stages so the event delegate is connected as it is in
        # app.
        window, widgets = await self.__setup_widget()
        try:
            viewports = ui_test.find_all(f"{window.title}//Frame/**/.identifier == 'viewport'")
            self.assertEqual(len(widgets), len(viewports))

            # Click the first viewport to make it active, then snapshot its active camera transform before scrolling.
            await self.__wait_widget_stage_loading(widgets[0])
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
        input_interface = carb.input.acquire_input_interface()
        key = carb.input.KeyboardInput.B
        key_is_down = False
        try:
            viewports = ui_test.find_all(f"{window.title}//Frame/**/.identifier == 'viewport'")
            self.assertEqual(len(widgets), len(viewports))

            # Activate the viewport and snapshot the camera before sending the key-held wheel event.
            await self.__wait_widget_stage_loading(widgets[0])
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
            self.assertTrue(input_interface.get_keyboard_value(keyboard, key))
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

    async def test_ctrl_t_triggers_teleport_picker_in_active_viewport(self):
        window, widget = await self.__setup_single_widget()
        context_manager = _get_context_manager()
        context_manager.get_usd_context(_TrexContext.STAGE_CRAFT)
        original_context = context_manager.get_current_context()
        original_request_query = _teleport_tool.viewport_api_request_query_hdremix
        requested_queries = []
        picked_position = (13.0, 17.0, 19.0)
        selected_prim_path = "/RootNode/meshes/mesh_BAC90CAA733B0859"

        try:
            viewports = ui_test.find_all(f"{window.title}//Frame/**/.identifier == 'viewport'")
            self.assertEqual(1, len(viewports))

            await self.__wait_widget_stage_loading(widget)
            await viewports[0].click()
            await ui_test.input.emulate_mouse_move(viewports[0].center)
            await ui_test.human_delay(human_delay_speed=2)
            self.assertTrue(widget.is_active())

            viewport_api = widget.viewport_api
            stage = viewport_api.stage
            selected_prim = stage.GetPrimAtPath(selected_prim_path)
            self.assertTrue(selected_prim.IsValid())

            def fake_request_query_hdremix(_pixel, callback, request_query_type):
                requested_queries.append(request_query_type)
                callback(selected_prim_path, picked_position, (0, 0))

            viewport_api.usd_context.get_selection().set_selected_prim_paths([selected_prim_path], True)
            self.assertEqual([selected_prim_path], viewport_api.usd_context.get_selection().get_selected_prim_paths())

            # Ctrl+T belongs to the active viewport. The hotkey should keep working even if another Trex pane last
            # set the app-level context.
            context_manager.set_current_context(_TrexContext.TEXTURE_CRAFT)
            _teleport_tool.viewport_api_request_query_hdremix = fake_request_query_hdremix

            await ui_test.emulate_keyboard_press(carb.input.KeyboardInput.T, carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL)
            await ui_test.human_delay(human_delay_speed=4)

            self.assertEqual(
                [_teleport_tool.RemixRequestQueryType.PATH_AND_WORLDPOS],
                requested_queries,
                "Ctrl+T did not trigger exactly the active viewport teleport picker",
            )
        finally:
            _teleport_tool.viewport_api_request_query_hdremix = original_request_query
            context_manager.set_current_context(original_context)
            await self.__destroy(window, [widget])

    async def test_snap_ui_available_by_default(self):
        _window, _widgets = await self.__setup_widget()  # Keep in memory during test
        settings = carb.settings.get_settings()
        try:
            self.assertFalse(settings.get("/exts/omni.kit.widget.toolbar/legacySnapButton/enabled"))
            self.assertFalse(settings.get("/exts/omni.kit.manipulator.prim.core/tools/enabled"))
            self.assertEqual(self.__count_snap_toolbar_groups(), 1)
        finally:
            await self.__destroy(_window, _widgets)

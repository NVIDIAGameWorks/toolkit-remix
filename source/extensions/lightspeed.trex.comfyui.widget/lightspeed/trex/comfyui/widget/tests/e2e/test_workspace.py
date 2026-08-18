"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

import time
from unittest.mock import patch

import omni.usd
from carb.input import KeyboardInput
from lightspeed.events_manager import get_instance as get_event_manager_instance
from lightspeed.trex.comfyui.core.core import ComfyUICore
from lightspeed.trex.comfyui.core.enums import ComfyUIState
from lightspeed.trex.comfyui.widget.setup.widget import ComfySetupAdvancedWidget
from lightspeed.trex.comfyui.widget.workspace import ComfySetupWorkspace
from lightspeed.trex.utils.widget.quicklayout import LAYOUT_LOADED_EVENT_NAME, subscribe_layout_loaded
from omni import ui
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase

# USD context that only this test owns, so its core and its stage cannot reach another test.
_CONTEXT_NAME = "comfyui_workspace_e2e"
# Port that refuses every connection, so a connection attempt fails without a server.
_CLOSED_PORT = 9
# Window size of a narrow, tall column, where a long message wraps and the panel keeps space over.
_NARROW_WIDTH = 320
_WIDE_WIDTH = 700
_TALL_HEIGHT = 400
# Seconds that a refused connection may need, including the retries of the request library.
_CONNECT_TIMEOUT = 30.0
# Size that the workspace gives a floating window, from `ComfySetupWorkspace`.
_DEFAULT_WIDTH = ComfySetupWorkspace._DEFAULT_WIDTH
_DEFAULT_HEIGHT = ComfySetupWorkspace._DEFAULT_HEIGHT


class _TestSetupWorkspace(ComfySetupWorkspace):
    """Setup workspace under a unique title.

    The extension registers its own "ComfyUI Setup" window, so a shared title would let a widget query
    match that window instead of the one the test built.
    """

    @property
    def title(self) -> str:
        """Return the unique test window title.

        Returns:
            Title that only this workspace uses.
        """
        return "ComfyUI Setup Geometry Test"


class TestComfySetupWorkspaceE2E(AsyncTestCase):
    """Test the real setup window and the real panel against the real ComfyUI core."""

    def _create_core(self) -> ComfyUICore:
        """Create a real core of a USD context that only this test owns.

        The core is the real one, and the test builds it directly: the factory of the extension caches every
        core that it builds, and a core of a context that no longer exists must leave no entry there. The
        panel looks its core up through that factory, so the lookup returns this core while the test runs.

        Returns:
            Core that the setup panel of this test drives.
        """
        omni.usd.get_context(_CONTEXT_NAME) or omni.usd.create_context(_CONTEXT_NAME)
        core = ComfyUICore(_CONTEXT_NAME)
        self.addCleanup(omni.usd.destroy_context, _CONTEXT_NAME)
        self.addCleanup(core.destroy)
        self.addCleanup(core.settings.set_port, core.settings.port)
        lookup = patch(
            "lightspeed.trex.comfyui.widget.setup.widget.get_comfyui_core_instance",
            return_value=core,
        )
        lookup.start()
        self.addCleanup(lookup.stop)
        return core

    async def _create_window(self) -> tuple[_TestSetupWorkspace, ui.Window, ComfySetupAdvancedWidget]:
        """Show the setup window of the test context.

        Returns:
            Workspace, the window that it created, and the panel inside that window.
        """
        workspace = _TestSetupWorkspace(_CONTEXT_NAME)
        self.addCleanup(workspace.cleanup)
        workspace.create_window()
        workspace.show_window_fn(True)
        await ui_test.wait_n_updates(6)
        return workspace, workspace.get_window(), workspace._content

    def _find(self, window: ui.Window, widget_type: str, identifier: str):
        """Find one widget of the setup panel.

        Args:
            window: Window that holds the panel.
            widget_type: omni.ui type name of the widget.
            identifier: Identifier that the panel gives the widget.

        Returns:
            Widget reference that reports its position and size.
        """
        return ui_test.find(f"{window.title}//Frame/**/{widget_type}[*].identifier=='{identifier}'")

    async def test_a_wrapped_connection_message_asks_for_a_taller_panel(self):
        """A user who cannot reach the server reads the whole message, and the button stays inside the panel."""
        core = self._create_core()
        workspace, window, setup_panel = await self._create_window()
        self.assertIsInstance(window, ui.Window)

        # The user types a port that no server listens on, then selects Connect. The panel reports the
        # refused connection to the log, and the test captures that report.
        port = self._find(window, "IntField", "ComfySetupPort")
        await port.input(str(_CLOSED_PORT), end_key=KeyboardInput.ENTER)
        connect = self._find(window, "Button", "ComfySetupConnect")
        with patch("lightspeed.trex.comfyui.widget.setup.widget.carb.log_error") as log_error:
            await connect.click()
            # The refused connection needs the time of the request, and a headless frame is fast, so the
            # test waits on the clock.
            deadline = time.monotonic() + _CONNECT_TIMEOUT
            while core.state != ComfyUIState.ERROR and time.monotonic() < deadline:
                await ui_test.human_delay(5)
        self.assertEqual(core.state, ComfyUIState.ERROR)
        self.assertEqual(core.settings.port, _CLOSED_PORT)
        self.assertIn(f"port={_CLOSED_PORT}", log_error.call_args[0][0])

        # A wide window shows the failure message in few lines.
        window.width = _WIDE_WIDTH
        window.height = _TALL_HEIGHT
        await ui_test.wait_n_updates(8)
        wide_height = setup_panel.needed_height
        self.assertGreater(wide_height, 0)

        # A narrow window, as a docked column is, wraps the same message in more lines. The panel then needs
        # more height, which is the height that its window asks its dock for.
        window.width = _NARROW_WIDTH
        await ui_test.wait_n_updates(8)
        self.assertGreater(setup_panel.needed_height, wide_height)

        # The Retry button stays inside the panel.
        panel = self._find(window, "Rectangle", "ComfySetupContent")
        connect = self._find(window, "Button", "ComfySetupConnect")
        panel_bottom = panel.center.y + (panel.size.y / 2)
        self.assertLessEqual(connect.center.y + (connect.size.y / 2), panel_bottom + 1)

    async def test_a_taller_window_keeps_the_connect_button_at_the_bottom(self):
        """A user who makes the window taller sees the panel fill it, and Connect stays at the bottom."""
        self._create_core()
        workspace, window, setup_panel = await self._create_window()

        # The panel fills the window it opens in, and it needs every point of that height.
        needed_height = setup_panel.needed_height
        panel = self._find(window, "Rectangle", "ComfySetupContent")
        short_panel_height = panel.size.y

        # The user makes the window twice as tall.
        window.height = window.height * 2
        await ui_test.wait_n_updates(8)

        # The panel grew with the window, and it still needs the same height for its rows.
        panel = self._find(window, "Rectangle", "ComfySetupContent")
        self.assertGreater(panel.size.y, short_panel_height)
        self.assertAlmostEqual(setup_panel.needed_height, needed_height, delta=1)

        # The Connect button sits at the bottom of the panel, not in the middle of it.
        connect = self._find(window, "Button", "ComfySetupConnect")
        panel_bottom = panel.center.y + (panel.size.y / 2)
        connect_bottom = connect.center.y + (connect.size.y / 2)
        self.assertLessEqual(connect_bottom, panel_bottom + 1)
        self.assertGreater(connect_bottom, panel_bottom - short_panel_height)

    async def test_a_layout_load_asks_the_window_to_fit_again(self):
        """A layout load replaces the geometry of every window, so the setup window fits its panel again."""
        self._create_core()
        _workspace, window, _setup_panel = await self._create_window()

        # The window floats, because the test application docks no window. It opens at the size of the panel
        # and keeps it, and a floating window is the one case that needs that size: no dock supplies one.
        self.assertEqual((window.width, window.height), (_DEFAULT_WIDTH, _DEFAULT_HEIGHT))
        height = window.height

        # A layout load reaches every subscriber of the shared event.
        loaded = []
        _subscription = subscribe_layout_loaded(lambda: loaded.append(True))
        get_event_manager_instance().call_global_custom_event(LAYOUT_LOADED_EVENT_NAME)
        await ui_test.wait_n_updates(8)

        # The window asked for the fit, and it kept its size because no dock holds it.
        self.assertEqual(len(loaded), 1)
        self.assertEqual(window.height, height)

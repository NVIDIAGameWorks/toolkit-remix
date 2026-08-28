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

import omni.ui as ui
from lightspeed.common.constants import WindowNames as _WindowNames
from lightspeed.trex.app.setup.lifecycle import is_user_ready as _is_user_ready
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase


class TestStartupChain(AsyncTestCase):
    """Exercise the normal StageCraft startup chain in an isolated process."""

    async def test_normal_startup_reaches_interactive_home(self):
        """Show a docked Home window whose primary actions are usable at USER_READY."""
        for _ in range(300):
            if _is_user_ready():
                break
            await ui_test.wait_n_updates(1)
        else:
            self.fail("StageCraft startup did not publish USER_READY")

        home_window = ui.Workspace.get_window(_WindowNames.HOME_PAGE)
        self.assertIsNotNone(home_window)
        self.assertTrue(home_window.visible)
        self.assertTrue(home_window.docked)

        for action in ("New", "Open"):
            control = ui_test.find(f"{_WindowNames.HOME_PAGE}//Frame/**/Button[*].text=='{action}'")
            self.assertIsNotNone(control)
            self.assertTrue(control.widget.enabled)

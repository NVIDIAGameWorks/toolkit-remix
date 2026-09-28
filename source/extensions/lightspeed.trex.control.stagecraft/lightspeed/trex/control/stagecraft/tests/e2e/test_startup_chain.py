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

from pathlib import Path

import omni.ui as ui
import omni.usd
from lightspeed.common.constants import WindowNames as _WindowNames
from lightspeed.trex.app.setup.lifecycle import is_user_ready as _is_user_ready
from omni.flux.utils.tests.context_managers import open_test_project
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase

_STARTUP_UPDATE_BUDGET = 300
_INGESTION_UPDATE_BUDGET = 600


class TestStartupChain(AsyncTestCase):
    """Exercise the normal StageCraft startup chain in an isolated process."""

    async def test_project_user_can_open_ingestion_workspace_on_first_click(self):
        """Open a project and enter Ingestion on the first sidebar click."""
        for _ in range(_STARTUP_UPDATE_BUDGET):
            if _is_user_ready():
                break
            await ui_test.wait_n_updates(1)
        else:
            self.fail("StageCraft startup did not publish USER_READY")

        async with open_test_project(
            "usd/project_example/combined.usda", "lightspeed.trex.app.resources"
        ) as project_url:
            # The normal StageCraft sidebar must expose Ingestion after the project opens.
            context = omni.usd.get_context("")
            stage = context.get_stage()
            self.assertIsNotNone(stage)
            self.assertEqual(Path(stage.GetRootLayer().realPath).resolve(), Path(project_url.path).resolve())
            button = ui_test.find(f"{_WindowNames.SIDEBAR}//Frame/**/Image[*].name=='Ingestion'")
            self.assertIsNotNone(button)
            self.assertEqual(button.widget.tooltip, "Asset Import/Ingestion")

            # One user click must finish lazy activation and show the Ingestion workspace.
            await button.click()
            await ui_test.human_delay()
            for _ in range(_INGESTION_UPDATE_BUDGET):
                ingestion_window = ui.Workspace.get_window(_WindowNames.INGESTCRAFT)
                if (
                    ingestion_window is not None
                    and ingestion_window.visible
                    and ui.Inspector.get_children(ingestion_window.frame)
                ):
                    break
                await ui_test.wait_n_updates(1)
            else:
                self.fail("Ingestion workspace did not become visible with populated content after the first click")

    async def test_normal_startup_reaches_interactive_home(self):
        """Show a docked Home window whose primary actions are usable at USER_READY."""
        for _ in range(_STARTUP_UPDATE_BUDGET):
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

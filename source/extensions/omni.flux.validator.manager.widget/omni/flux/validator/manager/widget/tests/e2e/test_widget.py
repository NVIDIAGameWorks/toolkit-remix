# ruff: noqa: ARG001
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

from __future__ import annotations

import asyncio
import sys
from unittest.mock import patch

import omni.ui as ui
from omni.flux.validator.manager.core import ManagerCore as _ManagerCore
from omni.flux.validator.manager.widget import ValidatorManagerWidget as _ValidatorManagerWidget
from omni.flux.validator.plugin.check.usd.example.print_prims import PrintPrims as _PrintPrims
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows, get_test_data_path, open_stage


def _create_schema():
    return _ManagerCore(
        {
            "name": "Test",
            "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
            "check_plugins": [
                {
                    "name": "PrintPrims",
                    "enabled": False,
                    "selector_plugins": [{"name": "AllPrims", "data": {}}],
                    "context_plugin": {"name": "CurrentStage", "data": {}},
                    "data": {},
                },
                {
                    "name": "PrintPrims",
                    "selector_plugins": [{"name": "AllPrims", "data": {}}],
                    "data": {},
                    "context_plugin": {"name": "CurrentStage", "data": {}},
                },
                {
                    "name": "PrintPrims",
                    "selector_plugins": [{"name": "AllPrims", "data": {}}],
                    "data": {},
                    "context_plugin": {"name": "CurrentStage", "data": {}},
                },
            ],
        }
    )


class TestManagerWidget(AsyncTestCase):
    # Before running each test
    async def setUp(self):
        await arrange_windows()
        await open_stage(get_test_data_path(__name__, "usd/cubes.usda"))

    # After running each test
    async def tearDown(self):
        pass

    async def __setup_widget(self, name):
        _core = _create_schema()
        window = ui.Window(f"TestValidationUI{name}", height=800, width=400)
        with window.frame:
            wid = _ValidatorManagerWidget(core=_core)

        await ui_test.human_delay(human_delay_speed=1)

        return window, _core, wid

    async def __destroy_setup(self, window, core, wid):
        await ui_test.human_delay(human_delay_speed=1)
        wid.destroy()
        window.frame.clear()
        window.destroy()

        await ui_test.human_delay(human_delay_speed=1)

    async def test_before_run_button(self):
        # setup
        window, _core, _wid = await self.__setup_widget("test_before_run_button")  # Keep in memory during test

        # grab the buttons
        run_button = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='run_validation'")
        run_progress = ui_test.find(f"{window.title}//Frame/**/ProgressBar[*].identifier=='run_validation'")
        plugin_titles = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='plugin_title'")

        # test before the run
        self.assertIsNotNone(run_button)
        self.assertIsNotNone(run_progress)
        self.assertIsNotNone(plugin_titles)

        self.assertEqual(run_progress.widget.model.get_value_as_float(), 0)
        self.assertEqual(len(plugin_titles), 3)  # because we have 3 check plugins and we didnt expand them

        await self.__destroy_setup(window, _core, _wid)

    async def test_before_run_button_selection_plugin(self):
        # setup
        window, _core, _wid = await self.__setup_widget(
            "test_before_run_button_selection_plugin"
        )  # Keep in memory during test

        # grab the buttons
        expand_checks = ui_test.find_all(f"{window.title}//Frame/**/Image[*].identifier=='expand_plugin'")
        plugin_titles = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='plugin_title'")

        self.assertEqual(len(plugin_titles), 3)  # 3 check plugins
        self.assertEqual(len(expand_checks), 3)  # because we have 3 check plugins and we didnt expand them

        # expand the first check plugin
        await expand_checks[0].click()

        # now we should have 5 plugin titles: 3 checks + 1 selector + 1 context
        expand_checks = ui_test.find_all(f"{window.title}//Frame/**/Image[*].identifier=='expand_plugin'")
        plugin_titles = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='plugin_title'")
        self.assertEqual(len(plugin_titles), 5)
        self.assertEqual(len(expand_checks), 5)

        await self.__destroy_setup(window, _core, _wid)

    async def test_after_run_button(self):
        finished = False

        def _on_run_finished(result, message: str | None = None):
            nonlocal finished
            # test after the run
            self.assertEqual(run_progress.widget.model.get_value_as_float(), 1.0)
            self.assertTrue(result)
            finished = True

        # setup
        window, _core, _wid = await self.__setup_widget("test_after_run_button")  # Keep in memory during test

        # grab the buttons and set the sub
        run_button = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='run_validation'")
        run_progress = ui_test.find(f"{window.title}//Frame/**/ProgressBar[*].identifier=='run_validation'")
        _ = _core.subscribe_run_finished(_on_run_finished)

        await run_button.click()
        while not finished:
            await ui_test.human_delay(human_delay_speed=1)
        await self.__destroy_setup(window, _core, _wid)

    async def test_expand_sub_context_plugin(self):
        # setup
        window, _core, _wid = await self.__setup_widget("test_expand_sub_context_plugin")  # Keep in memory during test

        # grab the buttons and set the sub
        expand_plugins = ui_test.find_all(f"{window.title}//Frame/**/Image[*].identifier=='expand_plugin'")
        self.assertIsNotNone(expand_plugins)
        await expand_plugins[0].click()  # expand first check

        expand_plugins = ui_test.find_all(f"{window.title}//Frame/**/Image[*].identifier=='expand_plugin'")
        self.assertIsNotNone(expand_plugins)
        await expand_plugins[1].click()  # expand first context
        await expand_plugins[2].click()  # expand first context

        await self.__destroy_setup(window, _core, _wid)

    async def test_right_click_menu(self):
        # setup
        window, _core, _wid = await self.__setup_widget("test_right_click_menu")  # Keep in memory during test

        # grab the buttons and set the sub
        expand_plugins = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='plugin_title'")
        await expand_plugins[1].click()
        await ui_test.human_delay()

        self.assertIsNotNone(expand_plugins)

        await expand_plugins[1].right_click()
        await ui_test.human_delay()
        await ui_test.select_context_menu("Re-run all")

        await ui_test.human_delay()
        await expand_plugins[1].click()
        await expand_plugins[1].click()
        await ui_test.human_delay()
        await expand_plugins[1].right_click()
        await ui_test.human_delay()
        await ui_test.select_context_menu("Re-run context + selected item(s)")

        await ui_test.human_delay()
        await expand_plugins[1].click()
        await expand_plugins[1].click()
        await ui_test.human_delay()
        await expand_plugins[1].right_click()
        await ui_test.human_delay()
        await ui_test.select_context_menu("Re-run context + from selected item(s) to last item")
        await ui_test.human_delay()

        await self.__destroy_setup(window, _core, _wid)

    async def test_run_pause_resume(self):
        finished = False

        def _on_run_finished(result, message: str | None = None):
            nonlocal finished
            # test after the run
            self.assertEqual(run_progress.widget.model.get_value_as_float(), 1.0)
            self.assertTrue(result)
            finished = True

        # setup
        window, _core, _wid = await self.__setup_widget("test_run_pause_resume")  # Keep in memory during test

        # grab the buttons and set the sub
        run_button = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='run_validation'")
        run_progress = ui_test.find(f"{window.title}//Frame/**/ProgressBar[*].identifier=='run_validation'")

        resume_frame = ui_test.find(f"{window.title}//Frame/**/Frame[*].identifier=='resume_validation'")
        self.assertIsNotNone(resume_frame)
        self.assertFalse(resume_frame.widget.visible)

        _ = _core.subscribe_run_finished(_on_run_finished)

        with patch.object(_PrintPrims, "_check") as m_mocked, patch.object(_PrintPrims, "_fix") as m_mocked2:
            v1 = (False, "Failed", None)
            if sys.version_info.minor > 7:
                m_mocked.return_value = v1
            else:
                f = asyncio.Future()
                f.set_result(v1)
                m_mocked.return_value = f

            v2 = (True, "Ok", None)
            if sys.version_info.minor > 7:
                m_mocked2.return_value = v2
            else:
                f = asyncio.Future()
                f.set_result(v2)
                m_mocked2.return_value = f

            await run_button.click()

        self.assertTrue(resume_frame.widget.visible)
        await resume_frame.click()
        while not finished:
            await ui_test.human_delay(human_delay_speed=1)
        await self.__destroy_setup(window, _core, _wid)

    async def test_run_stop(self):
        finished = False

        def _on_run_finished(_result, message: str | None = None):
            nonlocal finished
            # test after the run
            finished = True

        # setup
        window, _core, _wid = await self.__setup_widget("test_run_pause_resume")  # Keep in memory during test

        # grab the buttons and set the sub
        run_button = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='run_validation'")
        stop_button = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='stop_validation'")

        _ = _core.subscribe_run_finished(_on_run_finished)

        with patch.object(_PrintPrims, "_check") as m_mocked, patch.object(_PrintPrims, "_fix") as m_mocked2:
            v1 = (False, "Failed", None)
            if sys.version_info.minor > 7:
                m_mocked.return_value = v1
            else:
                f = asyncio.Future()
                f.set_result(v1)
                m_mocked.return_value = f

            v2 = (True, "Ok", None)
            if sys.version_info.minor > 7:
                m_mocked2.return_value = v2
            else:
                f = asyncio.Future()
                f.set_result(v2)
                m_mocked2.return_value = f

            with self.assertRaises(ValueError):
                _core.set_force_ignore_exception(True)
                await run_button.click()
                await ui_test.human_delay()
                await stop_button.click()
                await ui_test.human_delay()
                await asyncio.gather(_core._last_run_task)
                _core.set_force_ignore_exception(False)

        while not finished:
            await ui_test.human_delay(human_delay_speed=1)
        await self.__destroy_setup(window, _core, _wid)

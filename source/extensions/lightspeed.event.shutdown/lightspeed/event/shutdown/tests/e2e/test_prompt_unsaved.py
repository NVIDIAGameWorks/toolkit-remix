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

import tempfile
from pathlib import Path
from typing import Callable
from unittest.mock import Mock, patch

import lightspeed.event.shutdown.unsaved_stage
import omni.kit.app
import omni.usd
from carb.settings import ISettings
from lightspeed.events_manager import get_instance as _get_event_manager_instance
from lightspeed.layer_manager.core import LayerManagerCore
from lightspeed.trex.control.stagecraft import get_instance as _get_control_stagecraft
from lightspeed.trex.layout.stagecraft import get_instance as _get_stagecraft_layout
from omni.flux.utils.widget.resources import get_test_data as _get_test_data
from omni.kit.test.async_unittest import AsyncTestCase
from omni.kit.test_suite.helpers import open_stage, wait_stage_loading
from omni.kit.window.file import FileWindowExtension


class MockEvent:
    type = omni.kit.app.POST_QUIT_EVENT_TYPE  # noqa A003 shadowing builtin name


def mock_prompt(response="ok"):
    """
    Return a mock prompt class that will trigger the callable associated with a particular button
    """

    class MockPrompt:
        """Mock for `lightspeed.trex.utils.widget.TrexMessageDialog`"""

        call_count = 0

        def __init__(
            self,
            message: str,
            title: str = "",
            ok_handler: Callable | None = None,
            middle_handler: Callable | None = None,
            middle_2_handler: Callable | None = None,
            cancel_handler: Callable | None = None,
            **kwargs,
        ):
            if title != "Save Project?":
                raise ValueError("Another prompt was unintentionally triggerred and mocked.")
            self.__class__.call_count += 1

            match response:
                case "ok" if ok_handler:
                    ok_handler()
                case "middle" if middle_handler:
                    middle_handler()
                case "middle_2" if middle_2_handler:
                    middle_2_handler()
                case "cancel" if cancel_handler:
                    cancel_handler()
                case _:
                    pass

        @classmethod
        def assert_called_once(cls):
            assert cls.call_count == 1, f"Prompt was triggered {cls.call_count} times. Expected 1."

        @classmethod
        def assert_not_called(cls):
            assert cls.call_count == 0, f"Prompt was triggered {cls.call_count} times."

    return MockPrompt


class TrexTestPromptIfUnsavedStage(AsyncTestCase):
    async def setUp(self):
        # get a test usd path in a temporary dir to make sure anything saved is cleaned up
        self._temp_dir = tempfile.TemporaryDirectory()  # noqa PLR1732
        self._temp_path = (Path(self._temp_dir.name) / "test.usda").as_posix()

        self._stagecraft = _get_stagecraft_layout()
        self._context = self._stagecraft._context  # noqa PLW0212 protected-access

        # mocked carb setting
        self._trex_ignore_unsaved_stage_on_exit = False

        # open something so that context can be set as dirty
        await open_stage(_get_test_data("usd/project_example/combined.usda"))

    # After running each test
    async def tearDown(self):
        await wait_stage_loading()
        self._temp_dir = None

    def _mock_get_carb_setting(self, setting: str):
        from lightspeed.event.shutdown.unsaved_stage import TREX_IGNORE_UNSAVED_STAGE_ON_EXIT

        if setting == TREX_IGNORE_UNSAVED_STAGE_ON_EXIT:
            return self._trex_ignore_unsaved_stage_on_exit
        return False

    async def test_open_new_file_with_unsaved_stage(self):
        self._context.set_pending_edit(True)

        with (
            patch.object(ISettings, "get", side_effect=self._mock_get_carb_setting),
            # This simulates showing prompt and clicking don't save
            # Note: keep this in sync with `lightspeed.trex.stagecraft.control.Setup._prompt_if_unsaved_project()`
            patch("lightspeed.trex.control.stagecraft.setup._TrexMessageDialog", mock_prompt("middle_2")) as prompt,
            patch.object(LayerManagerCore, "open_stage"),
        ):
            # opening a new project should ask if we want to save our work
            self._stagecraft._open_work_file(self._temp_path)  # noqa PLW0212 protected-access

        prompt.assert_called_once()

    async def test_unload_with_unsaved_stage(self):
        # Open a project and flag that there is a pending edit
        self._context.set_pending_edit(True)

        with (
            patch.object(ISettings, "get", side_effect=self._mock_get_carb_setting),
            # This simulates showing prompt and clicking don't save
            # Note: keep this in sync with `lightspeed.trex.stagecraft.control.Setup._prompt_if_unsaved_project()`
            patch("lightspeed.trex.control.stagecraft.setup._TrexMessageDialog", mock_prompt("middle_2")) as prompt,
            patch.object(LayerManagerCore, "create_new_stage"),
        ):
            # unloading the current stage should ask if we want to save our work
            _get_control_stagecraft()._on_new_workfile()  # noqa PLW0212 protected-access

        prompt.assert_called_once()

    async def test_no_prompt_if_no_pending_edit(self):
        self._context.set_pending_edit(False)

        with (
            patch.object(ISettings, "get", side_effect=self._mock_get_carb_setting),
            patch("lightspeed.trex.control.stagecraft.setup._TrexMessageDialog", mock_prompt("middle_2")) as prompt,
            patch.object(LayerManagerCore, "open_stage"),
        ):
            self._stagecraft._open_work_file(self._temp_path)  # noqa PLW0212 protected-access

        prompt.assert_not_called()

    async def test_open_new_file_will_show_prompt_but_can_click_dont_save(self):
        self._context.set_pending_edit(True)

        with (
            patch.object(ISettings, "get", side_effect=self._mock_get_carb_setting),
            # This simulates showing prompt and clicking "don't save"
            patch("lightspeed.trex.control.stagecraft.setup._TrexMessageDialog", mock_prompt("middle_2")) as prompt,
            patch.object(FileWindowExtension, "save") as mock_file_save,
            patch.object(LayerManagerCore, "open_stage"),
        ):
            self._stagecraft._open_work_file(self._temp_path)  # noqa PLW0212 protected-access

        prompt.assert_called_once()
        mock_file_save.assert_not_called()

    async def test_shutdown_will_show_prompt_and_save(self):
        self._context.set_pending_edit(True)

        mock_shutdown_callable = Mock()

        with (
            patch.object(ISettings, "get", side_effect=self._mock_get_carb_setting),
            # This simulates showing prompt and clicking save
            patch("lightspeed.trex.control.stagecraft.setup._TrexMessageDialog", mock_prompt("ok")) as prompt,
            patch.object(FileWindowExtension, "save", side_effect=mock_shutdown_callable) as mock_file_save,
        ):
            # We can't actually shut down the app or the test will not be able to finish. We call the next best thing,
            # and simulate a close action with a fake shutdown callable.
            # omni.kit.app.get_app().shutdown()  # closes too fast.
            # app_window = omni.appwindow.get_default_app_window().shutdown()  # this crashes
            _get_control_stagecraft().interrupt_shutdown(mock_shutdown_callable)

        prompt.assert_called_once()
        mock_file_save.assert_called_once()
        mock_shutdown_callable.assert_called_once()

    async def test_shutdown_no_prompt_if_ignore_on_exit_setting_is_true(self):
        self._context.set_pending_edit(True)
        self._trex_ignore_unsaved_stage_on_exit = True

        with (
            patch.object(ISettings, "get", side_effect=self._mock_get_carb_setting),
            patch("lightspeed.trex.control.stagecraft.setup._TrexMessageDialog", mock_prompt("middle_2")) as prompt,
        ):

            # Simulate close event even closer to actual event handling in order to
            # test the effect of the preference.
            event_name = lightspeed.event.shutdown.unsaved_stage.EventUnsavedStageOnShutdown().name
            event = _get_event_manager_instance().get_registered_event(event_name)
            # XXX: call private "slot" method on event as if it was triggered.
            event._EventUnsavedStageOnShutdown__on_shutdown_event(MockEvent)  # noqa PLW0212 protected-access

        prompt.assert_not_called()

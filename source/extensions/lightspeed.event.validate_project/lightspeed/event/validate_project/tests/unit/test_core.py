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

import asyncio
import contextlib
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import omni.kit.app
import omni.usd
from lightspeed.event.validate_project.core import EventValidateProjectCore
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.layer_manager.core.data_models import LayerType as _LayerType
from omni.kit.test import AsyncTestCase
from pxr import Usd


@contextlib.asynccontextmanager
async def make_temp_directory(context):
    temp_dir = tempfile.TemporaryDirectory()
    try:
        yield temp_dir
    finally:
        if context.can_close_stage():
            await context.close_stage_async()
        temp_dir.cleanup()


class TestValidateProjectCore(AsyncTestCase):
    """Test deferred project validation and existing validation repairs."""

    async def setUp(self):
        self._layer_manager = _LayerManagerCore()

    async def tearDown(self):
        pass

    async def test_schedule_validation_reuses_pending_task(self):
        """Keep one pending validation task while more events arrive."""
        # Arrange
        core = EventValidateProjectCore.__new__(EventValidateProjectCore)
        pending_task = MagicMock()
        core._validation_task = pending_task

        with patch("lightspeed.event.validate_project.core.asyncio.ensure_future") as ensure_future_mock:
            # Act
            core._EventValidateProjectCore__schedule_validation()

        # Assert
        self.assertIs(pending_task, core._validation_task)
        ensure_future_mock.assert_not_called()

    async def test_scheduled_validation_runs_after_one_update(self):
        """Run deferred project validation after one application update."""
        # Arrange
        core = EventValidateProjectCore.__new__(EventValidateProjectCore)
        core._validation_task = asyncio.current_task()
        order = []
        app = MagicMock()
        app.next_update_async = AsyncMock(side_effect=lambda: order.append("update"))
        core._EventValidateProjectCore__validate_project = MagicMock(side_effect=lambda: order.append("validate"))

        with patch("lightspeed.event.validate_project.core.omni.kit.app.get_app", return_value=app):
            # Act
            await core._EventValidateProjectCore__validate_project_next_update()

        # Assert
        self.assertEqual(["update", "validate"], order)
        self.assertIsNone(core._validation_task)

    async def test_anonymous_startup_stage_is_ignored_silently(self):
        """Do not validate the anonymous stage used before a project opens."""
        # Arrange
        core = EventValidateProjectCore.__new__(EventValidateProjectCore)
        stage = MagicMock()
        stage.GetRootLayer.return_value.anonymous = True
        core._context = MagicMock()
        core._context.get_stage.return_value = stage
        core._EventValidateProjectCore__layer_manager = MagicMock()

        # Act
        core._EventValidateProjectCore__validate_project()

        # Assert
        core._EventValidateProjectCore__layer_manager.get_layer_of_type.assert_not_called()

    async def test_uninstall_cancels_pending_validation(self):
        """Cancel pending validation when the event owner uninstalls."""
        # Arrange
        core = EventValidateProjectCore.__new__(EventValidateProjectCore)
        core._stage_event_sub = MagicMock()
        core._layer_event_sub = MagicMock()
        validation_task = MagicMock()
        core._validation_task = validation_task

        # Act
        core._uninstall()

        # Assert
        validation_task.cancel.assert_called_once_with()
        self.assertIsNone(core._validation_task)

    async def test_unresolvable_capture_sublayer_does_not_raise(self):
        """Validate that an unresolvable capture sublayer path logs a warning instead of raising."""
        context = omni.usd.get_context()
        async with make_temp_directory(context) as temp_dir:
            stage = Usd.Stage.CreateNew(f"{temp_dir.name}/project.usd")
            await context.attach_stage_async(stage)

            project_layer = stage.GetRootLayer()
            self._layer_manager.set_custom_data_layer_type(project_layer, _LayerType.workfile)

            # Create a real mod layer
            stage_mod = Usd.Stage.CreateNew(f"{temp_dir.name}/mod.usd")
            layer_mod = stage_mod.GetRootLayer()
            self._layer_manager.set_custom_data_layer_type(layer_mod, _LayerType.replacement)
            project_layer.subLayerPaths.insert(0, layer_mod.identifier)

            # Create a real capture layer on disk
            stage_capture = Usd.Stage.CreateNew(f"{temp_dir.name}/capture.usd")
            layer_capture = stage_capture.GetRootLayer()
            self._layer_manager.set_custom_data_layer_type(layer_capture, _LayerType.capture)

            # Insert capture sublayer with a path that CANNOT be resolved on disk.
            # This simulates the scenario from issue #384 where the capture path
            # points to a non-existent location.
            project_layer.subLayerPaths.insert(1, "./nonexistent/path/capture.usd")

            await omni.kit.app.get_app().next_update_async()

            core = EventValidateProjectCore()
            core._install()

            # Trigger validation — should not raise AttributeError on None.identifier
            core._EventValidateProjectCore__validate_project()

            core._uninstall()
            core.destroy()

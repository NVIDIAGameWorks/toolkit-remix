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

import tempfile
from pathlib import Path

import omni.client
import omni.kit.app
import omni.kit.test
import omni.usd
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.layer_manager.core import LayerType as _LayerType
from lightspeed.trex.capture.core.shared import Setup as _CaptureCoreSetup
from pxr import Usd


class TestOnLoadEvent(omni.kit.test.AsyncTestCase):
    async def setUp(self):
        pass

    async def tearDown(self):
        pass

    async def test_on_load_event_sets_directory_from_capture_layer(self):
        """When a capture layer is present on OPENED, __directory is derived from its realPath."""
        layer_manager = _LayerManagerCore()
        context = omni.usd.get_context()

        stage = Usd.Stage.CreateInMemory("test_dir.usd")
        await context.attach_stage_async(stage)

        stage_replacement = Usd.Stage.CreateInMemory("replacement_dir.usd")
        layer_replacement = stage_replacement.GetRootLayer()
        layer_manager.set_custom_data_layer_type(layer_replacement, _LayerType.replacement)
        stage.GetRootLayer().subLayerPaths.insert(0, layer_replacement.identifier)

        stage_capture = Usd.Stage.CreateInMemory("capture_dir.usd")
        layer_capture = stage_capture.GetRootLayer()
        layer_manager.set_custom_data_layer_type(layer_capture, _LayerType.capture)
        stage.GetRootLayer().subLayerPaths.insert(1, layer_capture.identifier)

        core = _CaptureCoreSetup("")
        # Fire a simulated OPENED event so __on_load_event runs
        context.get_stage_event_stream().push(int(omni.usd.StageEventType.OPENED))
        await omni.kit.app.get_app().next_update_async()

        expected_dir = omni.client.normalize_url(layer_capture.identifier).rsplit("/", 1)[0]
        self.assertEqual(core.get_directory(), expected_dir)

    async def test_on_load_event_sets_directory_from_project_structure_when_no_capture(self):
        """When there is no capture layer on OPENED, __directory falls back to project_dir/deps/captures."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Build a minimal on-disk project structure: project.usda + deps/captures/
            project_dir = Path(tmpdir) / "my_project"
            project_dir.mkdir()
            captures_dir = project_dir / "deps" / "captures"
            captures_dir.mkdir(parents=True)
            project_file = project_dir / "project.usda"

            stage = Usd.Stage.CreateNew(str(project_file))
            layer_manager = _LayerManagerCore()
            layer_manager.set_custom_data_layer_type(stage.GetRootLayer(), _LayerType.workfile)
            stage.Save()

            context = omni.usd.get_context()
            await context.open_stage_async(str(project_file))
            await omni.kit.app.get_app().next_update_async()

            core = _CaptureCoreSetup("")
            context.get_stage_event_stream().push(int(omni.usd.StageEventType.OPENED))
            await omni.kit.app.get_app().next_update_async()

            self.assertIsNotNone(core.get_directory())
            self.assertIn("captures", core.get_directory())

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

import omni.usd
from omni.flux.validator.manager.core import ManagerCore as _ManagerCore
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows, get_test_data_path, open_stage, wait_stage_loading
from pxr import Sdf


class TestDefaultPrim(AsyncTestCase):
    async def setUp(self):
        await arrange_windows()

    # After running each test
    async def tearDown(self):
        await wait_stage_loading()

    def _make_core(self):
        return _ManagerCore(
            {
                "name": "Test",
                "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                "check_plugins": [
                    {
                        "name": "DefaultPrim",
                        "selector_plugins": [{"name": "Nothing", "data": {}}],
                        "data": {},
                        "context_plugin": {"name": "DependencyIterator", "data": {}},
                        "pause_if_fix_failed": False,
                    }
                ],
            }
        )

    async def test_run_no_fix(self):
        # Arrange
        await open_stage(get_test_data_path(__name__, "usd/mesh.usda"))
        core = self._make_core()

        sub_check_count = 0
        sub_fix_count = 0

        def check_check_sub_validation(_result, _message, _data):
            nonlocal sub_check_count
            sub_check_count += 1
            self.assertTrue(_result, msg=_message)
            self.assertIn("Check", _message)
            self.assertNotIn("FAIL", _message)
            self.assertIn("PASS", _message)

        def check_fix_sub_validation(_result, _message, _data):
            nonlocal sub_fix_count
            sub_fix_count += 1

        _sub_check_check = core.model.check_plugins[0].instance.subscribe_check(check_check_sub_validation)  # noqa
        _sub_check_fix = core.model.check_plugins[0].instance.subscribe_fix(check_fix_sub_validation)  # noqa

        # Act
        await core.deferred_run()

        # Assert
        self.assertEqual(sub_check_count, 1)
        self.assertEqual(sub_fix_count, 0)  # 0 because the check is good, so we dont run the fix

    async def test_run_no_fix_multi_layer(self):
        # Arrange
        await open_stage(get_test_data_path(__name__, "usd/multi_layer_no_fix.usda"))
        core = self._make_core()

        sub_check_count = 0
        sub_fix_count = 0

        def check_check_sub_validation(_result, _message, _data):
            nonlocal sub_check_count
            sub_check_count += 1
            self.assertTrue(_result, msg=_message)
            self.assertIn("Check", _message)
            self.assertNotIn("FAIL", _message)
            self.assertIn("PASS", _message)

        def check_fix_sub_validation(_result, _message, _data):
            nonlocal sub_fix_count
            sub_fix_count += 1

        _sub_check_check = core.model.check_plugins[0].instance.subscribe_check(check_check_sub_validation)  # noqa
        _sub_check_fix = core.model.check_plugins[0].instance.subscribe_fix(check_fix_sub_validation)  # noqa

        # Act
        await core.deferred_run()

        # Assert
        self.assertEqual(sub_check_count, 2)
        self.assertEqual(sub_fix_count, 0)  # 0 because the check is good, so we don't run the fix

    async def test_run_auto_fix(self):
        # Arrange
        await open_stage(get_test_data_path(__name__, "usd/cubes.usda"))
        core = self._make_core()
        usd_context = omni.usd.get_context()
        stage = usd_context.get_stage()
        self.assertFalse(stage.HasDefaultPrim())

        # Act
        await core.deferred_run()

        # Assert
        stage = omni.usd.get_context().get_stage()
        self.assertTrue(stage.HasDefaultPrim())

        session_layer = stage.GetSessionLayer()
        root_prims_count = len(
            [p for p in stage.GetPseudoRoot().GetChildren() if not session_layer.GetPrimAtPath(p.GetPath())]
        )
        self.assertEqual(root_prims_count, 1)

    async def test_run_auto_fix_multi_layer(self):
        # Arrange
        await open_stage(get_test_data_path(__name__, "usd/multi_layer_auto.usda"))
        core = self._make_core()
        usd_context = omni.usd.get_context()
        stage = usd_context.get_stage()

        root_layer = stage.GetRootLayer()
        sub_layer = Sdf.Layer.FindOrOpenRelativeToLayer(root_layer, root_layer.subLayerPaths[0])

        self.assertFalse(root_layer.HasDefaultPrim())
        self.assertTrue(sub_layer.HasDefaultPrim())

        # Act
        await core.deferred_run()

        # Assert
        stage = omni.usd.get_context().get_stage()
        for layer in stage.GetLayerStack(includeSessionLayers=False):
            self.assertTrue(layer.HasDefaultPrim())

        session_layer = stage.GetSessionLayer()
        root_prims_count = len(
            [p for p in stage.GetPseudoRoot().GetChildren() if not session_layer.GetPrimAtPath(p.GetPath())]
        )
        self.assertEqual(root_prims_count, 1)

    async def test_run_auto_fix_multi_root(self):
        # Arrange
        await open_stage(get_test_data_path(__name__, "usd/multiple_roots.usda"))
        core = self._make_core()
        stage = omni.usd.get_context().get_stage()
        self.assertFalse(stage.HasDefaultPrim())

        # Act
        await core.deferred_run()

        # Assert
        stage = omni.usd.get_context().get_stage()

        self.assertTrue(stage.HasDefaultPrim())
        self.assertEquals(stage.GetDefaultPrim().GetName(), "Group")

        session_layer = stage.GetSessionLayer()
        root_prims_count = len(
            [p for p in stage.GetPseudoRoot().GetChildren() if not session_layer.GetPrimAtPath(p.GetPath())]
        )
        self.assertEqual(root_prims_count, 1)

    async def test_run_auto_fix_multi_root_multi_layer(self):
        # Arrange
        await open_stage(get_test_data_path(__name__, "usd/multi_layer_multiple_roots.usda"))
        core = self._make_core()
        stage = omni.usd.get_context().get_stage()

        root_layer = stage.GetRootLayer()
        sub_layer = Sdf.Layer.FindOrOpenRelativeToLayer(root_layer, root_layer.subLayerPaths[0])

        self.assertTrue(root_layer.HasDefaultPrim())
        self.assertFalse(sub_layer.HasDefaultPrim())

        # Act
        await core.deferred_run()

        # Assert
        stage = omni.usd.get_context().get_stage()

        root_layer = stage.GetRootLayer()
        sub_layer = Sdf.Layer.FindOrOpenRelativeToLayer(root_layer, root_layer.subLayerPaths[0])

        self.assertTrue(root_layer.HasDefaultPrim())
        # self.assertTrue(sub_layer.HasDefaultPrim())

        self.assertEqual(stage.GetDefaultPrim().GetName(), "Group")

        session_layer = stage.GetSessionLayer()
        root_prims_count = len(
            [p for p in stage.GetPseudoRoot().GetChildren() if not session_layer.GetPrimAtPath(p.GetPath())]
        )
        self.assertEqual(root_prims_count, 1)

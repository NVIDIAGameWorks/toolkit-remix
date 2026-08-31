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

import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import omni.usd
from omni.flux.nvtt.core import BlockFormat as _BlockFormat
from omni.flux.nvtt.core import MipmapFilter as _MipmapFilter
from omni.flux.utils.common.omni_url import OmniUrl
from omni.flux.validator.manager.core import ManagerCore as _ManagerCore
from omni.flux.validator.plugin.check.usd.texture.convert_to_dds import ConvertToDDS as _ConvertToDDS
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows, get_test_data_path, open_stage


class TestConvertToDDS(AsyncTestCase):
    async def setUp(self):
        await arrange_windows()
        self.temp_dir = TemporaryDirectory()  # pylint: disable=consider-using-with
        self.temp_path = Path(self.temp_dir.name)

    # After running each test
    async def tearDown(self):
        await omni.usd.get_context().close_stage_async()
        self.temp_dir.cleanup()
        self.temp_dir = None

    def _make_core(self):
        return _ManagerCore(
            {
                "name": "Test",
                "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                "check_plugins": [
                    {
                        "name": "ConvertToDDS",
                        "selector_plugins": [{"name": "AllShaders", "data": {}}],
                        "data": {
                            "data_flows": [{"name": "InOutData", "push_input_data": True, "push_output_data": True}]
                        },
                        "context_plugin": {"name": "CurrentStage", "data": {}},
                    }
                ],
            }
        )

    async def test_destroy_releases_base_schema(self):
        # Arrange
        await omni.usd.get_context().new_stage_async()
        plugin = self._make_core().model.check_plugins[0].instance
        plugin._schema = object()

        # Act
        plugin.destroy()

        # Assert
        self.assertIsNone(plugin._schema)

    async def test_on_max_workers_field_edit_end_with_invalid_value_restores_model(self):
        # Arrange
        await omni.usd.get_context().new_stage_async()
        check_plugin = self._make_core().model.check_plugins[0]
        model = MagicMock()
        model.get_value_as_int.return_value = 0

        # Act
        check_plugin.instance._on_max_workers_field_edit_end(check_plugin.data, model)

        # Assert
        self.assertEqual(2, check_plugin.data.max_workers)
        model.set_value.assert_called_once_with(2)

    async def test_default_conversion_settings_are_typed(self):
        """Default validator settings map directly to the in-process encoder."""
        # Arrange
        await omni.usd.get_context().new_stage_async()
        settings = self._make_core().model.check_plugins[0].data.conversion_settings

        # Assert
        self.assertEqual(_BlockFormat.BC7, settings["inputs:diffuse_texture"].block_format)
        self.assertTrue(settings["inputs:diffuse_texture"].gamma_encoded)
        self.assertEqual(_BlockFormat.BC5, settings["inputs:normalmap_texture"].block_format)
        self.assertFalse(settings["inputs:normalmap_texture"].gamma_encoded)
        self.assertEqual(_BlockFormat.BC4, settings["inputs:height_texture"].block_format)
        self.assertEqual(_MipmapFilter.MAX, settings["inputs:height_texture"].mip_filter)

    async def test_conversion_settings_accept_schema_data(self):
        """Validation schema data can override typed NVTT settings with raw enum values."""
        # Arrange
        await omni.usd.get_context().new_stage_async()

        # Act
        data = _ConvertToDDS.Data.model_validate(
            {
                "conversion_settings": {
                    "inputs:diffuse_texture": {
                        "block_format": 6,
                        "gamma_encoded": False,
                    }
                }
            }
        )

        # Assert
        setting = data.conversion_settings["inputs:diffuse_texture"]
        self.assertEqual(_BlockFormat.BC4, setting.block_format)
        self.assertFalse(setting.gamma_encoded)
        self.assertEqual(_MipmapFilter.BOX, setting.mip_filter)

    async def test_conversion_settings_accept_string_enum_values(self):
        """Validation schema data can override typed NVTT settings with lowercase enum names."""
        # Arrange
        await omni.usd.get_context().new_stage_async()

        # Act
        data = _ConvertToDDS.Data.model_validate(
            {
                "conversion_settings": {
                    "inputs:diffuse_texture": {
                        "block_format": "bc4",
                        "gamma_encoded": False,
                        "mip_filter": "max",
                    }
                }
            }
        )

        # Assert
        setting = data.conversion_settings["inputs:diffuse_texture"]
        self.assertEqual(_BlockFormat.BC4, setting.block_format)
        self.assertFalse(setting.gamma_encoded)
        self.assertEqual(_MipmapFilter.MAX, setting.mip_filter)

    async def test_fix_when_data_flow_raises_releases_executor(self):
        # Arrange
        shutil.copytree(get_test_data_path(__name__, "usd/pillow_cube"), self.temp_path / Path("pillow_cube"))
        await open_stage(str(self.temp_path / Path("pillow_cube/pillow_cube.usda")))
        check_plugin = self._make_core().model.check_plugins[0]
        check_plugin.data.max_workers = 1
        shader = omni.usd.get_context().get_stage().GetPrimAtPath("/World/Looks/M_Prop_CompanionCube_Pillow_A/Shader")
        executor_context = MagicMock()
        executor_context.__enter__.return_value = MagicMock()
        executor_context.__exit__.return_value = False

        # Act
        with (
            patch(
                "omni.flux.validator.plugin.check.usd.texture.convert_to_dds.ThreadPoolExecutor",
                return_value=executor_context,
            ) as thread_pool_executor,
            patch(
                "omni.flux.validator.plugin.check.usd.texture.convert_to_dds._validator_factory_utils.push_input_data",
                side_effect=RuntimeError("Data flow failed"),
            ),
            self.assertRaisesRegex(RuntimeError, "Data flow failed"),
        ):
            await check_plugin.instance._fix.__wrapped__(check_plugin.instance, check_plugin.data, "", [shader])

        # Assert
        thread_pool_executor.assert_called_once_with(max_workers=1)
        executor_context.__exit__.assert_called_once()

    async def test_run_nothing_to_fix(self):
        # Arrange
        await open_stage(get_test_data_path(__name__, "usd/mesh_no_texture.usda"))
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

        _sub_check_check = core.model.check_plugins[0].instance.subscribe_check(check_check_sub_validation)
        _sub_check_fix = core.model.check_plugins[0].instance.subscribe_fix(check_fix_sub_validation)

        with patch.object(OmniUrl, "delete") as delete_mock:
            # Act
            await core.deferred_run()

        # Assert
        self.assertEqual(delete_mock.call_count, 0)

        self.assertEqual(sub_check_count, 1)
        self.assertEqual(sub_fix_count, 0)  # 0 because the check is good, so we dont run the fix

        self.assertIsNone(core.model.check_plugins[0].data.data_flows[0].input_data)
        self.assertIsNone(core.model.check_plugins[0].data.data_flows[0].output_data)

    async def test_run_fix_converts_textures_in_process(self):
        """DDS conversion runs the real in-process NVTT encoder end to end.

        GPU pinning is exercised by omni.flux.nvtt.core's own tests, not here.
        """
        shutil.copytree(get_test_data_path(__name__, "usd/pillow_cube"), self.temp_path / Path("pillow_cube"))

        # Arrange
        await open_stage(str(self.temp_path / Path("pillow_cube/pillow_cube.usda")))
        core = self._make_core()
        usd_context = omni.usd.get_context()
        stage = usd_context.get_stage()

        # Act
        await core.deferred_run()

        # Assert
        prim = stage.GetPrimAtPath("/World/Looks/M_Prop_CompanionCube_Pillow_A/Shader")
        in_paths = [
            ("inputs:diffuse_texture", Path("pillow_cube/T_Prop_CompanionCube_Pillow_A_Albedo.png")),
            ("inputs:metallic_texture", Path("pillow_cube/T_Prop_CompanionCube_Pillow_A_Metal_Metallic.dds")),
            ("inputs:normalmap_texture", Path("pillow_cube/T_Prop_CompanionCube_Pillow_A_Normal.png")),
            ("inputs:reflectionroughness_texture", Path("pillow_cube/T_Prop_CompanionCube_Pillow_A_Rough.png")),
            ("inputs:height_texture", Path("pillow_cube/height.png")),
        ]
        out_paths = [
            ("inputs:diffuse_texture", Path("pillow_cube/T_Prop_CompanionCube_Pillow_A_Albedo.a.rtex.dds")),
            ("inputs:metallic_texture", Path("pillow_cube/T_Prop_CompanionCube_Pillow_A_Metal_Metallic.m.rtex.dds")),
            ("inputs:normalmap_texture", Path("pillow_cube/T_Prop_CompanionCube_Pillow_A_Normal.n.rtex.dds")),
            ("inputs:reflectionroughness_texture", Path("pillow_cube/T_Prop_CompanionCube_Pillow_A_Rough.r.rtex.dds")),
            ("inputs:height_texture", Path("pillow_cube/height.h.rtex.dds")),
        ]
        self.assertEqual(len(core.model.check_plugins[0].data.data_flows), 1)
        for attr_name, out_path_rel in out_paths:
            out_path = self.temp_path / out_path_rel
            self.assertEqual(prim.GetAttribute(attr_name).Get().resolvedPath, str(out_path))
            self.assertTrue(out_path.exists())

            # test dataflow out
            found_input = False
            for data_flow in core.model.check_plugins[0].data.data_flows:
                if str(out_path) in [str(Path(output_data)) for output_data in data_flow.output_data]:
                    found_input = True
                    break
            self.assertTrue(found_input)

        for _attr_name, in_path_rel in in_paths:
            in_path = self.temp_path / in_path_rel

            # test data flow in
            found_input = False
            for data_flow in core.model.check_plugins[0].data.data_flows:
                if str(in_path) in [str(Path(input_data)) for input_data in data_flow.input_data]:
                    found_input = True
                    break
            self.assertTrue(found_input)

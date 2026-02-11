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

import shutil
import tempfile
from pathlib import Path

import omni.kit.test
from omni.flux.utils.material_converter import MaterialConverterCore
from omni.flux.utils.material_converter.impl.omni_pbr_to_aperture_pbr import OmniPBRToAperturePBRConverterBuilder
from omni.flux.utils.material_converter.utils import SupportedShaderOutputs
from omni.kit.test_suite.helpers import get_test_data_path

_PRIM_PATHS = [
    "/World/Looks/M_Fixture_Elevator_Interior_02",
    "/World/Looks/M_Fixture_Elevator_Interior_Glass",
    "/World/Looks/M_Fixture_Elevator_Interior_01",
]


class TestOmniPBRToAperturePBRConverterBuilderE2E(omni.kit.test.AsyncTestCase):
    # Before running each test
    async def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.context = omni.usd.get_context()

    # After running each test
    async def tearDown(self):
        if omni.usd.get_context().get_stage():
            await omni.usd.get_context().close_stage_async()

        self.temp_dir.cleanup()

        self.temp_dir = None
        self.context = None

    async def test_convert_should_produce_expected_output(self):
        # Setup the file paths
        base_temp_path = Path(self.temp_dir.name)
        omni_pbr_temp_path = base_temp_path / "omni_pbr.usda"
        aperture_pbr_temp_path = base_temp_path / "aperture_pbr.usda"

        omni_pbr_path = get_test_data_path(__name__, "usd/omni_pbr.usda")
        aperture_pbr_path = get_test_data_path(__name__, "usd/aperture_pbr.usda")

        # Copy the test input to avoid accidentally modifying it
        shutil.copy(omni_pbr_path, omni_pbr_temp_path)

        # Open the copied stage
        await self.context.open_stage_async(str(omni_pbr_temp_path))
        stage = self.context.get_stage()
        root_layer = stage.GetRootLayer()

        converter_builder = OmniPBRToAperturePBRConverterBuilder()

        # Convert all the different prims in the stage
        for prim_path in _PRIM_PATHS:
            prim = stage.GetPrimAtPath(prim_path)

            self.assertTrue(bool(prim))

            converter = converter_builder.build(prim, SupportedShaderOutputs.APERTURE_PBR_OPACITY.value)
            success, message, was_skipped = await MaterialConverterCore.convert("", converter)

            self.assertTrue(success)
            self.assertEqual(f"Completed prim '{prim_path}' conversion on layer {root_layer.identifier}", message)
            self.assertFalse(was_skipped)

        self.context.save_as_stage(str(aperture_pbr_temp_path))

        with open(aperture_pbr_path) as expected_file:
            with open(aperture_pbr_temp_path) as actual_file:
                self.assertEqual(expected_file.read(), actual_file.read())

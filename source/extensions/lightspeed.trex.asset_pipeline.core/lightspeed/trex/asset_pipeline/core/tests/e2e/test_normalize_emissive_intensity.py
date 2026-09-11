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

import pathlib
import tempfile

import omni.kit.test
from lightspeed.trex.asset_pipeline.core import RemixAssetItem, RemixAssetPipelineContext
from lightspeed.trex.asset_pipeline.core.steps import NormalizeEmissiveIntensityStep
from pxr import Sdf, Usd, UsdShade


class TestNormalizeEmissiveIntensityE2E(omni.kit.test.AsyncTestCase):
    async def test_run_normalizes_only_legacy_emissive_intensity(self):
        """Shaders authored at the legacy 10000.0 emissive intensity are rewritten to 1.0; others stay untouched."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Step 1: Author a real model stage on disk with two shaders, one carrying the legacy
            # 10000.0 emissive intensity and one carrying an intentional artist value.
            model_path = pathlib.Path(temp_dir) / "model.usda"
            stage = Usd.Stage.CreateNew(str(model_path))
            legacy_shader = UsdShade.Shader.Define(stage, "/World/Looks/Legacy/Shader")
            legacy_shader.CreateInput("emissive_intensity", Sdf.ValueTypeNames.Float).Set(10000.0)
            other_shader = UsdShade.Shader.Define(stage, "/World/Looks/Other/Shader")
            other_shader.CreateInput("emissive_intensity", Sdf.ValueTypeNames.Float).Set(2.5)
            stage.Save()

            item = RemixAssetItem.from_model(model_path)

            async with RemixAssetPipelineContext(items=[item]) as context:
                # Step 2: Run the normalization step against the real stage through the pipeline context.
                await NormalizeEmissiveIntensityStep().run(context)

                # Step 3: Reopen the saved file from disk and verify only the legacy value moved to 1.0.
                reopened = Usd.Stage.Open(str(model_path))
                legacy_attr = reopened.GetAttributeAtPath("/World/Looks/Legacy/Shader.inputs:emissive_intensity")
                other_attr = reopened.GetAttributeAtPath("/World/Looks/Other/Shader.inputs:emissive_intensity")
                self.assertEqual(legacy_attr.Get(), 1.0)
                self.assertEqual(other_attr.Get(), 2.5)

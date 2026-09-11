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
from lightspeed.trex.asset_pipeline.core.steps import MetaStep
from pxr import Gf, Usd, UsdGeom


class TestMetaE2E(omni.kit.test.AsyncTestCase):
    async def test_run_wraps_model_roots_and_normalizes_unit_scale(self):
        """The meta step wraps model roots under ReferenceTarget/XForms and normalizes unit scale."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Step 1: Author a real model stage on disk with two root prims, a scaled Deco prim, and
            # centimeter units, so the step has both roots to wrap and a unit scale to normalize.
            temp_path = pathlib.Path(temp_dir)
            stage_path = temp_path / "model.usda"
            stage = Usd.Stage.CreateNew(str(stage_path))
            UsdGeom.Mesh.Define(stage, "/Mesh")
            deco = UsdGeom.Xform.Define(stage, "/Deco")
            deco.AddScaleOp().Set(Gf.Vec3f(2.0, 2.0, 2.0))
            stage.SetMetadata("metersPerUnit", 0.01)
            stage.GetRootLayer().Save()

            item = RemixAssetItem.from_model(stage_path)

            async with RemixAssetPipelineContext(items=[item], output_dir=temp_path / "processed") as context:
                # Step 2: Run the meta step against the real stage through the pipeline USD context.
                await MetaStep().run(context)

                # Step 3: Reopen the saved stage through the pipeline context and inspect the result.
                result_stage = await context.open_stage(stage_path)

                # The two former roots now live under a single ReferenceTarget default prim.
                root_prims = result_stage.GetPseudoRoot().GetChildren()
                self.assertEqual(len(root_prims), 1)
                reference_target = root_prims[0]
                self.assertEqual(reference_target.GetName(), "ReferenceTarget")
                self.assertEqual(str(result_stage.GetDefaultPrim().GetPath()), "/ReferenceTarget")

                # ReferenceTarget owns exactly one XForms wrapper that holds the original content.
                xforms_children = reference_target.GetChildren()
                self.assertEqual(len(xforms_children), 1)
                xforms_prim = xforms_children[0]
                self.assertEqual(xforms_prim.GetName(), "XForms")

                # Unit normalization rewrites the stage to meters.
                self.assertEqual(result_stage.GetMetadata("metersPerUnit"), 1.0)

                # Both wrappers are legacy-style groups with an identity translate/rotate/scale
                # transform. The unit-scale pass lands on the XForms wrapper, the root at the time it
                # ran, and leaves the outer ReferenceTarget at identity.
                for wrapper in (reference_target, xforms_prim):
                    self.assertEqual(Usd.ModelAPI(wrapper).GetKind(), "group")
                    self.assertEqual(
                        [op.GetOpName() for op in UsdGeom.Xformable(wrapper).GetOrderedXformOps()],
                        ["xformOp:translate", "xformOp:rotateXYZ", "xformOp:scale"],
                    )
                self.assertEqual(tuple(UsdGeom.Xformable(xforms_prim).GetOrderedXformOps()[2].Get()), (100, 100, 100))
                self.assertEqual(tuple(UsdGeom.Xformable(reference_target).GetOrderedXformOps()[2].Get()), (1, 1, 1))

                # The original Deco prim is nested (no longer a root prim) by the time the
                # unit-scale pass runs, so its own authored scale is left untouched.
                deco_prim = xforms_prim.GetChild("Deco")
                self.assertTrue(deco_prim.IsValid())
                deco_scale_ops = [
                    op
                    for op in UsdGeom.Xformable(deco_prim).GetOrderedXformOps()
                    if op.GetOpType() == UsdGeom.XformOp.TypeScale
                ]
                self.assertEqual(len(deco_scale_ops), 1)
                self.assertEqual(tuple(deco_scale_ops[0].Get()), (2.0, 2.0, 2.0))

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

__all__ = ["TestAssetModifierSubmissionE2E"]

import enum

from carb.settings import get_settings
from lightspeed.trex.asset_modifiers.factory import ModifierInput
from lightspeed.trex.asset_modifiers.factory import get_instance as _get_asset_modifier_factory
from lightspeed.trex.asset_modifiers.core.constants import SOURCE_INPUT
from lightspeed.trex.asset_modifiers.core.core import AssetModifiersCore
from lightspeed.trex.asset_modifiers.core.enums import SourceGetter
from lightspeed.trex.asset_modifiers.core.settings import AssetModifierSettings
from lightspeed.trex.asset_modifiers.core.tests.e2e.scale_mesh_job import ScaleMeshTestJob
from lightspeed.trex.asset_modifiers.core.tests.e2e.scale_mesh_modifier import ScaleMeshTestModifier
from omni.flux.utils.tests.context_managers import open_test_project
from omni.kit.test import AsyncTestCase
from omni.usd import get_context
from pxr import UsdShade

_OWNER = "/RootNode/meshes/mesh_0AB745B8BEE1F16B"
_MESH = f"{_OWNER}/mesh"


class TestAssetModifierSubmissionE2E(AsyncTestCase):
    """Prepare modifier graphs from a real project stage."""

    async def setUp(self) -> None:
        """Register and select the scale modifier."""
        self._core = AssetModifiersCore("")
        _get_asset_modifier_factory().register_plugins([ScaleMeshTestModifier])
        AssetModifierSettings().set_active_modifier_name(ScaleMeshTestModifier.name)

    async def tearDown(self) -> None:
        """Remove the modifier and its settings."""
        _get_asset_modifier_factory().unregister_plugins([ScaleMeshTestModifier])
        get_settings().destroy_item(AssetModifierSettings.get_modifier_key(ScaleMeshTestModifier))
        AssetModifierSettings().set_active_modifier_name("")

    async def test_stage_values_reach_the_job_and_skip_a_source_without_material(self) -> None:
        """Pass the material read at Run to the job, group All Compatible Prims, then skip a source with no material."""
        async with open_test_project("usd/project_example/combined.usda", ext_name="lightspeed.trex.app.resources"):
            # 1. The selected capture mesh gets one graph, and its job receives the material read from the stage.
            graphs, skipped = await self._core.prepare_submission([_MESH])
            (job,) = [job for job in graphs[0].jobs if isinstance(job, ScaleMeshTestJob)]
            self.assertEqual(skipped, {})
            # Like AI Tools, the graph has the modifier name only, so Job Queue filters stay short.
            self.assertEqual(graphs[0].name, ScaleMeshTestModifier.display_name)
            self.assertEqual(job.values, {"scale": 1.0, "material": "/RootNode/Looks/mat_BC868CE5A075ABB1"})

            # 2. All Compatible Prims finds the same mesh without a selection and builds one graph per source model.
            AssetModifierSettings().set_value(ScaleMeshTestModifier, SOURCE_INPUT, SourceGetter.ALL)
            graphs, _skipped = await self._core.prepare_submission()
            jobs = [job for graph in graphs for job in graph.jobs if isinstance(job, ScaleMeshTestJob)]
            self.assertEqual(len({job.source_url for job in jobs}), len(jobs))
            self.assertIn(_MESH, [path for job in jobs for path in job.prim_paths])

            # 3. Without a bound material, build_graph() sets the job's skip reason, so the source is left out.
            AssetModifierSettings().set_value(ScaleMeshTestModifier, SOURCE_INPUT, SourceGetter.SELECTED)
            UsdShade.MaterialBindingAPI(get_context().get_stage().GetPrimAtPath(_OWNER)).UnbindAllBindings()
            self.assertEqual(
                await self._core.prepare_submission([_MESH]), ([], {_MESH: "The mesh has no bound material."})
            )

    async def test_plain_enum_input_round_trips_through_settings(self) -> None:
        """Store a plain Enum member as its value and read the same member back."""
        mode = enum.Enum("Mode", {"FIRST": 1, "SECOND": 2})
        item = ModifierInput("mode", "Mode", mode, mode.FIRST)
        settings = AssetModifierSettings()

        settings.set_value(ScaleMeshTestModifier, item, mode.SECOND)

        self.assertIs(settings.get_value(ScaleMeshTestModifier, item), mode.SECOND)

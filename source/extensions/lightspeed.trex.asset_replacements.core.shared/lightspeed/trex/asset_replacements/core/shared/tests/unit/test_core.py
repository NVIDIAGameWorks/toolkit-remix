"""
* Copyright (c) 2023, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
from lightspeed.trex.asset_replacements.core.shared import Setup as _AssetReplacementsCore
from omni.flux.utils.widget.resources import get_test_data as _get_test_data
from omni.kit.test.async_unittest import AsyncTestCase
from omni.kit.test_suite.helpers import open_stage, wait_stage_loading
from pxr import Sdf


class TestAssetReplacementsCoreWidget(AsyncTestCase):
    # Before running each test
    async def setUp(self):
        await open_stage(_get_test_data("usd/project_example/combined.usda"))

    # After running each test
    async def tearDown(self):
        await wait_stage_loading()

    async def test_filter_transformable(self):
        # setup
        core = _AssetReplacementsCore("")

        self.assertEqual(core.filter_transformable_prims([Sdf.Path("/RootNode")]), [])
        self.assertEqual(core.filter_transformable_prims([Sdf.Path("/RootNode/lights")]), [])
        self.assertEqual(
            core.filter_transformable_prims([Sdf.Path("/RootNode/lights/light_9907D0B07D040077")]),
            ["/RootNode/lights/light_9907D0B07D040077"],
        )
        self.assertEqual(
            core.filter_transformable_prims(
                [Sdf.Path("/RootNode"), Sdf.Path("/RootNode/lights/light_9907D0B07D040077")]
            ),
            ["/RootNode/lights/light_9907D0B07D040077"],
        )

        self.assertEqual(core.filter_transformable_prims([Sdf.Path("/RootNode/meshes")]), [])
        self.assertEqual(core.filter_transformable_prims([Sdf.Path("/RootNode/meshes/mesh_CED45075A077A49A")]), [])
        self.assertEqual(core.filter_transformable_prims([Sdf.Path("/RootNode/meshes/mesh_CED45075A077A49A/mesh")]), [])

        self.assertEqual(
            core.filter_transformable_prims(
                [Sdf.Path("/RootNode/meshes/mesh_BAC90CAA733B0859/ref_c89e0497f4ff4dc4a7b70b79c85692da")]
            ),
            [],
        )
        self.assertEqual(
            core.filter_transformable_prims(
                [Sdf.Path("/RootNode/meshes/mesh_BAC90CAA733B0859/ref_c89e0497f4ff4dc4a7b70b79c85692da/Cube")]
            ),
            [],
        )

        self.assertEqual(core.filter_transformable_prims([Sdf.Path("/RootNode/instances")]), [])
        self.assertEqual(core.filter_transformable_prims([Sdf.Path("/RootNode/instances/inst_BAC90CAA733B0859_0")]), [])
        self.assertEqual(
            core.filter_transformable_prims(
                [Sdf.Path("/RootNode/instances/inst_BAC90CAA733B0859_0/ref_c89e0497f4ff4dc4a7b70b79c85692da")]
            ),
            ["/RootNode/meshes/mesh_BAC90CAA733B0859/ref_c89e0497f4ff4dc4a7b70b79c85692da"],
        )
        self.assertEqual(
            core.filter_transformable_prims(
                [Sdf.Path("/RootNode/instances/inst_BAC90CAA733B0859_0/ref_c89e0497f4ff4dc4a7b70b79c85692da/Cube")]
            ),
            ["/RootNode/meshes/mesh_BAC90CAA733B0859/ref_c89e0497f4ff4dc4a7b70b79c85692da/Cube"],
        )
        self.assertEqual(
            core.filter_transformable_prims(
                [
                    Sdf.Path("/RootNode/instances/inst_BAC90CAA733B0859_0"),
                    Sdf.Path("/RootNode/instances/inst_BAC90CAA733B0859_0/ref_c89e0497f4ff4dc4a7b70b79c85692da/Cube"),
                ]
            ),
            ["/RootNode/meshes/mesh_BAC90CAA733B0859/ref_c89e0497f4ff4dc4a7b70b79c85692da/Cube"],
        )

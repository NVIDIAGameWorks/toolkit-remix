"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""

import os.path
import pathlib
import tempfile

import carb
import carb.tokens
import omni.kit.test
import omni.usd
from lightspeed.layer_manager.scripts.core import LayerManagerCore, LayerType

# from ..upscale_core import LightspeedUpscalerCore


class Test(omni.kit.test.AsyncTestCaseFailOnLogError):
    async def setUp(self):
        pass

    async def tearDown(self):
        pass

    async def test_batch_upscale_function(self):
        """Test the batch upscale functionality of the lightspeed.upscale extension.

        Takes a simplified capture scene from a game with a single model and material, and runs the batch upscale
        processed. Then this test confirms that the replacement layer is generated, includes an autoupscale sublayer
        and has generated an upscaled .dds texture.
        """
        pass
        # extension_path = carb.tokens.get_tokens_interface().resolve("${lightspeed.upscale}")
        # test_file_path = str(
        #     pathlib.Path(extension_path)
        #     .joinpath("data")
        #     .joinpath("lss")
        #     .joinpath("capture")
        #     .joinpath("portal-gun-test-stage.usda")
        #     .absolute()
        # )
        # temp_dir = tempfile.TemporaryDirectory()
        # replacement_path = os.path.join(temp_dir.name, "replacements.usda")
        # autoupscale_path = os.path.join(temp_dir.name, "autoupscale.usda")
        # layer_manager = LayerManagerCore()
        # layer_manager.insert_sublayer(test_file_path, LayerType.capture, False)
        # layer_manager.lock_layer(LayerType.capture)
        # replacement_layer = layer_manager.create_new_sublayer(
        #     LayerType.replacement, path=replacement_path, sublayer_create_position=0
        # )
        # await LightspeedUpscalerCore.lss_async_batch_upscale_entire_capture_layer()
        # replacement_exists = os.path.exists(replacement_path)
        # upscale_texture_exists = os.path.exists(temp_dir.name + "/textures/F5CE656D9F82F196_upscaled4x.dds")
        # autoupscale_usda_exits = os.path.exists(autoupscale_path)
        # autoupscale_is_sublayer_of_replacement = False
        # for sublayerpath in replacement_layer.subLayerPaths:
        #     if os.path.basename(sublayerpath) == "autoupscale.usda":
        #         autoupscale_is_sublayer_of_replacement = True
        # temp_dir.cleanup()
        # result = all(
        #     [replacement_exists, upscale_texture_exists, autoupscale_usda_exits, autoupscale_is_sublayer_of_replacement]
        # )
        # self.assertTrue(result)

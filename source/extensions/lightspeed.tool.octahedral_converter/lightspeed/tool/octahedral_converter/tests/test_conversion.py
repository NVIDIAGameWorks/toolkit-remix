"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""

import pathlib

import carb
import carb.tokens
import numpy as np
import omni.kit.test
import omni.usd
from PIL import Image

from ..octahedral_converter_core import LightspeedOctahedralConverter


class Test(omni.kit.test.AsyncTestCaseFailOnLogError):
    async def setUp(self):
        pass

    async def tearDown(self):
        pass

    async def test_convert_dx(self):
        """Test converting a DirectX Normal Map to an Octahedral Normal Map"""
        extension_path = carb.tokens.get_tokens_interface().resolve("${lightspeed.tool.octahedral_converter}")
        texture_folder_path = pathlib.Path(extension_path).joinpath("data").joinpath("textures")
        oth_path = texture_folder_path.joinpath("Normal_Map_Test_Octahedral.png").absolute()
        dx_path = texture_folder_path.joinpath("Normal_Map_Test_DirectX.png").absolute()

        dx_img = np.array(Image.open(dx_path))[:, :, 0:3]
        oth_img = np.array(Image.open(oth_path))[:, :, 0:3]
        converted_img = LightspeedOctahedralConverter.ConvertDXToOctahedral(dx_img)

        diff = oth_img[:, :, 0:3].astype("int32") - converted_img[:, :, 0:3].astype("int32")

        # allow pixels to be off by +-2 to account for floating point error
        self.assertTrue((diff <= 2).all())
        self.assertTrue((diff >= -2).all())

    async def test_convert_ogl(self):
        """Test converting a OpenGL Normal Map to an Octahedral Normal Map"""
        extension_path = carb.tokens.get_tokens_interface().resolve("${lightspeed.tool.octahedral_converter}")
        texture_folder_path = pathlib.Path(extension_path).joinpath("data").joinpath("textures")
        oth_path = texture_folder_path.joinpath("Normal_Map_Test_Octahedral.png").absolute()
        ogl_path = texture_folder_path.joinpath("Normal_Map_Test_OpenGL.png").absolute()

        oth_img = np.array(Image.open(oth_path))[:, :, 0:3]
        ogl_img = np.array(Image.open(ogl_path))[:, :, 0:3]

        converted_img = LightspeedOctahedralConverter.ConvertOGLToOctahedral(ogl_img)

        diff = oth_img[:, :, 0:3].astype("int32") - converted_img[:, :, 0:3].astype("int32")
        self.assertTrue((diff <= 2).all())
        self.assertTrue((diff >= -2).all())

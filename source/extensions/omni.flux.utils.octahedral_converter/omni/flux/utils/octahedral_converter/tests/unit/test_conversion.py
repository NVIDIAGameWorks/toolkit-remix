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

import pathlib

import numpy as np
import omni.kit.test
import omni.usd
from omni.flux.utils.octahedral_converter import OctahedralConverter
from omni.kit.test_suite.helpers import get_test_data_path
from PIL import Image


class TestOctahedralConverter(omni.kit.test.AsyncTestCaseFailOnLogError):
    async def setUp(self):
        pass

    async def tearDown(self):
        pass

    async def test_convert_dx(self):
        """Test converting a DirectX Normal Map to an Octahedral Normal Map"""
        texture_folder_path = pathlib.Path(get_test_data_path(__name__, "textures"))
        oth_path = texture_folder_path.joinpath("Normal_Map_Test_Octahedral.png").absolute()
        dx_path = texture_folder_path.joinpath("Normal_Map_Test_DirectX.png").absolute()

        with Image.open(dx_path) as image_file:
            dx_img = np.array(image_file)[:, :, 0:3]
        with Image.open(oth_path) as image_file:
            oth_img = np.array(image_file)[:, :, 0:3]
        converted_img = OctahedralConverter.convert_dx_to_octahedral(dx_img)

        diff = oth_img[:, :, 0:3].astype("int32") - converted_img[:, :, 0:3].astype("int32")

        # allow pixels to be off by +-2 to account for floating point error
        self.assertTrue((diff <= 2).all())
        self.assertTrue((diff >= -2).all())

    async def test_convert_ogl(self):
        """Test converting a OpenGL Normal Map to an Octahedral Normal Map"""
        texture_folder_path = pathlib.Path(get_test_data_path(__name__, "textures"))
        oth_path = texture_folder_path.joinpath("Normal_Map_Test_Octahedral.png").absolute()
        ogl_path = texture_folder_path.joinpath("Normal_Map_Test_OpenGL.png").absolute()

        with Image.open(oth_path) as image_file:
            oth_img = np.array(image_file)[:, :, 0:3]
        with Image.open(ogl_path) as image_file:
            ogl_img = np.array(image_file)[:, :, 0:3]

        converted_img = OctahedralConverter.convert_ogl_to_octahedral(ogl_img)

        diff = oth_img[:, :, 0:3].astype("int32") - converted_img[:, :, 0:3].astype("int32")
        self.assertTrue((diff <= 2).all())
        self.assertTrue((diff >= -2).all())

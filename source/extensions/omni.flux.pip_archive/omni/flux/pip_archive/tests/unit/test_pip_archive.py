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

import omni.kit.pipapi
import omni.kit.test


class TestPipArchive(omni.kit.test.AsyncTestCase):
    async def test_pip_archive(self):
        # Take one of packages from deps/pip.toml,
        # it should be prebundled and available without need for going into online index
        omni.kit.pipapi.install("numpy", version="1.19.0", use_online_index=False)
        import numpy as np  # noqa: PLC0415

        self.assertIsNotNone(np)

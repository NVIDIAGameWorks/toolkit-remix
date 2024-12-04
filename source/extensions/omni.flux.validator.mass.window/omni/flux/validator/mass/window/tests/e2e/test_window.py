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

from omni import kit
from omni.kit.test import AsyncTestCase


class TestMassWindow(AsyncTestCase):
    """Empty test file to prevent flakey test exits in CI"""

    async def setUp(self):
        pass

    async def tearDown(self):
        for _ in range(10):
            await kit.app.get_app().next_update_async()

    async def test_do_nothing(self):
        pass

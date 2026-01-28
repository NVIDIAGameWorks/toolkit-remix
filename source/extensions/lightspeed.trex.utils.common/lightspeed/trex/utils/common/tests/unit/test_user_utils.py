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

import omni.kit.test
from lightspeed.trex.utils.common.user_utils import get_user_key


class TestUserUtils(omni.kit.test.AsyncTestCase):
    def test_get_user_key(self):
        # Act
        key1 = get_user_key()
        key2 = get_user_key()

        # Assert
        # Verify that keys are hex values
        self.assertTrue(int(key1, 16))
        self.assertTrue(int(key2, 16))
        # Verify that it is consistent
        self.assertEqual(key1, key2)

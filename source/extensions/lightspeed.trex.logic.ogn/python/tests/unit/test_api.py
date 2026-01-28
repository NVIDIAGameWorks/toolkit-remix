"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

# Testing the stability of the API in this module

import lightspeed.trex.logic.ogn as ogtp
import omni.graph.core.tests as ogts
from omni.graph.tools.tests.internal_utils import _check_module_api_consistency, _check_public_api_contents


# ======================================================================
class _TestLightspeedTrexLogicOgnApi(ogts.OmniGraphTestCase):
    # These are standard subdirectories that are not published as explicit modules of their own
    _UNPUBLISHED = ["tests", "ogn"]

    async def test_api(self):
        _check_module_api_consistency(ogtp, self._UNPUBLISHED)  # noqa: SLF001
        _check_module_api_consistency(ogtp.tests, is_test_module=True)  # noqa: SLF001

    async def test_api_features(self):
        """Test that the known public API features continue to exist"""
        _check_public_api_contents(ogtp, [], self._UNPUBLISHED, only_expected_allowed=True)  # noqa: SLF001
        _check_public_api_contents(ogtp.tests, [], [], only_expected_allowed=True)  # noqa: SLF001

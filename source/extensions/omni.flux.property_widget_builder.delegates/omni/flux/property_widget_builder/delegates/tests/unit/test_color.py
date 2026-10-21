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

__all__ = ("TestChannelModel",)

import omni.kit.test
from omni.flux.property_widget_builder.delegates.float_value.color import _ChannelModel


class TestChannelModel(omni.kit.test.AsyncTestCase):
    """Validate channel input that native numeric controls may deliver."""

    async def test_set_value_nonfinite_input_preserves_current_channel(self):
        """Reject non-finite numeric input before it can become a normalized color."""
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                # Arrange
                model = _ChannelModel(0.5)

                # Act
                model.set_value(value)

                # Assert
                self.assertEqual(model.get_value_as_float(), 0.5)

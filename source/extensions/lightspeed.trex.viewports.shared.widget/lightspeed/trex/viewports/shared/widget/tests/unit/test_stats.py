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

from unittest.mock import MagicMock, patch

import omni.kit.test
from lightspeed.trex.viewports.shared.widget.stats import items as _items


class TestViewportStatisticFading(omni.kit.test.AsyncTestCase):
    async def test_begin_animation_preserves_alpha_until_external_update(self):
        # Arrange
        update_stream = MagicMock()
        update_stream.create_subscription_to_pop.return_value = MagicMock(name="subscription")
        app = MagicMock()
        app.get_update_event_stream.return_value = update_stream
        statistic = _items.ViewportStatisticFading(
            "/exts/test/cameraSpeedMessage",
            stat_name="Camera Speed",
            parent=MagicMock(),
        )
        update_info = {}

        try:
            with patch("omni.kit.app.get_app", return_value=app):
                statistic._begin_animation()

            # Act
            skipped = statistic._skip_update(update_info)

            # Assert
            self.assertTrue(skipped)
            self.assertEqual(1, update_info["alpha"])
        finally:
            statistic.destroy()

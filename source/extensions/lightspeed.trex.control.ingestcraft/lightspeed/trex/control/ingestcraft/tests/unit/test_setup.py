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

import lightspeed.trex.control.ingestcraft.setup as _setup_module
from lightspeed.trex.control.ingestcraft.setup import Setup


class TestSetup(omni.kit.test.AsyncTestCase):
    """Tests IngestCraft stage setup."""

    async def test_init_creates_stage_without_writing_lifecycle_settings(self) -> None:
        """Create the IngestCraft stage without using settings as lifecycle signals."""
        # Arrange
        settings = MagicMock()
        settings.get.return_value = "stagecraft"
        context = MagicMock()
        contexts = MagicMock()
        contexts.get_usd_context.return_value = context

        with (
            patch.object(_setup_module.carb.settings, "get_settings", return_value=settings),
            patch.object(_setup_module, "_trex_contexts_instance", return_value=contexts),
        ):
            # Act
            setup = Setup()

        # Assert
        self.assertIs(context, setup._context)
        context.new_stage_with_callback.assert_called_once_with(setup._on_new_stage_created)
        settings.set.assert_not_called()

    async def test_new_stage_callback_failure_does_not_publish_readiness(self) -> None:
        """Leave readiness unpublished when the initial stage cannot be created."""
        # Arrange
        setup = Setup.__new__(Setup)

        with patch.object(_setup_module.carb, "log_error") as mock_log_error:
            # Act
            setup._on_new_stage_created(False, "stage creation failed")

        # Assert
        mock_log_error.assert_called_once()

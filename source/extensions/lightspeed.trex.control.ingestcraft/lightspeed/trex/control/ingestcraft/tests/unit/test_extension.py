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

import lightspeed.trex.control.ingestcraft.extension as _extension_module
from lightspeed.trex.control.ingestcraft.extension import TrexStageCraftControlExtension


class TestExtensionLifecycle(omni.kit.test.AsyncTestCase):
    """Tests IngestCraft extension reload lifecycle."""

    async def test_startup_creates_setup(self) -> None:
        """Create one IngestCraft setup during extension startup."""
        # Arrange
        extension = TrexStageCraftControlExtension()
        setup = object()
        contexts = MagicMock()

        with (
            patch.object(_extension_module, "trex_contexts_instance", return_value=contexts),
            patch.object(_extension_module, "Setup", return_value=setup) as setup_mock,
        ):
            # Act
            extension.on_startup("lightspeed.trex.control.ingestcraft")

        # Assert
        setup_mock.assert_called_once_with()
        contexts.create_usd_context.assert_called_once_with(_extension_module._TrexContexts.INGEST_CRAFT)
        self.assertIs(setup, extension._setup)

    async def test_shutdown_releases_setup(self) -> None:
        """Release the IngestCraft setup reference during extension shutdown."""
        # Arrange
        extension = TrexStageCraftControlExtension()
        extension._setup = object()

        # Act
        extension.on_shutdown()

        # Assert
        self.assertIsNone(extension._setup)

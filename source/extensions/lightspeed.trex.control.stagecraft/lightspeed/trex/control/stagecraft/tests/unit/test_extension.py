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

import lightspeed.trex.control.stagecraft.extension as _extension_module
from lightspeed.trex.control.stagecraft.extension import TrexStageCraftControlExtension


class TestExtensionLifecycle(omni.kit.test.AsyncTestCase):
    """Test StageCraft extension resource ownership."""

    async def test_startup_owns_stagecraft_setup(self):
        """Retain the StageCraft setup on the extension instance."""
        # Arrange
        extension = TrexStageCraftControlExtension()
        setup = MagicMock()
        contexts = MagicMock()
        event_manager = MagicMock()

        with (
            patch.object(_extension_module, "trex_contexts_instance", return_value=contexts),
            patch.object(_extension_module.commands, "register_commands"),
            patch.object(_extension_module, "_get_event_manager_instance", return_value=event_manager),
            patch.object(_extension_module, "_StageCraftSetup", return_value=setup),
        ):
            # Act
            extension.on_startup("lightspeed.trex.control.stagecraft")

        # Assert
        self.assertIs(setup, extension._setup)

    async def test_shutdown_unregisters_event_and_releases_stagecraft_setup(self):
        """Unregister the shutdown event and release StageCraft during extension shutdown."""
        # Arrange
        extension = TrexStageCraftControlExtension()
        setup = MagicMock()
        unsaved_event = MagicMock()
        event_manager = MagicMock()
        extension._setup = setup
        extension._unsaved_event = unsaved_event

        with (
            patch.object(_extension_module, "_get_event_manager_instance", return_value=event_manager),
            patch.object(_extension_module.commands, "unregister_commands"),
        ):
            # Act
            extension.on_shutdown()

        # Assert
        event_manager.unregister_event.assert_called_once_with(unsaved_event)
        setup.destroy.assert_called_once_with()
        self.assertIsNone(extension._unsaved_event)
        self.assertIsNone(extension._setup)

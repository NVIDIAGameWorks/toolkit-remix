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

import asyncio
import importlib
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import omni.kit.test

from lightspeed.trex.utils.widget import ingestcraft_loader as _loader

_INGEST_SETUP_MODULE = "lightspeed.trex.control.ingestcraft.setup"
_LOADER_MODULE = "lightspeed.trex.utils.widget.ingestcraft_loader"


def _make_runtime(stage=None, *, enabled=True):
    manager = MagicMock()
    manager.is_extension_enabled.return_value = enabled
    app = MagicMock()
    app.get_extension_manager.return_value = manager
    context = MagicMock()
    context.get_stage.return_value = stage
    return app, manager, context


class TestIngestCraftLoader(omni.kit.test.AsyncTestCase):
    """Tests lazy IngestCraft activation."""

    async def test_import_without_ingestcraft_setup_does_not_import_setup(self) -> None:
        """Keep the disabled IngestCraft setup module out of the loader import."""
        # Arrange
        sys.modules.pop(_LOADER_MODULE, None)
        sys.modules.pop(_INGEST_SETUP_MODULE, None)

        # Act
        importlib.import_module(_LOADER_MODULE)

        # Assert
        self.assertNotIn(_INGEST_SETUP_MODULE, sys.modules)

    async def test_ensure_ingestcraft_loaded_already_ready_returns_without_enabling_extensions(self) -> None:
        """Avoid enabling runtime extensions when IngestCraft is already ready."""
        # Arrange
        app, manager, context = _make_runtime(stage=MagicMock())

        with (
            patch.object(_loader.omni.kit.app, "get_app", return_value=app),
            patch.object(_loader.omni.usd, "get_context", return_value=context),
        ):
            # Act
            result = await _loader.ensure_ingestcraft_loaded()

        # Assert
        self.assertTrue(result)
        manager.set_extension_enabled.assert_not_called()

    async def test_ensure_ingestcraft_loaded_when_extensions_disabled_enables_runtime_extensions(self) -> None:
        """Enable each IngestCraft runtime extension that is not already active."""
        # Arrange
        app, manager, context = _make_runtime(stage=MagicMock(), enabled=False)

        with (
            patch.object(_loader.omni.kit.app, "get_app", return_value=app),
            patch.object(_loader.omni.usd, "get_context", return_value=context),
        ):
            # Act
            result = await _loader.ensure_ingestcraft_loaded()

        # Assert
        self.assertTrue(result)
        manager.set_extension_enabled.assert_has_calls(
            [
                call("lightspeed.trex.viewports.ingestcraft.bundle", True),
                call("lightspeed.trex.control.ingestcraft", True),
            ]
        )

    async def test_ensure_ingestcraft_loaded_when_stage_opened_event_fires_returns_true(self) -> None:
        """Return success when the IngestCraft context publishes its opened event."""
        # Arrange
        app, _, context = _make_runtime()
        callbacks = []
        context.get_stage_event_stream.return_value.create_subscription_to_pop.side_effect = (
            lambda callback, **_kwargs: callbacks.append(callback) or MagicMock()
        )

        with (
            patch.object(_loader.omni.kit.app, "get_app", return_value=app),
            patch.object(_loader.omni.usd, "get_context", return_value=context),
        ):
            # Act
            load_task = asyncio.create_task(_loader.ensure_ingestcraft_loaded())
            await asyncio.sleep(0)
            callbacks[0](SimpleNamespace(type=int(_loader.omni.usd.StageEventType.OPENED)))
            result = await load_task

        # Assert
        self.assertTrue(result)

    async def test_ensure_ingestcraft_loaded_when_stage_never_ready_logs_timeout(self) -> None:
        """Log a timeout when the IngestCraft stage never opens."""
        # Arrange
        app, _, context = _make_runtime()

        with (
            patch.object(_loader.omni.kit.app, "get_app", return_value=app),
            patch.object(_loader.omni.usd, "get_context", return_value=context),
            patch.object(_loader.carb, "log_error") as mock_log_error,
        ):
            # Act
            result = await _loader.ensure_ingestcraft_loaded(timeout_seconds=0)

        # Assert
        self.assertFalse(result)
        mock_log_error.assert_called_once_with(
            "[lightspeed.trex.utils.widget] Timed out loading IngestCraft extensions"
        )

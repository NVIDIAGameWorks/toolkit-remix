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

from unittest.mock import MagicMock, patch

import omni.kit.app
from omni.kit.test import AsyncTestCase

from lightspeed.event.autosave.core import (
    SETTINGS_ENABLED,
    SETTINGS_INTERVAL_SECONDS,
    AutoSaveCore,
)

_DIRTY_LAYER_ID = "omni:/test/mod.usda"


class TestAutoSaveCore(AsyncTestCase):
    async def setUp(self):
        self._settings = MagicMock()
        self._settings.get.side_effect = self._settings_get
        self._setting_values = {
            SETTINGS_ENABLED: True,
            SETTINGS_INTERVAL_SECONDS: 300,
        }

        self._mock_layer = MagicMock()
        self._mock_layer.anonymous = False

        self._layer_manager = MagicMock()
        self._layer_manager.get_layer.return_value = MagicMock()  # non-None → guard passes

        self._context = MagicMock()
        self._context.get_stage.return_value = MagicMock()

        self._notification_manager = MagicMock()

    def _settings_get(self, key, *args, **kwargs):
        return self._setting_values.get(key)

    def _make_core(self):
        with (
            patch("lightspeed.event.autosave.core.carb.settings.get_settings", return_value=self._settings),
            patch("lightspeed.event.autosave.core.omni.usd.get_context", return_value=self._context),
            patch("lightspeed.event.autosave.core._LayerManagerCore", return_value=self._layer_manager),
            patch(
                "lightspeed.event.autosave.core._nm.manager.NotificationManager",
                return_value=self._notification_manager,
            ),
        ):
            return AutoSaveCore()

    async def test_autosave_saves_dirty_layers_when_enabled(self):
        """_do_autosave saves each non-anonymous dirty layer when auto-save is enabled."""
        core = self._make_core()

        with (
            patch("lightspeed.event.autosave.core.carb.settings.get_settings", return_value=self._settings),
            patch("lightspeed.event.autosave.core.LayerUtils.get_dirty_layers", return_value=[_DIRTY_LAYER_ID]),
            patch("lightspeed.event.autosave.core.Sdf.Layer.FindOrOpen", return_value=self._mock_layer),
        ):
            await core._do_autosave()

        self._mock_layer.Save.assert_called_once()

    async def test_autosave_skips_when_disabled(self):
        """_do_autosave does nothing when the enabled setting is False."""
        self._setting_values[SETTINGS_ENABLED] = False
        core = self._make_core()

        with (
            patch("lightspeed.event.autosave.core.carb.settings.get_settings", return_value=self._settings),
            patch("lightspeed.event.autosave.core.LayerUtils.get_dirty_layers", return_value=[_DIRTY_LAYER_ID]),
            patch("lightspeed.event.autosave.core.Sdf.Layer.FindOrOpen", return_value=self._mock_layer),
        ):
            await core._do_autosave()

        self._mock_layer.Save.assert_not_called()

    async def test_autosave_skips_without_stage(self):
        """_do_autosave does nothing when no stage is loaded."""
        core = self._make_core()
        self._context.get_stage.return_value = None

        with (
            patch("lightspeed.event.autosave.core.carb.settings.get_settings", return_value=self._settings),
            patch("lightspeed.event.autosave.core.LayerUtils.get_dirty_layers", return_value=[_DIRTY_LAYER_ID]),
            patch("lightspeed.event.autosave.core.Sdf.Layer.FindOrOpen", return_value=self._mock_layer),
        ):
            await core._do_autosave()

        self._mock_layer.Save.assert_not_called()

    async def test_autosave_skips_without_project_layers(self):
        """_do_autosave does nothing when the capture or replacement layer is missing."""
        core = self._make_core()
        self._layer_manager.get_layer.return_value = None  # guard fails

        with (
            patch("lightspeed.event.autosave.core.carb.settings.get_settings", return_value=self._settings),
            patch("lightspeed.event.autosave.core.LayerUtils.get_dirty_layers", return_value=[_DIRTY_LAYER_ID]),
            patch("lightspeed.event.autosave.core.Sdf.Layer.FindOrOpen", return_value=self._mock_layer),
        ):
            await core._do_autosave()

        self._mock_layer.Save.assert_not_called()

    async def test_autosave_skips_anonymous_layers(self):
        """_do_autosave never calls Save() on anonymous (unsaved) layers."""
        core = self._make_core()
        self._mock_layer.anonymous = True

        with (
            patch("lightspeed.event.autosave.core.carb.settings.get_settings", return_value=self._settings),
            patch("lightspeed.event.autosave.core.LayerUtils.get_dirty_layers", return_value=[_DIRTY_LAYER_ID]),
            patch("lightspeed.event.autosave.core.Sdf.Layer.FindOrOpen", return_value=self._mock_layer),
        ):
            await core._do_autosave()

        self._mock_layer.Save.assert_not_called()

    async def test_autosave_posts_notification_after_saving(self):
        """A notification is posted when at least one layer was saved."""
        core = self._make_core()
        self._notification_manager.on_startup = MagicMock()

        with (
            patch("lightspeed.event.autosave.core.carb.settings.get_settings", return_value=self._settings),
            patch("lightspeed.event.autosave.core.LayerUtils.get_dirty_layers", return_value=[_DIRTY_LAYER_ID]),
            patch("lightspeed.event.autosave.core.Sdf.Layer.FindOrOpen", return_value=self._mock_layer),
        ):
            await core._do_autosave()

        self._notification_manager.post_notification.assert_called_once()

    async def test_autosave_no_notification_when_nothing_dirty(self):
        """No notification is posted when there are no dirty layers to save."""
        core = self._make_core()

        with (
            patch("lightspeed.event.autosave.core.carb.settings.get_settings", return_value=self._settings),
            patch("lightspeed.event.autosave.core.LayerUtils.get_dirty_layers", return_value=[]),
        ):
            await core._do_autosave()

        self._notification_manager.post_notification.assert_not_called()

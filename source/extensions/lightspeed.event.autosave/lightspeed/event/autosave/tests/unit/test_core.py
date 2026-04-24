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

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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
        self._mock_layer.identifier = _DIRTY_LAYER_ID

        self._layer_manager = MagicMock()
        self._layer_manager.get_layer_of_type.return_value = MagicMock()  # non-None → guard passes

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

    async def test_autosave_defaults_to_disabled_when_setting_is_missing(self):
        """AutoSaveCore defaults the enabled setting to False on first run."""
        del self._setting_values[SETTINGS_ENABLED]

        self._make_core()

        self._settings.set.assert_any_call(SETTINGS_ENABLED, False)

    async def test_autosave_prompts_before_saving_dirty_layers_when_enabled(self):
        """_do_autosave prompts instead of saving immediately when auto-save is enabled."""
        core = self._make_core()

        with (
            patch("lightspeed.event.autosave.core.carb.settings.get_settings", return_value=self._settings),
            patch("lightspeed.event.autosave.core.LayerUtils.get_dirty_layers", return_value=[_DIRTY_LAYER_ID]),
            patch("lightspeed.event.autosave.core.Sdf.Layer.FindOrOpen", return_value=self._mock_layer),
            patch(
                "lightspeed.event.autosave.core._PromptButtonInfo",
                side_effect=lambda label, handler=None: SimpleNamespace(label=label, handler=handler),
            ),
            patch("lightspeed.event.autosave.core._PromptManager.post_simple_prompt") as prompt_mock,
        ):
            await core._do_autosave()

        self._mock_layer.Save.assert_not_called()
        prompt_mock.assert_called_once()
        self.assertEqual("Save", prompt_mock.call_args.kwargs["ok_button_info"].label)
        self.assertEqual("Don't Save", prompt_mock.call_args.kwargs["middle_button_info"].label)
        self.assertEqual("Don't Ask Again This Session", prompt_mock.call_args.kwargs["middle_2_button_info"].label)

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
        self._layer_manager.get_layer_of_type.return_value = None  # guard fails

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

    async def test_autosave_save_prompt_handler_saves_layers(self):
        """The Save prompt handler saves the queued layers."""
        core = self._make_core()

        with (
            patch(
                "lightspeed.event.autosave.core._PromptButtonInfo",
                side_effect=lambda label, handler=None: SimpleNamespace(label=label, handler=handler),
            ),
            patch("lightspeed.event.autosave.core._PromptManager.post_simple_prompt") as prompt_mock,
        ):
            core._prompt_to_autosave([self._mock_layer])

        prompt_mock.call_args.kwargs["ok_button_info"].handler()

        self._mock_layer.Save.assert_called_once()
        self.assertFalse(core._autosave_prompt_open)

    async def test_autosave_dont_save_prompt_handler_skips_layers(self):
        """The Don't Save prompt handler leaves the queued layers untouched."""
        core = self._make_core()

        with (
            patch(
                "lightspeed.event.autosave.core._PromptButtonInfo",
                side_effect=lambda label, handler=None: SimpleNamespace(label=label, handler=handler),
            ),
            patch("lightspeed.event.autosave.core._PromptManager.post_simple_prompt") as prompt_mock,
        ):
            core._prompt_to_autosave([self._mock_layer])

        prompt_mock.call_args.kwargs["middle_button_info"].handler()

        self._mock_layer.Save.assert_not_called()
        self.assertFalse(core._autosave_prompt_open)

    async def test_autosave_dont_ask_again_handler_saves_layers_and_suppresses_prompt(self):
        """The Don't Ask Again This Session prompt handler saves and suppresses prompts."""
        core = self._make_core()

        with (
            patch(
                "lightspeed.event.autosave.core._PromptButtonInfo",
                side_effect=lambda label, handler=None: SimpleNamespace(label=label, handler=handler),
            ),
            patch("lightspeed.event.autosave.core._PromptManager.post_simple_prompt") as prompt_mock,
        ):
            core._prompt_to_autosave([self._mock_layer])

        prompt_mock.call_args.kwargs["middle_2_button_info"].handler()

        self._mock_layer.Save.assert_called_once()
        self.assertTrue(core._autosave_prompt_suppressed_for_session)
        self.assertFalse(core._autosave_prompt_open)

    async def test_autosave_saves_without_prompt_when_prompt_suppressed_for_session(self):
        """_do_autosave saves immediately once prompts are suppressed for the session."""
        core = self._make_core()
        core._autosave_prompt_suppressed_for_session = True

        with (
            patch("lightspeed.event.autosave.core.carb.settings.get_settings", return_value=self._settings),
            patch("lightspeed.event.autosave.core.LayerUtils.get_dirty_layers", return_value=[_DIRTY_LAYER_ID]),
            patch("lightspeed.event.autosave.core.Sdf.Layer.FindOrOpen", return_value=self._mock_layer),
            patch("lightspeed.event.autosave.core._PromptManager.post_simple_prompt") as prompt_mock,
        ):
            await core._do_autosave()

        self._mock_layer.Save.assert_called_once()
        prompt_mock.assert_not_called()

    async def test_autosave_posts_notification_after_saving(self):
        """A notification is posted when at least one layer was saved."""
        core = self._make_core()
        self._notification_manager.on_startup = MagicMock()

        core._save_layers([self._mock_layer])

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

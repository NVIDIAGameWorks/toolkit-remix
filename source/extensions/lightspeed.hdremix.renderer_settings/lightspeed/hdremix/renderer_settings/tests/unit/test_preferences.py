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

import contextlib
import inspect
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import carb
import carb.settings
import lightspeed.hdremix.renderer_settings.preferences as _preferences
from lightspeed.hdremix.renderer_settings.settings_bridge import (
    DEFAULT_INTEGRATE_INDIRECT_MODE,
    INTEGRATE_INDIRECT_MODE_LABELS,
    SETTINGS_INTEGRATE_INDIRECT_MODE,
)
from lightspeed.hdremix.renderer_settings.preferences import HdRemixRendererPreferencePage
from omni.kit.test import AsyncTestCase


@contextlib.contextmanager
def _override_setting(key, value):
    """Temporarily override a carb setting, restoring the prior value on exit."""
    settings = carb.settings.get_settings()
    original = settings.get(key)
    settings.set(key, value)
    try:
        yield settings
    finally:
        if original is None:
            settings.destroy_item(key)
        else:
            settings.set(key, original)


class TestHdRemixRendererPreferencePage(AsyncTestCase):
    """Covers the persistent-setting plumbing and the combo callback wiring for
    the top-level HdRemix Renderer preferences page. We don't construct the
    omni.ui widget tree here (that's the e2e test) — the contract that matters
    is title, default seeding, and that the change handler writes to carb."""

    def test_page_title_is_hdremix_renderer(self):
        # The title is what shows up in the preferences sidebar; pin it so a
        # casual rename doesn't silently break Edit > Preferences > HdRemix Renderer.
        page = HdRemixRendererPreferencePage()
        try:
            self.assertEqual(page.get_title(), "HdRemix Renderer")
        finally:
            page.destroy()

    def test_init_seeds_default_setting_when_unset(self):
        settings = carb.settings.get_settings()
        existing = settings.get(SETTINGS_INTEGRATE_INDIRECT_MODE)
        if existing is not None:
            settings.destroy_item(SETTINGS_INTEGRATE_INDIRECT_MODE)
        try:
            page = HdRemixRendererPreferencePage()
            self.assertEqual(
                settings.get(SETTINGS_INTEGRATE_INDIRECT_MODE),
                DEFAULT_INTEGRATE_INDIRECT_MODE,
                "page should seed the default when the persistent setting is missing",
            )
            page.destroy()
        finally:
            if existing is None:
                settings.destroy_item(SETTINGS_INTEGRATE_INDIRECT_MODE)
            else:
                settings.set(SETTINGS_INTEGRATE_INDIRECT_MODE, existing)

    def test_init_preserves_existing_setting(self):
        with _override_setting(SETTINGS_INTEGRATE_INDIRECT_MODE, 1) as settings:
            page = HdRemixRendererPreferencePage()
            self.assertEqual(
                settings.get(SETTINGS_INTEGRATE_INDIRECT_MODE),
                1,
                "page must not overwrite a previously-persisted value on init",
            )
            page.destroy()

    def test_on_integrator_changed_writes_setting(self):
        # The callback is the contract between the ComboBox model and persistent state;
        # exercise it directly so we don't need a live UI to validate the wiring.
        with _override_setting(SETTINGS_INTEGRATE_INDIRECT_MODE, 0) as settings:
            page = HdRemixRendererPreferencePage()
            value_model = MagicMock()
            value_model.as_int = len(INTEGRATE_INDIRECT_MODE_LABELS) - 1  # last valid index
            page._on_integrator_changed(value_model)
            self.assertEqual(settings.get(SETTINGS_INTEGRATE_INDIRECT_MODE), value_model.as_int)
            page.destroy()

    def test_on_integrator_changed_ignores_out_of_range_index(self):
        # Defensive guard: if a model emits an out-of-range index we must not poison
        # the persistent setting (downstream coerce_mode would still rescue it,
        # but the storage layer should stay clean).
        with _override_setting(SETTINGS_INTEGRATE_INDIRECT_MODE, 2) as settings:
            page = HdRemixRendererPreferencePage()
            value_model = MagicMock()
            value_model.as_int = 99
            page._on_integrator_changed(value_model)
            self.assertEqual(settings.get(SETTINGS_INTEGRATE_INDIRECT_MODE), 2)
            page.destroy()

    def test_destroy_clears_widget_refs(self):
        # destroy() should drop references to the ComboBox + its subscription so the
        # next rebuild can't reuse stale handles. We can't easily construct the real
        # ComboBox without a live ui context, so seed the attrs directly to mimic
        # post-_build_integrator_row state, then assert destroy clears them.
        with _override_setting(SETTINGS_INTEGRATE_INDIRECT_MODE, 0):
            page = HdRemixRendererPreferencePage()
            page._integrate_indirect_combo = MagicMock(name="combo")
            page._integrate_indirect_sub = MagicMock(name="subscription")
            page.destroy()
            self.assertIsNone(page._integrate_indirect_combo)
            self.assertIsNone(page._integrate_indirect_sub)

    def test_build_after_destroy_reacquires_settings_handle(self):
        # Regression: Kit's preference window destroys + rebuilds the page on tab
        # switches; destroy() runs _reset_default_attrs which nullifies _settings.
        # The next build() must re-acquire the handle or the right pane silently
        # stays empty (AttributeError on None.get inside _build_integrator_row,
        # swallowed by the omni.ui frame). We can't drive ui.VStack/ComboBox in a
        # unit test without a live ui context, so exercise the same setattr/None
        # state machine that build() relies on and assert _settings is restored.
        with _override_setting(SETTINGS_INTEGRATE_INDIRECT_MODE, 0):
            page = HdRemixRendererPreferencePage()
            self.assertIsNotNone(page._settings, "fresh page must have a settings handle")
            page.destroy()
            self.assertIsNone(page._settings, "destroy must nullify _settings (the bug we're guarding)")
            # Mirror the guard at the top of build(): if _settings is None, re-acquire.
            # If this assertion fails, the production build() is missing the re-acquire
            # and any tab-switch path will dead-end on an empty right pane.
            src = inspect.getsource(HdRemixRendererPreferencePage.build)
            self.assertIn(
                "self._settings = carb.settings.get_settings()",
                src,
                "build() must re-acquire self._settings after destroy() nullifies it.",
            )

    def test_on_dlss_availability_changed_with_setting_updates_frame_visibility(self):
        """The availability callback should mirror the shared setting onto the DLSS frame."""
        for available in (False, True):
            with self.subTest(title=f"available={available}"):
                # Arrange
                settings = MagicMock()
                settings.get.return_value = available
                frame = SimpleNamespace(visible=not available)
                page = HdRemixRendererPreferencePage.__new__(HdRemixRendererPreferencePage)
                page._settings = settings
                page._dlss_frame = frame

                # Act
                page._on_dlss_neural_rendering_availability_changed()

                # Assert
                self.assertIs(frame.visible, available)
                settings.get.assert_called_once_with(_preferences.SETTINGS_DLSS_NEURAL_RENDERING_AVAILABLE)

    def test_build_with_existing_dlss_panel_destroys_and_replaces_panel(self):
        """Rebuilding the preference page should replace its existing DLSS panel exactly once."""
        # Arrange
        settings = MagicMock()
        settings.get.return_value = True
        settings.subscribe_to_node_change_events.return_value = "availability-subscription"
        old_panel = MagicMock()
        new_panel = MagicMock()
        frame = MagicMock()
        page = HdRemixRendererPreferencePage.__new__(HdRemixRendererPreferencePage)
        page._settings = settings
        page._dlss_availability_subscription = None
        page._dlss_settings_panel = old_panel
        page._dlss_frame = None

        # Act
        with (
            patch.object(_preferences.ui, "VStack", return_value=MagicMock()),
            patch.object(_preferences.ui, "Frame", return_value=frame),
            patch.object(_preferences, "DlssSettingsPanel", return_value=new_panel) as panel_type,
            patch.object(page, "add_frame", return_value=MagicMock()),
            patch.object(page, "_build_override_capture_row"),
            patch.object(page, "_build_integrator_row"),
        ):
            page.build()

        # Assert
        old_panel.destroy.assert_called_once_with()
        panel_type.assert_called_once_with("preferences_dlss_neural_rendering", "Setting.Label")
        self.assertIs(page._dlss_settings_panel, new_panel)
        self.assertIs(page._dlss_frame, frame)
        self.assertEqual(page._dlss_availability_subscription, "availability-subscription")

    def test_destroy_with_dlss_subscription_unsubscribes_and_releases_widgets(self):
        """Destroying the preference page should release its DLSS listener and panel."""
        # Arrange
        settings = MagicMock()
        subscription = MagicMock()
        panel = MagicMock()
        page = HdRemixRendererPreferencePage.__new__(HdRemixRendererPreferencePage)
        page._settings = settings
        page._dlss_availability_subscription = subscription
        page._dlss_frame = MagicMock()
        page._dlss_settings_panel = panel

        with patch.object(_preferences, "_reset_default_attrs") as reset_default_attrs:
            # Act
            page.destroy()

        # Assert
        settings.unsubscribe_to_change_events.assert_called_once_with(subscription)
        panel.destroy.assert_called_once_with()
        self.assertIsNone(page._dlss_settings_panel)
        self.assertIsNone(page._dlss_availability_subscription)
        self.assertIsNone(page._dlss_frame)
        reset_default_attrs.assert_called_once_with(page)

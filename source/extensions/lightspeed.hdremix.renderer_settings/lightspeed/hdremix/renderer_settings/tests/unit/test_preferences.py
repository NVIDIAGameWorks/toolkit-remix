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
from unittest.mock import MagicMock

import carb
import carb.settings
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

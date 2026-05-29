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

__all__ = ("TestHdRemixRendererE2E",)

from unittest.mock import patch

import carb.settings
import omni.kit.app
import omni.kit.test
import omni.kit.ui_test
import omni.kit.window.preferences
from lightspeed.hdremix.renderer_settings.settings_bridge import (
    DEFAULT_INTEGRATE_INDIRECT_MODE,
    INTEGRATE_INDIRECT_MODE_LABELS,
    SETTINGS_INTEGRATE_INDIRECT_MODE,
)
from omni.kit.window.preferences import get_page_list

_HDREMIX_PATCH_TARGET = "lightspeed.hdremix.renderer_settings.settings_bridge._hdremix_set_configvar"


class TestHdRemixRendererE2E(omni.kit.test.AsyncTestCase):
    """End-to-end verification against the real preferences extension.

    Runs with the actual ``omni.kit.window.preferences`` loaded and asserts that
    our top-level "HdRemix Renderer" page is registered alongside (NOT inside)
    the built-in Viewport page. Most assertions read the page list directly —
    a robust signal that's stable across Kit versions. One additional test drives
    the actual Preferences dialog to pin that the entry also visibly renders,
    accepting the widget-tree brittleness as the cost of catching cases where
    the page is registered but never painted.
    """

    async def setUp(self):
        self._settings = carb.settings.get_settings()
        self._original_mode = self._settings.get(SETTINGS_INTEGRATE_INDIRECT_MODE)
        # Let the extension finish on_startup before we inspect state.
        for _ in range(5):
            await omni.kit.app.get_app().next_update_async()

    async def tearDown(self):
        if self._original_mode is None:
            self._settings.destroy_item(SETTINGS_INTEGRATE_INDIRECT_MODE)
        else:
            self._settings.set(SETTINGS_INTEGRATE_INDIRECT_MODE, self._original_mode)

    async def test_hdremix_renderer_present_and_kit_viewport_page_build_is_stubbed(self):
        # The extension does two things on startup:
        #   1. Registers a top-level "HdRemix Renderer" page (must be present).
        #   2. Stubs Kit's built-in "Viewport" page ``build`` so its no-op
        #      settings (Auto Frame, toolbar visibility, Area Select Occluded)
        #      stop misleading users — without UNregistering the page, because
        #      omni.kit.viewport.menubar.settings looks the page up by title
        #      and errors if it's missing.
        # Both contracts pinned here: HdRemix Renderer present, Viewport still
        # registered, Viewport's build is OURS (not kit's original).
        pages_by_title = {page.get_title(): page for page in get_page_list()}
        self.assertIn(
            "HdRemix Renderer",
            pages_by_title,
            "Expected a top-level 'HdRemix Renderer' entry in the preferences sidebar.",
        )
        self.assertIn(
            "Viewport",
            pages_by_title,
            "Kit's 'Viewport' page must stay registered — the viewport menubar's "
            "'Preferences' navigation looks it up by title and errors if missing.",
        )

        viewport_page = pages_by_title["Viewport"]
        # The kit ViewportPreferences class lives under omni.kit.window.preferences.scripts.pages.viewport_page;
        # the bound build method's __qualname__ starts with that class name when unmodified.
        # After our wrap, ``build`` is an args-absorbing lambda defined inside
        # HdRemixRendererExtension._wrap_viewport_page_build, so the lambda's
        # __qualname__ is "HdRemixRendererExtension._wrap_viewport_page_build.<locals>.<lambda>".
        build_qualname = getattr(viewport_page.build, "__qualname__", "")
        self.assertIn(
            "HdRemixRendererExtension._wrap_viewport_page_build",
            build_qualname,
            f"Viewport page build should be our redirect stub, got: {build_qualname!r}",
        )

    async def test_hdremix_renderer_entry_visible_in_preferences_dialog(self):
        # Complements the get_page_list() assertion above: drives the actual
        # Preferences window and checks our entry renders in the sidebar. Catches
        # a regression where the page is registered programmatically but never
        # painted (e.g., extension on_startup silently failed before our wrap).
        inst = omni.kit.window.preferences.get_instance()
        self.assertIsNotNone(inst, "omni.kit.window.preferences is not loaded")
        inst.show_preferences_window()
        try:
            for _ in range(10):
                await omni.kit.app.get_app().next_update_async()
            await omni.kit.ui_test.human_delay(10)

            labels = omni.kit.ui_test.find_all("Preferences//Frame/**/Label[*]")
            visible_titles = [lbl.widget.text for lbl in labels if lbl.widget.visible]
            self.assertIn(
                "HdRemix Renderer",
                visible_titles,
                f"'HdRemix Renderer' entry not visible in the Preferences dialog sidebar. "
                f"Visible labels: {sorted({t for t in visible_titles if t})}",
            )
        finally:
            inst.hide_preferences_window()
            await omni.kit.ui_test.human_delay(10)

    async def test_persistent_setting_seeded_with_default(self):
        # The page's __init__ seeds the setting if missing. This pins the carb
        # setting path itself — if a typo changes the path, downstream UI breaks
        # silently and only this test catches it.
        value = self._settings.get(SETTINGS_INTEGRATE_INDIRECT_MODE)
        self.assertIsNotNone(value, f"Persistent setting {SETTINGS_INTEGRATE_INDIRECT_MODE} not seeded by startup.")
        self.assertIn(
            value,
            range(len(INTEGRATE_INDIRECT_MODE_LABELS)),
            f"Persistent setting value {value!r} is outside the valid integrator range "
            f"0..{len(INTEGRATE_INDIRECT_MODE_LABELS) - 1}.",
        )

    async def test_carb_setting_change_drives_running_extension_to_push_to_hdremix(self):
        # End-to-end log-spy: the extension is already loaded (test bootstrap
        # ran on_startup), its HdRemixSettingsBridge is subscribed to the persistent
        # setting. Flip the setting at the carb level and assert the running bridge
        # actually pushed the new value through to hdremix_set_configvar — proving
        # the carb -> bridge -> dxvk-remix path is live, not just unit-mockable.
        # Unit tests cover the install-time push; this one covers the change-time
        # push that happens in the running extension context.
        current = self._settings.get(SETTINGS_INTEGRATE_INDIRECT_MODE)
        # Pick a target that's guaranteed to differ from the current value so a
        # change-notice actually fires (carb skips notices when value is unchanged).
        target = 0 if current != 0 else 1
        with patch(_HDREMIX_PATCH_TARGET) as mock_set:
            self._settings.set(SETTINGS_INTEGRATE_INDIRECT_MODE, target)
            # Pump a few frames so the carb change-event subscription has time
            # to fire on the running bridge and reach _push_integrate_indirect_mode.
            for _ in range(3):
                await omni.kit.app.get_app().next_update_async()
            mock_set.assert_any_call("rtx.integrateIndirectMode", str(target))

    async def test_default_matches_dxvk_remix_default(self):
        # If anyone changes DEFAULT_INTEGRATE_INDIRECT_MODE away from dxvk-remix's
        # native default (NRC=2), users without prior config get a surprise on first
        # launch. Lock that in here so a casual constant edit fails this test.
        self.assertEqual(
            DEFAULT_INTEGRATE_INDIRECT_MODE,
            2,
            "DEFAULT_INTEGRATE_INDIRECT_MODE drift: should match dxvk-remix's NRC=2 default.",
        )
        self.assertEqual(
            INTEGRATE_INDIRECT_MODE_LABELS[2],
            "RTX Neural Radiance Cache",
            "Index 2 should map to RTX Neural Radiance Cache (matches dxvk-remix IntegrateIndirectMode enum + runtime overlay label).",
        )

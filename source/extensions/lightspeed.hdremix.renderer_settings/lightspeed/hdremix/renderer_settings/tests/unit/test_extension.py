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

__all__ = ("TestHdRemixRendererExtension",)

from unittest.mock import MagicMock, patch

from lightspeed.hdremix.renderer_settings.extension import HdRemixRendererExtension
from omni.kit.test import AsyncTestCase


def _make_page(title: str):
    page = MagicMock(name=f"page<{title}>")
    page.get_title.return_value = title
    # Capture the original 'build' so tests can assert against it being preserved.
    page.build = MagicMock(name=f"original_build<{title}>")
    return page


class TestHdRemixRendererExtension(AsyncTestCase):
    """Pins the stub-then-restore contract for Kit's built-in 'Viewport'
    preferences page.

    The page is left registered (kit's viewport-menubar 'Preferences' navigation
    looks the page up by title and errors loudly if it's missing) but its
    ``build`` is replaced with a small redirect notice — its real settings
    (Auto Frame, toolbar visibility, Area Select Occluded) are no-ops against
    the customized Remix viewport. On shutdown the original ``build`` is restored
    so a hot-disable of our extension doesn't permanently mutate kit state.
    """

    def _patch_targets(self):
        return (
            patch("lightspeed.hdremix.renderer_settings.extension.register_page"),
            patch("lightspeed.hdremix.renderer_settings.extension.unregister_page"),
            patch("lightspeed.hdremix.renderer_settings.extension.get_page_list"),
            patch("lightspeed.hdremix.renderer_settings.extension.HdRemixRendererPreferencePage"),
            patch("lightspeed.hdremix.renderer_settings.extension.HdRemixSettingsBridge"),
        )

    async def test_on_startup_wraps_kit_viewport_page_build_without_unregistering(self):
        viewport_page = _make_page("Viewport")
        original_build = viewport_page.build
        other_page = _make_page("Stage")
        patches = self._patch_targets()
        with (
            patches[0],
            patches[1] as unregister_mock,
            patches[2] as get_pages_mock,
            patches[3],
            patches[4],
        ):
            get_pages_mock.return_value = [other_page, viewport_page]
            ext = HdRemixRendererExtension()
            try:
                ext.on_startup("lightspeed.hdremix.renderer_settings-1.0.0")

                # Page must NOT be unregistered — kit's viewport menubar still navigates to it.
                kit_page_unregisters = [
                    c for c in unregister_mock.call_args_list if c.args and c.args[0] is viewport_page
                ]
                self.assertEqual(
                    kit_page_unregisters, [], "Viewport page was unregistered; kit menu lookup will error."
                )

                # Build was wrapped: the page now points at our stub, and the original is saved.
                self.assertIs(ext._viewport_page, viewport_page)
                self.assertIs(ext._original_viewport_build, original_build)
                self.assertIsNot(viewport_page.build, original_build, "build should be replaced by our redirect stub")

                # Unrelated pages (e.g. 'Stage') must be untouched.
                self.assertIsNot(other_page.build, ext._build_viewport_stub)
            finally:
                ext.on_shutdown()

    async def test_on_shutdown_restores_original_viewport_build(self):
        viewport_page = _make_page("Viewport")
        original_build = viewport_page.build
        patches = self._patch_targets()
        with (
            patches[0],
            patches[1],
            patches[2] as get_pages_mock,
            patches[3],
            patches[4],
        ):
            get_pages_mock.return_value = [viewport_page]
            ext = HdRemixRendererExtension()
            ext.on_startup("lightspeed.hdremix.renderer_settings-1.0.0")
            self.assertIsNot(viewport_page.build, original_build)  # sanity: still wrapped

            ext.on_shutdown()

            self.assertIs(
                viewport_page.build,
                original_build,
                "shutdown must restore the original kit build so kit stays clean on hot-disable",
            )

    async def test_on_startup_with_no_viewport_page_is_a_noop(self):
        # If Kit ever stops registering a built-in Viewport page (or our load
        # order changes), we must NOT try to wrap nothing.
        patches = self._patch_targets()
        with (
            patches[0],
            patches[1],
            patches[2] as get_pages_mock,
            patches[3],
            patches[4],
        ):
            get_pages_mock.return_value = [_make_page("Stage")]
            ext = HdRemixRendererExtension()
            try:
                ext.on_startup("lightspeed.hdremix.renderer_settings-1.0.0")
                self.assertIsNone(ext._viewport_page)
                self.assertIsNone(ext._original_viewport_build)
            finally:
                ext.on_shutdown()

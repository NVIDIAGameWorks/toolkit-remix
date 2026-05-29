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

import carb
import omni.ext
import omni.ui as ui
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.kit.window.preferences import get_page_list, register_page, unregister_page

from .preferences import HdRemixRendererPreferencePage
from .settings_bridge import HdRemixSettingsBridge

_KIT_VIEWPORT_PAGE_TITLE = "Viewport"
_VIEWPORT_STUB_MESSAGE = (
    "Kit's built-in Viewport settings (Auto Frame, viewport-toolbar visibility, "
    "Area Select Occluded Objects) are no-ops against the customized Remix viewport.\n\n"
    "For renderer controls that actually take effect, see Edit > Preferences > HdRemix Renderer."
)


class HdRemixRendererExtension(omni.ext.IExt):
    """Registers the HdRemix Renderer preferences page and bridges persistent settings to dxvk-remix."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_attr = {
            "_bridge": None,
            "_preferences_page": None,
            "_viewport_page": None,
            "_original_viewport_build": None,
        }
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

    def on_startup(self, ext_id):
        carb.log_info("[lightspeed.hdremix.renderer_settings] startup")
        # Register the preferences page first so it shows up even if the bridge start
        # below ever fails — the UI alone is still useful for inspecting state.
        try:
            self._preferences_page = HdRemixRendererPreferencePage()
            register_page(self._preferences_page)
        except Exception as exc:  # noqa: BLE001 - never abort startup on UI registration failure
            carb.log_error(f"[lightspeed.hdremix.renderer_settings] failed to register preferences page: {exc}")

        # Stub out Kit's built-in "Viewport" preferences page content. Its settings
        # (Auto Frame, viewport-toolbar visibility, Area Select Occluded Objects) are
        # no-ops against the customized Remix viewport, so we replace the page's
        # ``build`` with a one-line redirect notice. The page stays in the registry
        # so the viewport menubar's "Preferences" navigation
        # (omni.kit.viewport.menubar.settings -> page lookup by title "Viewport")
        # keeps working — unregistering the page caused that lookup to spam errors.
        try:
            self._wrap_viewport_page_build()
        except Exception as exc:  # noqa: BLE001 - stub is best-effort, never fatal
            carb.log_error(f"[lightspeed.hdremix.renderer_settings] failed to stub Viewport page: {exc}")

        try:
            self._bridge = HdRemixSettingsBridge()
            self._bridge.start()
        except Exception as exc:  # noqa: BLE001 - never abort startup on bridge start failure
            carb.log_error(f"[lightspeed.hdremix.renderer_settings] failed to start renderer bridge: {exc}")

    def _wrap_viewport_page_build(self):
        for page in get_page_list():
            if page.get_title() == _KIT_VIEWPORT_PAGE_TITLE:
                self._viewport_page = page
                break
        if self._viewport_page is None:
            return
        self._original_viewport_build = self._viewport_page.build
        # Args-absorbing closure: bound method assignment is robust against `page.build()`
        # but would TypeError if the framework ever calls with an explicit page argument
        # (e.g. ``getattr(page, "build")(page)``). The closure swallows anything.
        self._viewport_page.build = lambda *_a, **_kw: self._build_viewport_stub()
        carb.log_info(
            f"[lightspeed.hdremix.renderer_settings] stubbed built-in {type(self._viewport_page).__name__} "
            "content (its settings do not apply to the customized Remix viewport)"
        )

    def _build_viewport_stub(self) -> None:
        with ui.VStack(height=0, spacing=8):
            ui.Spacer(height=4)
            ui.Label(
                _VIEWPORT_STUB_MESSAGE,
                style_type_name_override="Setting.Label",
                word_wrap=True,
                alignment=ui.Alignment.LEFT_TOP,
            )

    def on_shutdown(self):
        carb.log_info("[lightspeed.hdremix.renderer_settings] shutdown")
        # Restore kit's Viewport page build so Kit is clean if our extension is hot-disabled
        # (Extensions Manager) rather than the whole app exiting.
        if self._viewport_page is not None and self._original_viewport_build is not None:
            try:
                self._viewport_page.build = self._original_viewport_build
            except Exception as exc:  # noqa: BLE001 - shutdown is best-effort
                carb.log_warn(f"[lightspeed.hdremix.renderer_settings] failed to restore Viewport build: {exc}")
        if self._preferences_page is not None:
            unregister_page(self._preferences_page)
            self._preferences_page.destroy()
        if self._bridge is not None:
            self._bridge.stop()
            self._bridge.destroy()
        _reset_default_attrs(self)

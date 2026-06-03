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

import carb
import carb.settings
import omni.kit.app
from lightspeed.hydra.remix.core import hdremix_set_configvar as _hdremix_set_configvar
from lightspeed.hydra.remix.core.extern import load_remix_extern_async as _load_remix_extern_async
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

SETTINGS_INTEGRATE_INDIRECT_MODE = "/persistent/exts/lightspeed.hdremix.renderer_settings/integrateIndirectMode"
# Pre-rename key; carried for one-shot migration on first startup of the renamed extension
# (REMIX-5483). Users who toggled the GI integrator before the rename had their preference
# stored under the old path; we copy it forward once so they don't lose their choice.
_LEGACY_SETTINGS_INTEGRATE_INDIRECT_MODE = "/persistent/exts/lightspeed.event.hdremix_renderer/integrateIndirectMode"
# Persistent marker for the one-shot legacy migration. Gating on this — instead of on
# "new key is None" — is required because extension.toml's [settings] block pre-seeds the
# new key with the TOML default before Python runs, so the new key is *always* set by the
# time migration is invoked. A value-based check also can't distinguish "TOML default
# applied" from "user explicitly chose the default value", which would re-migrate over
# their choice. The marker is set after a single migration attempt regardless of whether
# legacy data was found.
_SETTINGS_LEGACY_MIGRATION_DONE = "/persistent/exts/lightspeed.hdremix.renderer_settings/legacyMigrationDone"
# When True, push the persisted integrator to dxvk-remix on startup and on every
# user toggle, overriding any value the loaded capture's preset would otherwise
# apply. When False (default), we leave the runtime alone -- the capture's
# preset wins -- and the combo in Preferences just records the user's preference
# for the next time this checkbox is on. This addresses Nicolas's review:
# previously the global preference was always sticky and silently overrode the
# per-capture integrator that designers expect when loading a new capture.
SETTINGS_OVERRIDE_CAPTURE_INTEGRATOR = "/persistent/exts/lightspeed.hdremix.renderer_settings/overrideCaptureIntegrator"
DEFAULT_OVERRIDE_CAPTURE_INTEGRATOR = False
# Indices match dxvk-remix's IntegrateIndirectMode enum (src/dxvk/rtx_render/rtx_options.h).
# Label strings mirror what the dxvk-remix runtime shows in its "Integrate Indirect
# Illumination Mode" combo so the Kit preferences page reads the same as the in-game
# overlay. Source-verified against RemixGui::ComboWithKey<IntegrateIndirectMode> in
# src/dxvk/imgui/dxvk_imgui.cpp — only index 2 carries the "RTX " prefix.
INTEGRATE_INDIRECT_MODE_LABELS = ["Importance Sampled", "ReSTIR GI", "RTX Neural Radiance Cache"]
DEFAULT_INTEGRATE_INDIRECT_MODE = 2  # NeuralRadianceCache; matches the dxvk-remix default
_RTX_OPTION_INTEGRATE_INDIRECT_MODE = "rtx.integrateIndirectMode"
# integrateIndirectMode has the UserSettings flag in dxvk-remix; when graphicsPreset != Custom
# the Quality layer overrides the User layer that hdremix_set_configvar writes to, and our toggle
# silently does nothing visible. Force preset to Custom (value 4 in the GraphicsPreset enum) so
# the User layer write wins. See dxvk-remix rtx_option.cpp:842-848 and rtx_options.h:75 (the
# GraphicsPreset enum).
_RTX_OPTION_GRAPHICS_PRESET = "rtx.graphicsPreset"
_RTX_GRAPHICS_PRESET_CUSTOM = "4"


def coerce_mode(value: object) -> int:
    """Coerce a raw carb setting value into a valid integrator mode index, falling back to the NRC default."""
    if value is None:
        return DEFAULT_INTEGRATE_INDIRECT_MODE
    try:
        mode = int(value)
    except (TypeError, ValueError):
        return DEFAULT_INTEGRATE_INDIRECT_MODE
    if 0 <= mode < len(INTEGRATE_INDIRECT_MODE_LABELS):
        return mode
    return DEFAULT_INTEGRATE_INDIRECT_MODE


class HdRemixSettingsBridge:
    """Relays persistent HdRemix renderer settings to the dxvk-remix runtime.

    NOTE: Named ``Settings`` to disambiguate from dxvk-remix's own runtime ``bridge``
    component (the D3D9 -> Vulkan translation layer shipped in bridge.dll). This class
    has nothing to do with that; it's the carb-settings -> hdremix_set_configvar relay.

    Subscribes to changes on the persistent carb settings and -- gated by the
    ``overrideCaptureIntegrator`` flag -- pushes them to dxvk-remix through
    ``hdremix_set_configvar`` so the running renderer updates live without a re-capture.
    When the override flag is False (default), runtime pushes are skipped on startup,
    on dropdown changes, and on the flag flipping back off; the dropdown then only
    records the user's preference and the loaded capture's preset wins. Not tied to
    stage lifecycle: GI integrator preference is an app-scoped renderer config, so
    start()/stop() are driven directly from the extension's on_startup/on_shutdown.
    """

    def __init__(self):
        # _reset_default_attrs() walks this dict on destroy() and sets each named
        # attribute back to the listed value, so anything we hold on to needs to be
        # listed here or it won't be released. _settings is the carb settings root;
        # explicitly nulling it on destroy is fine — it's just a global handle.
        self.default_attr = {
            "_settings": None,
            "_integrate_indirect_sub": None,
            "_override_capture_sub": None,
            "_startup_push_task": None,
        }
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._settings = carb.settings.get_settings()
        self._migrate_legacy_setting()

    def _migrate_legacy_setting(self):
        """One-shot copy of the pre-rename persistent value to the new key.

        Before this extension was renamed from ``lightspeed.event.hdremix_renderer`` to
        ``lightspeed.hdremix.renderer_settings`` (REMIX-5483), the GI-integrator preference
        was persisted under the old key. Returning users would otherwise lose their saved
        choice — extension.toml pre-seeds the new key with the TOML default before Python
        runs, so a naive ``if new_key is None`` gate would always short-circuit.

        Gate on the dedicated marker key so the copy happens at most once across all
        launches and is independent of the integrator value (avoids re-migrating over a
        user who explicitly picks the default value under the new key).
        """
        if self._settings.get(_SETTINGS_LEGACY_MIGRATION_DONE):
            return
        legacy = self._settings.get(_LEGACY_SETTINGS_INTEGRATE_INDIRECT_MODE)
        if legacy is not None:
            self._settings.set(SETTINGS_INTEGRATE_INDIRECT_MODE, legacy)
            carb.log_info(
                f"[hdremix_renderer] migrated legacy integrateIndirectMode={legacy} "
                f"from {_LEGACY_SETTINGS_INTEGRATE_INDIRECT_MODE} to the new key."
            )
        self._settings.set(_SETTINGS_LEGACY_MIGRATION_DONE, True)

    def start(self):
        self.stop()
        self._integrate_indirect_sub = self._settings.subscribe_to_node_change_events(
            SETTINGS_INTEGRATE_INDIRECT_MODE, self._on_integrate_indirect_mode_changed
        )
        # Also react to the override flag flipping mid-session: enabling it must apply
        # immediately, not wait for the next dropdown change or a restart. The push logic
        # lives here in the bridge (not the preferences UI handler) so any writer of the
        # setting stays in sync, not just the checkbox widget.
        self._override_capture_sub = self._settings.subscribe_to_node_change_events(
            SETTINGS_OVERRIDE_CAPTURE_INTEGRATOR, self._on_override_capture_changed
        )
        # Defer the initial push until the next frame: hdremix_set_configvar requires the HdRemix
        # delegate to be initialized, which may not yet be the case during extension startup.
        # Without this, an exception in start() would abort on_startup and prevent the
        # preferences page from registering at all.
        self._startup_push_task = asyncio.ensure_future(self._deferred_initial_push())

    def stop(self):
        if self._startup_push_task is not None and not self._startup_push_task.done():
            self._startup_push_task.cancel()
        self._startup_push_task = None
        if self._integrate_indirect_sub is not None:
            self._settings.unsubscribe_to_change_events(self._integrate_indirect_sub)
            self._integrate_indirect_sub = None
        if self._override_capture_sub is not None:
            self._settings.unsubscribe_to_change_events(self._override_capture_sub)
            self._override_capture_sub = None

    async def _deferred_initial_push(self):
        try:
            await omni.kit.app.get_app().next_update_async()
            # safe_remix_extern() is sync and raises inside any asyncio loop ("Cannot call
            # load_remix_extern() from within a running event loop"), so we have to load
            # HdRemix.dll via the async path BEFORE the first set_configvar. After this
            # await, _instance is set and subsequent (sync) safe_remix_extern() calls
            # from the settings-change handler short-circuit cleanly.
            try:
                await _load_remix_extern_async()
            except Exception as exc:  # noqa: BLE001
                carb.log_warn(
                    f"[hdremix_renderer] load_remix_extern_async failed: {exc}. "
                    "Skipping initial push; the user may need to toggle the combo manually after the renderer is ready."
                )
                return
            # Only push on startup if the user has explicitly opted to override
            # the loaded capture's integrator. Default (override off) leaves the
            # runtime alone so the capture's preset value applies on each load.
            if self._settings.get(SETTINGS_OVERRIDE_CAPTURE_INTEGRATOR):
                self._push_integrate_indirect_mode()
            else:
                carb.log_info(
                    "[hdremix_renderer] overrideCaptureIntegrator=False; deferring to capture's preset "
                    "(skip startup push). Toggle the checkbox in Preferences to force the global value."
                )
        except asyncio.CancelledError:
            pass

    def _push_integrate_indirect_mode(self):
        mode = coerce_mode(self._settings.get(SETTINGS_INTEGRATE_INDIRECT_MODE))
        try:
            _hdremix_set_configvar(_RTX_OPTION_INTEGRATE_INDIRECT_MODE, str(mode))
        except Exception as exc:  # noqa: BLE001 - we never want to break the extension on a runtime hiccup
            carb.log_warn(
                f"[hdremix_renderer] failed to push integrateIndirectMode={mode}: {exc}. "
                "The HdRemix renderer may not be initialized yet."
            )
            return
        carb.log_info(
            f"[hdremix_renderer] integrateIndirectMode set to {mode} ({INTEGRATE_INDIRECT_MODE_LABELS[mode]})"
        )

    def _on_integrate_indirect_mode_changed(self, *_args, **_kwargs):
        # Gate every runtime push -- including dropdown-change pushes -- on the
        # override flag (REMIX-5483 review by Nicolas): if the user hasn't opted
        # in to overriding the capture's preset, changing the dropdown only
        # records their preference; it does not touch the live renderer. This is
        # symmetric with _deferred_initial_push and makes the checkbox a true
        # global gate.
        if not self._settings.get(SETTINGS_OVERRIDE_CAPTURE_INTEGRATOR):
            carb.log_info(
                "[hdremix_renderer] integrateIndirectMode preference updated but overrideCaptureIntegrator=False; "
                "skipping runtime push (capture preset wins)."
            )
            return
        # User-driven change with override on: force graphicsPreset=Custom so
        # dxvk-remix's Quality layer stops overriding our User-layer write. We
        # do NOT do this in _deferred_initial_push so a fresh launch keeps
        # whatever preset the user had. First UI toggle "consumes" the preset;
        # subsequent toggles work normally.
        self._force_graphics_preset_custom()
        self._push_integrate_indirect_mode()

    def _on_override_capture_changed(self, *_args, **_kwargs):
        # Enabling the override mid-session applies it right away rather than waiting for
        # the next dropdown change or a restart (the tooltip promises "on startup and on
        # every change", which previously left a gap when only the checkbox flipped).
        # Mirror the user-driven dropdown path: force graphicsPreset=Custom so our
        # User-layer write wins, then push the persisted mode. When the flag flips back to
        # False we leave the runtime as-is -- the next loaded capture's preset applies --
        # symmetric with _deferred_initial_push's startup gating.
        if not self._settings.get(SETTINGS_OVERRIDE_CAPTURE_INTEGRATOR):
            carb.log_info(
                "[hdremix_renderer] overrideCaptureIntegrator=False; leaving the runtime as-is "
                "(the next loaded capture's preset wins)."
            )
            return
        self._force_graphics_preset_custom()
        self._push_integrate_indirect_mode()

    def _force_graphics_preset_custom(self):
        # Force dxvk-remix's graphicsPreset to Custom (enum value 4) so its Quality layer
        # stops shadowing the User-layer write hdremix_set_configvar makes for
        # integrateIndirectMode. Shared by the dropdown-change and override-toggle push
        # paths. See dxvk-remix rtx_option.cpp:842-848 and rtx_options.h:75.
        try:
            _hdremix_set_configvar(_RTX_OPTION_GRAPHICS_PRESET, _RTX_GRAPHICS_PRESET_CUSTOM)
        except Exception as exc:  # noqa: BLE001
            carb.log_warn(
                f"[hdremix_renderer] failed to force graphicsPreset=Custom: {exc}. "
                "integrateIndirectMode change may be shadowed by the active graphics preset."
            )

    def destroy(self):
        self.stop()
        _reset_default_attrs(self)

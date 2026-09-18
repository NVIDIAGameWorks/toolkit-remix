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
import math
from functools import partial

import carb
import carb.settings
import omni.kit.app
import omni.usd
from lightspeed.common import constants
from lightspeed.events_manager import get_instance as _get_event_manager_instance
from lightspeed.hydra.remix.core import RemixSupport
from lightspeed.hydra.remix.core import get_dlss_neural_rendering_support
from lightspeed.hydra.remix.core import hdremix_set_configvar as _hdremix_set_configvar
from lightspeed.hydra.remix.core import is_remix_extern_ready
from lightspeed.hydra.remix.core import is_remix_supported
from lightspeed.hydra.remix.core import is_remix_timeout
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

from .dlss_settings import DLSS_MODEL, DLSS_SETTINGS, DlssSetting, DlssSettingKind, coerce_dlss_value, format_dlss_value
from .dlss_settings import SETTINGS_DLSS_NEURAL_RENDERING_AVAILABLE

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
_CONFIG_DELIMITER = " = "
_LEGACY_DLSS_MODEL_RUNTIME_KEY = "rtx.dlssNeuralRendering.style"


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


def _read_captured_remix_config() -> dict[str, str]:
    """Return the resolved runtime configuration stored on the current capture."""
    stage = omni.usd.get_context().get_stage()
    if stage is None:
        return {}
    prim = stage.GetPrimAtPath(constants.CAPTURED_REMIX_SETTINGS)
    if not prim.IsValid():
        return {}
    attribute = prim.GetAttribute(constants.CAPTURED_REMIX_CONFIG_ATTR)
    values = attribute.Get() if attribute else None
    if not values:
        return {}

    result = {}
    for entry in values:
        if not isinstance(entry, str):
            continue
        key, delimiter, value = entry.partition(_CONFIG_DELIMITER)
        if delimiter and key and value:
            result[key] = value
    return result


def _parse_captured_dlss_value(setting: DlssSetting, raw_value: str) -> object | None:
    """Parse a captured DLSS value without replacing malformed input with a default."""
    if setting.kind == DlssSettingKind.BOOL:
        normalized = raw_value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        return None

    if setting.kind == DlssSettingKind.ENUM:
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            return None
        if not 0 <= value < len(setting.options):
            return None
        return value

    if setting.kind == DlssSettingKind.UNIT_FLOAT:
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(value):
            return None
        return coerce_dlss_value(setting, value)

    components = raw_value.replace(",", " ").split()
    if len(components) != 4:
        return None
    try:
        values = [float(component) for component in components]
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in values):
        return None
    return coerce_dlss_value(setting, values)


async def _wait_for_remix_extern_async() -> bool:
    """Wait for viewport-owned Remix extern initialization without starting support discovery."""
    while not is_remix_extern_ready():
        support_level, _ = is_remix_supported()
        if support_level == RemixSupport.NOT_SUPPORTED and not is_remix_timeout():
            return False
        await omni.kit.app.get_app().next_update_async()
    return True


class HdRemixSettingsBridge:
    """Relay persistent HdRemix renderer settings to the dxvk-remix runtime.

    DLSS Neural Rendering controls inherit resolved values from each capture and write
    only subsequent user edits. Renderer support discovery remains owned by the viewport.
    """

    def __init__(self):
        """Initialize persistent settings and lifecycle state."""
        self.default_attr = {
            "_settings": None,
            "_integrate_indirect_sub": None,
            "_override_capture_sub": None,
        }
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._settings = carb.settings.get_settings()
        self._dlss_subscriptions = []
        self._capture_layer_imported_sub = None
        self._settings_push_task = None
        self._pending_dlss_settings: set[DlssSetting] = set()
        self._initial_integrator_push_pending = False
        self._is_running = False
        self._syncing_dlss_settings = False
        self._dlss_neural_rendering_support_task: asyncio.Task | None = None
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
        """Subscribe to Toolkit settings and schedule the initial runtime push."""
        self.stop()
        self._is_running = True
        self._settings.set(SETTINGS_DLSS_NEURAL_RENDERING_AVAILABLE, False)
        self._dlss_neural_rendering_support_task = asyncio.ensure_future(self._poll_dlss_neural_rendering_support())
        self._initial_integrator_push_pending = True
        self._capture_layer_imported_sub = _get_event_manager_instance().subscribe_global_custom_event(
            constants.GlobalEventNames.CAPTURE_LAYER_IMPORTED.value, self._sync_dlss_settings_from_capture
        )
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
        for setting in DLSS_SETTINGS:
            subscription = self._settings.subscribe_to_node_change_events(
                setting.setting_path, partial(self._on_dlss_setting_changed, setting)
            )
            self._dlss_subscriptions.append(subscription)
        self._sync_dlss_settings_from_capture()
        self._schedule_settings_push()

    def stop(self):
        """Cancel deferred work and unsubscribe from Toolkit settings."""
        self._is_running = False
        self._pending_dlss_settings.clear()
        self._initial_integrator_push_pending = False
        self._syncing_dlss_settings = False
        if self._dlss_neural_rendering_support_task is not None and not self._dlss_neural_rendering_support_task.done():
            self._dlss_neural_rendering_support_task.cancel()
        self._dlss_neural_rendering_support_task = None
        self._settings.set(SETTINGS_DLSS_NEURAL_RENDERING_AVAILABLE, False)

        if self._settings_push_task is not None and not self._settings_push_task.done():
            self._settings_push_task.cancel()
        self._settings_push_task = None
        self._capture_layer_imported_sub = None
        if self._integrate_indirect_sub is not None:
            self._settings.unsubscribe_to_change_events(self._integrate_indirect_sub)
            self._integrate_indirect_sub = None
        if self._override_capture_sub is not None:
            self._settings.unsubscribe_to_change_events(self._override_capture_sub)
            self._override_capture_sub = None
        for subscription in self._dlss_subscriptions:
            self._settings.unsubscribe_to_change_events(subscription)
        self._dlss_subscriptions.clear()

    async def _poll_dlss_neural_rendering_support(self) -> None:
        """Publish DLSS Neural Rendering availability after native capability discovery completes."""
        try:
            if not await _wait_for_remix_extern_async():
                return
            while self._is_running:
                support = get_dlss_neural_rendering_support()
                if support != RemixSupport.WAITING_FOR_INIT:
                    self._settings.set(
                        SETTINGS_DLSS_NEURAL_RENDERING_AVAILABLE,
                        support == RemixSupport.SUPPORTED,
                    )
                    return
                await omni.kit.app.get_app().next_update_async()
        except asyncio.CancelledError:
            pass

    def _sync_dlss_settings_from_capture(self) -> None:
        """Seed Toolkit controls from captured runtime values without echoing them back."""
        captured_config = _read_captured_remix_config()
        if not captured_config:
            return

        if _LEGACY_DLSS_MODEL_RUNTIME_KEY in captured_config and DLSS_MODEL.runtime_key not in captured_config:
            self._syncing_dlss_settings = True
            try:
                for setting in DLSS_SETTINGS:
                    self._settings.set(setting.setting_path, coerce_dlss_value(setting, None))
                    self._pending_dlss_settings.add(setting)
            finally:
                self._syncing_dlss_settings = False
            carb.log_info("[hdremix_renderer] reset legacy DLSS Neural Rendering capture settings to current defaults.")
            self._schedule_settings_push()
            return

        self._syncing_dlss_settings = True
        try:
            for setting in DLSS_SETTINGS:
                raw_value = captured_config.get(setting.runtime_key)
                if raw_value is None:
                    continue
                value = _parse_captured_dlss_value(setting, raw_value)
                if value is None:
                    carb.log_warn(f"[hdremix_renderer] ignored invalid captured {setting.identifier}={raw_value}.")
                    continue
                self._pending_dlss_settings.discard(setting)
                self._settings.set(setting.setting_path, value)
        finally:
            self._syncing_dlss_settings = False

    def _schedule_settings_push(self):
        """Queue the initial integrator push or user edits until HdRemix is ready."""
        if not self._is_running:
            return
        if self._settings_push_task is not None and not self._settings_push_task.done():
            return
        self._settings_push_task = asyncio.ensure_future(self._deferred_settings_push())

    def _defer_dlss_push_until_ready(self, setting: DlssSetting) -> bool:
        """Queue a user-edited setting when the native extern is not ready."""
        if not self._is_running:
            return True
        if is_remix_extern_ready():
            return False
        self._pending_dlss_settings.add(setting)
        self._schedule_settings_push()
        return True

    async def _deferred_settings_push(self):
        """Apply queued user edits and the one-time startup integrator override."""
        push_initial_integrator = self._initial_integrator_push_pending
        self._initial_integrator_push_pending = False
        try:
            await omni.kit.app.get_app().next_update_async()
            if not await _wait_for_remix_extern_async() or not self._is_running:
                return
            pending_settings = tuple(setting for setting in DLSS_SETTINGS if setting in self._pending_dlss_settings)
            self._pending_dlss_settings.clear()
            for setting in pending_settings:
                self._push_dlss_setting(setting)
            if push_initial_integrator:
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

    def _push_config_value(self, key: str, value: str, label: str) -> None:
        """Push a renderer config variable without breaking the extension on runtime errors."""
        try:
            _hdremix_set_configvar(key, value)
        except Exception as exc:  # noqa: BLE001 - the renderer can disappear during shutdown
            carb.log_warn(
                f"[hdremix_renderer] failed to push {label}={value}: {exc}. "
                "The HdRemix renderer may not be initialized yet."
            )
            return
        carb.log_info(f"[hdremix_renderer] {label} set to {value}")

    def _push_dlss_setting(self, setting: DlssSetting) -> None:
        """Push one persisted DLSS Neural Rendering setting."""
        value = coerce_dlss_value(setting, self._settings.get(setting.setting_path))
        self._push_config_value(setting.runtime_key, format_dlss_value(value), setting.identifier)

    def _on_dlss_setting_changed(self, setting: DlssSetting, *_args, **_kwargs) -> None:
        """Push a live DLSS setting change or defer it until the extern is ready."""
        if self._syncing_dlss_settings or self._defer_dlss_push_until_ready(setting):
            return
        self._push_dlss_setting(setting)

    def _on_integrate_indirect_mode_changed(self, *_args, **_kwargs):
        # Gate every runtime push -- including dropdown-change pushes -- on the
        # override flag (REMIX-5483 review by Nicolas): if the user hasn't opted
        # in to overriding the capture's preset, changing the dropdown only
        # records their preference; it does not touch the live renderer.
        if not self._settings.get(SETTINGS_OVERRIDE_CAPTURE_INTEGRATOR):
            carb.log_info(
                "[hdremix_renderer] integrateIndirectMode preference updated but overrideCaptureIntegrator=False; "
                "skipping runtime push (capture preset wins)."
            )
            return
        # User-driven change with override on: force graphicsPreset=Custom so
        # dxvk-remix's Quality layer stops overriding our User-layer write.
        self._force_graphics_preset_custom()
        self._push_integrate_indirect_mode()

    def _on_override_capture_changed(self, *_args, **_kwargs):
        # Enabling the override mid-session applies it right away rather than waiting for
        # the next dropdown change or a restart. Disabling leaves the runtime as-is so
        # the next loaded capture's preset applies.
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

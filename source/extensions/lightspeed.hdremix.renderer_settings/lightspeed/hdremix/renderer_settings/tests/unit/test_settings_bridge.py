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
from unittest.mock import AsyncMock, call, patch

import carb
import carb.settings
from lightspeed.hdremix.renderer_settings.settings_bridge import (
    DEFAULT_INTEGRATE_INDIRECT_MODE,
    INTEGRATE_INDIRECT_MODE_LABELS,
    SETTINGS_INTEGRATE_INDIRECT_MODE,
    SETTINGS_OVERRIDE_CAPTURE_INTEGRATOR,
    HdRemixSettingsBridge,
    _LEGACY_SETTINGS_INTEGRATE_INDIRECT_MODE,
    _SETTINGS_LEGACY_MIGRATION_DONE,
    coerce_mode,
)
from omni.kit.test import AsyncTestCase

_HDREMIX_PATCH_TARGET = "lightspeed.hdremix.renderer_settings.settings_bridge._hdremix_set_configvar"
_LOAD_EXTERN_PATCH_TARGET = "lightspeed.hdremix.renderer_settings.settings_bridge._load_remix_extern_async"


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


@contextlib.contextmanager
def _migration_keys_reset():
    """Snapshot + clear the three keys the legacy-migration path reads/writes, restoring
    them on exit. Lets each migration test start from a clean slate (no marker, no legacy,
    no new-key value) and then set up only the state it cares about, without contaminating
    state for sibling tests."""
    settings = carb.settings.get_settings()
    keys = (
        SETTINGS_INTEGRATE_INDIRECT_MODE,
        _LEGACY_SETTINGS_INTEGRATE_INDIRECT_MODE,
        _SETTINGS_LEGACY_MIGRATION_DONE,
    )
    originals = {k: settings.get(k) for k in keys}
    for k in keys:
        if originals[k] is not None:
            settings.destroy_item(k)
    try:
        yield settings
    finally:
        for k in keys:
            current = settings.get(k)
            if originals[k] is None:
                if current is not None:
                    settings.destroy_item(k)
            else:
                settings.set(k, originals[k])


class TestHdRemixSettingsBridge(AsyncTestCase):
    def test_coerce_mode_handles_invalid_values(self):
        # Sanity check the pure helper before exercising the I/O paths.
        self.assertEqual(coerce_mode(None), DEFAULT_INTEGRATE_INDIRECT_MODE)
        self.assertEqual(coerce_mode("garbage"), DEFAULT_INTEGRATE_INDIRECT_MODE)
        self.assertEqual(coerce_mode(99), DEFAULT_INTEGRATE_INDIRECT_MODE)
        self.assertEqual(coerce_mode(-1), DEFAULT_INTEGRATE_INDIRECT_MODE)
        self.assertEqual(coerce_mode(0), 0)
        self.assertEqual(coerce_mode(1), 1)
        self.assertEqual(coerce_mode(2), 2)
        self.assertEqual(coerce_mode("1"), 1)

    async def test_install_pushes_persisted_mode_when_override_on(self):
        # With overrideCaptureIntegrator=True the bridge must push the currently-
        # persisted mode to the runtime on startup. Default (override=False) is
        # covered by test_install_skips_push_when_override_off below.
        with (
            _override_setting(SETTINGS_INTEGRATE_INDIRECT_MODE, 1),
            _override_setting(SETTINGS_OVERRIDE_CAPTURE_INTEGRATOR, True),
        ):
            with patch(_LOAD_EXTERN_PATCH_TARGET, new=AsyncMock(return_value=0)):
                with patch(_HDREMIX_PATCH_TARGET) as mock_set:
                    bridge = HdRemixSettingsBridge()
                    try:
                        bridge.start()
                        await bridge._startup_push_task
                        # Startup pushes ONLY the integrator — not graphicsPreset — so a fresh
                        # launch keeps whatever quality preset the user had.
                        mock_set.assert_called_once_with("rtx.integrateIndirectMode", "1")
                    finally:
                        bridge.stop()
                        bridge.destroy()

    async def test_install_skips_push_when_override_off(self):
        # Default (overrideCaptureIntegrator=False) -> bridge must NOT push on startup
        # so the loaded capture's preset value wins. Regression guard for Nicolas's
        # review: previously the global preference was sticky and silently
        # overrode the per-capture integrator on every stage load.
        with (
            _override_setting(SETTINGS_INTEGRATE_INDIRECT_MODE, 1),
            _override_setting(SETTINGS_OVERRIDE_CAPTURE_INTEGRATOR, False),
        ):
            with patch(_LOAD_EXTERN_PATCH_TARGET, new=AsyncMock(return_value=0)):
                with patch(_HDREMIX_PATCH_TARGET) as mock_set:
                    bridge = HdRemixSettingsBridge()
                    try:
                        bridge.start()
                        await bridge._startup_push_task
                        mock_set.assert_not_called()
                    finally:
                        bridge.stop()
                        bridge.destroy()

    async def test_install_falls_back_to_default_on_invalid_value(self):
        with (
            _override_setting(SETTINGS_INTEGRATE_INDIRECT_MODE, "garbage"),
            _override_setting(SETTINGS_OVERRIDE_CAPTURE_INTEGRATOR, True),
        ):
            with patch(_LOAD_EXTERN_PATCH_TARGET, new=AsyncMock(return_value=0)):
                with patch(_HDREMIX_PATCH_TARGET) as mock_set:
                    bridge = HdRemixSettingsBridge()
                    try:
                        bridge.start()
                        await bridge._startup_push_task
                        mock_set.assert_called_once_with(
                            "rtx.integrateIndirectMode", str(DEFAULT_INTEGRATE_INDIRECT_MODE)
                        )
                    finally:
                        bridge.stop()
                        bridge.destroy()

    async def test_setting_change_triggers_push_and_forces_custom_preset(self):
        # A user-driven setting change with override=ON must push BOTH
        # graphicsPreset=Custom (=4) AND the new integrator value, in that order.
        # Forcing Custom is what stops dxvk-remix's Quality layer from shadowing
        # the User-layer integrator write. We invoke the handler directly instead
        # of round-tripping through carb's subscribe_to_node_change_events: the
        # extension auto-starts another HdRemixSettingsBridge in the test app,
        # and its subscription would fire too, doubling every recorded call and
        # breaking the order assertion.
        with (
            _override_setting(SETTINGS_INTEGRATE_INDIRECT_MODE, 1),
            _override_setting(SETTINGS_OVERRIDE_CAPTURE_INTEGRATOR, True),
        ):
            with patch(_LOAD_EXTERN_PATCH_TARGET, new=AsyncMock(return_value=0)):
                with patch(_HDREMIX_PATCH_TARGET) as mock_set:
                    bridge = HdRemixSettingsBridge()
                    try:
                        bridge._on_integrate_indirect_mode_changed()
                        self.assertEqual(
                            mock_set.call_args_list,
                            [
                                call("rtx.graphicsPreset", "4"),
                                call("rtx.integrateIndirectMode", "1"),
                            ],
                        )
                    finally:
                        bridge.destroy()

    async def test_setting_change_skips_push_when_override_off(self):
        # Regression guard for Nicolas's REMIX-5483 review (round 2): with
        # overrideCaptureIntegrator=False, changing the dropdown must NOT touch
        # the live renderer -- the capture's preset wins. Symmetric with the
        # startup-push gate in test_install_skips_push_when_override_off.
        with (
            _override_setting(SETTINGS_INTEGRATE_INDIRECT_MODE, 1),
            _override_setting(SETTINGS_OVERRIDE_CAPTURE_INTEGRATOR, False),
        ):
            with patch(_LOAD_EXTERN_PATCH_TARGET, new=AsyncMock(return_value=0)):
                with patch(_HDREMIX_PATCH_TARGET) as mock_set:
                    bridge = HdRemixSettingsBridge()
                    try:
                        bridge._on_integrate_indirect_mode_changed()
                        self.assertEqual(
                            mock_set.call_args_list,
                            [],
                            f"override=False must skip ALL runtime writes; got {mock_set.call_args_list!r}",
                        )
                    finally:
                        bridge.destroy()

    async def test_override_flag_flip_triggers_immediate_push(self):
        # Symmetric to test_setting_change_triggers_push_and_forces_custom_preset
        # but covers the checkbox-flip path: flipping overrideCaptureIntegrator to
        # True mid-session must immediately force graphicsPreset=Custom and push
        # the persisted integrator, rather than waiting for the next dropdown
        # change or a restart. Closes the unit-level gap behind the e2e test.
        with (
            _override_setting(SETTINGS_INTEGRATE_INDIRECT_MODE, 1),
            _override_setting(SETTINGS_OVERRIDE_CAPTURE_INTEGRATOR, True),
        ):
            with patch(_LOAD_EXTERN_PATCH_TARGET, new=AsyncMock(return_value=0)):
                with patch(_HDREMIX_PATCH_TARGET) as mock_set:
                    bridge = HdRemixSettingsBridge()
                    try:
                        bridge._on_override_capture_changed()
                        self.assertEqual(
                            mock_set.call_args_list,
                            [
                                call("rtx.graphicsPreset", "4"),
                                call("rtx.integrateIndirectMode", "1"),
                            ],
                        )
                    finally:
                        bridge.destroy()

    async def test_override_flag_flip_off_skips_push(self):
        # Flipping overrideCaptureIntegrator back to False mid-session must NOT
        # touch the live renderer -- the next loaded capture's preset wins,
        # symmetric with the startup-push gate.
        with (
            _override_setting(SETTINGS_INTEGRATE_INDIRECT_MODE, 1),
            _override_setting(SETTINGS_OVERRIDE_CAPTURE_INTEGRATOR, False),
        ):
            with patch(_LOAD_EXTERN_PATCH_TARGET, new=AsyncMock(return_value=0)):
                with patch(_HDREMIX_PATCH_TARGET) as mock_set:
                    bridge = HdRemixSettingsBridge()
                    try:
                        bridge._on_override_capture_changed()
                        self.assertEqual(
                            mock_set.call_args_list,
                            [],
                            f"override=False flip must skip runtime writes; got {mock_set.call_args_list!r}",
                        )
                    finally:
                        bridge.destroy()

    def test_labels_match_dxvk_remix_enum_order(self):
        # Pins the exact ordering of INTEGRATE_INDIRECT_MODE_LABELS against dxvk-remix's
        # IntegrateIndirectMode enum (src/dxvk/rtx_render/rtx_options.h). If upstream
        # re-orders the enum, the dropdown's "RTX Neural Radiance Cache" entry would
        # silently start writing a different integer to rtx.integrateIndirectMode and
        # the visual behavior wouldn't match the label. Strings verified against
        # RemixGui::ComboWithKey<IntegrateIndirectMode> in src/dxvk/imgui/dxvk_imgui.cpp;
        # only index 2 carries the "RTX " prefix in the upstream combo.
        self.assertEqual(
            INTEGRATE_INDIRECT_MODE_LABELS,
            ["Importance Sampled", "ReSTIR GI", "RTX Neural Radiance Cache"],
        )

    async def test_preset_force_to_custom_repeats_on_subsequent_toggles(self):
        # Sticky preset assertion: with override=ON, every user toggle must re-force
        # graphicsPreset=Custom, not just the first. Without this, a future "restore
        # preset between toggles" politeness fix would silently reintroduce Quality-layer
        # shadowing on the second change. Two consecutive handler invocations must each
        # emit the preset write.
        with (
            _override_setting(SETTINGS_INTEGRATE_INDIRECT_MODE, 0),
            _override_setting(SETTINGS_OVERRIDE_CAPTURE_INTEGRATOR, True),
        ):
            with patch(_LOAD_EXTERN_PATCH_TARGET, new=AsyncMock(return_value=0)):
                with patch(_HDREMIX_PATCH_TARGET) as mock_set:
                    bridge = HdRemixSettingsBridge()
                    try:
                        bridge._on_integrate_indirect_mode_changed()
                        bridge._on_integrate_indirect_mode_changed()
                        preset_calls = [c for c in mock_set.call_args_list if c == call("rtx.graphicsPreset", "4")]
                        self.assertEqual(
                            len(preset_calls),
                            2,
                            f"graphicsPreset=4 must be forced on every user toggle; got {mock_set.call_args_list!r}",
                        )
                    finally:
                        bridge.destroy()

    async def test_round_trip_persistence_and_replay_after_bridge_recreation(self):
        # Catches drift between the carb settings path the change handler writes and
        # the one start()'s deferred push reads on next launch. Simulates app relaunch
        # by destroying the bridge and instantiating a fresh one against the still-set
        # persistent value; the startup push must replay it. If the two paths ever
        # desync (typo, prefix change, etc.) this fails before users see "I set NRC
        # but it's back on ReSTIR".
        with (
            _override_setting(SETTINGS_INTEGRATE_INDIRECT_MODE, 1),
            _override_setting(SETTINGS_OVERRIDE_CAPTURE_INTEGRATOR, True),
        ):
            with patch(_LOAD_EXTERN_PATCH_TARGET, new=AsyncMock(return_value=0)):
                with patch(_HDREMIX_PATCH_TARGET) as first_set:
                    bridge = HdRemixSettingsBridge()
                    try:
                        bridge.start()
                        await bridge._startup_push_task
                        first_set.assert_called_once_with("rtx.integrateIndirectMode", "1")
                    finally:
                        bridge.stop()
                        bridge.destroy()
                with patch(_HDREMIX_PATCH_TARGET) as replayed_set:
                    replayed_bridge = HdRemixSettingsBridge()
                    try:
                        replayed_bridge.start()
                        await replayed_bridge._startup_push_task
                        replayed_set.assert_called_once_with("rtx.integrateIndirectMode", "1")
                    finally:
                        replayed_bridge.stop()
                        replayed_bridge.destroy()

    def test_legacy_migration_copies_old_key_value_through_toml_default(self):
        # Regression: extension.toml pre-seeds the new key with its TOML default before
        # Python runs, so a "new key is None" gate inside Python never fires and returning
        # users would silently lose their pre-rename choice. Pin that migration is gated
        # on the marker key and actually copies the legacy value even when the new key is
        # already populated with the TOML default at __init__ time.
        with _migration_keys_reset() as settings:
            settings.set(_LEGACY_SETTINGS_INTEGRATE_INDIRECT_MODE, 1)
            settings.set(SETTINGS_INTEGRATE_INDIRECT_MODE, DEFAULT_INTEGRATE_INDIRECT_MODE)
            bridge = HdRemixSettingsBridge()
            try:
                self.assertEqual(settings.get(SETTINGS_INTEGRATE_INDIRECT_MODE), 1)
                self.assertTrue(settings.get(_SETTINGS_LEGACY_MIGRATION_DONE))
            finally:
                bridge.destroy()

    def test_legacy_migration_runs_at_most_once(self):
        # Once the marker is set, subsequent launches must NOT re-migrate from legacy —
        # otherwise a user who explicitly picks the default integrator value under the new
        # key after migration would be silently reverted to their old (different) legacy
        # value on every launch.
        with _migration_keys_reset() as settings:
            settings.set(_LEGACY_SETTINGS_INTEGRATE_INDIRECT_MODE, 1)
            settings.set(SETTINGS_INTEGRATE_INDIRECT_MODE, DEFAULT_INTEGRATE_INDIRECT_MODE)
            settings.set(_SETTINGS_LEGACY_MIGRATION_DONE, True)
            bridge = HdRemixSettingsBridge()
            try:
                self.assertEqual(
                    settings.get(SETTINGS_INTEGRATE_INDIRECT_MODE),
                    DEFAULT_INTEGRATE_INDIRECT_MODE,
                    "Marker-gated migration must not overwrite the new key on subsequent launches.",
                )
            finally:
                bridge.destroy()

    def test_legacy_migration_sets_marker_even_when_no_legacy_value(self):
        # Fresh installs (no legacy key) still flip the marker so the next launch's check
        # is a cheap O(1) settings.get() instead of repeatedly probing the legacy key.
        with _migration_keys_reset() as settings:
            bridge = HdRemixSettingsBridge()
            try:
                self.assertTrue(settings.get(_SETTINGS_LEGACY_MIGRATION_DONE))
            finally:
                bridge.destroy()

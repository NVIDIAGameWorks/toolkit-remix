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
import contextlib
from unittest.mock import AsyncMock, MagicMock, call, patch

import carb
import carb.settings
from lightspeed.hydra.remix.core import RemixSupport
from omni.kit.test import AsyncTestCase

from ... import settings_bridge as _settings_bridge
from ...dlss_settings import (
    DLSS_ENABLE,
    DLSS_HIGHLIGHT_RECOVERY_THRESHOLDS,
    DLSS_INTENSITY,
    DLSS_MODEL,
    DLSS_SETTINGS,
    DLSS_STRUCTURE_INTENSITY,
    DLSS_TONE_INTENSITY,
    coerce_dlss_value,
)
from ...settings_bridge import (
    DEFAULT_INTEGRATE_INDIRECT_MODE,
    INTEGRATE_INDIRECT_MODE_LABELS,
    SETTINGS_INTEGRATE_INDIRECT_MODE,
    SETTINGS_OVERRIDE_CAPTURE_INTEGRATOR,
    HdRemixSettingsBridge,
    _LEGACY_SETTINGS_INTEGRATE_INDIRECT_MODE,
    _SETTINGS_LEGACY_MIGRATION_DONE,
    _wait_for_remix_extern_async,
    coerce_mode,
)

_HDREMIX_PATCH_TARGET = "lightspeed.hdremix.renderer_settings.settings_bridge._hdremix_set_configvar"
_WAIT_PATCH_TARGET = "lightspeed.hdremix.renderer_settings.settings_bridge._wait_for_remix_extern_async"


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


def _event_manager_with_callback(callbacks):
    """Build an event-manager mock that records its subscription callback."""
    event_manager = MagicMock()
    event_manager.subscribe_global_custom_event.side_effect = lambda event_name, callback: (
        callbacks.append((event_name, callback)) or MagicMock()
    )
    return event_manager


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
            with patch(_WAIT_PATCH_TARGET, new=AsyncMock(return_value=True)):
                with patch(_HDREMIX_PATCH_TARGET) as mock_set:
                    bridge = HdRemixSettingsBridge()
                    try:
                        bridge.start()
                        await bridge._settings_push_task
                        # Startup pushes ONLY the integrator — not graphicsPreset — so a fresh
                        # launch keeps whatever quality preset the user had.
                        mock_set.assert_called_once_with("rtx.integrateIndirectMode", "1")
                        self.assertNotIn(call("rtx.graphicsPreset", "4"), mock_set.call_args_list)
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
            with patch(_WAIT_PATCH_TARGET, new=AsyncMock(return_value=True)):
                with patch(_HDREMIX_PATCH_TARGET) as mock_set:
                    bridge = HdRemixSettingsBridge()
                    try:
                        bridge.start()
                        await bridge._settings_push_task
                        written_keys = {runtime_call.args[0] for runtime_call in mock_set.call_args_list}
                        self.assertNotIn("rtx.graphicsPreset", written_keys)
                        self.assertNotIn("rtx.integrateIndirectMode", written_keys)
                    finally:
                        bridge.stop()
                        bridge.destroy()

    async def test_install_falls_back_to_default_on_invalid_value(self):
        with (
            _override_setting(SETTINGS_INTEGRATE_INDIRECT_MODE, "garbage"),
            _override_setting(SETTINGS_OVERRIDE_CAPTURE_INTEGRATOR, True),
        ):
            with patch(_WAIT_PATCH_TARGET, new=AsyncMock(return_value=True)):
                with patch(_HDREMIX_PATCH_TARGET) as mock_set:
                    bridge = HdRemixSettingsBridge()
                    try:
                        bridge.start()
                        await bridge._settings_push_task
                        mock_set.assert_any_call("rtx.integrateIndirectMode", str(DEFAULT_INTEGRATE_INDIRECT_MODE))
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
            with patch(_WAIT_PATCH_TARGET, new=AsyncMock(return_value=True)):
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
            with patch(_WAIT_PATCH_TARGET, new=AsyncMock(return_value=True)):
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
            with patch(_WAIT_PATCH_TARGET, new=AsyncMock(return_value=True)):
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
            with patch(_WAIT_PATCH_TARGET, new=AsyncMock(return_value=True)):
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
            with patch(_WAIT_PATCH_TARGET, new=AsyncMock(return_value=True)):
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
            with patch(_WAIT_PATCH_TARGET, new=AsyncMock(return_value=True)):
                with patch(_HDREMIX_PATCH_TARGET) as first_set:
                    bridge = HdRemixSettingsBridge()
                    try:
                        bridge.start()
                        await bridge._settings_push_task
                        first_set.assert_any_call("rtx.integrateIndirectMode", "1")
                    finally:
                        bridge.stop()
                        bridge.destroy()
                with patch(_HDREMIX_PATCH_TARGET) as replayed_set:
                    replayed_bridge = HdRemixSettingsBridge()
                    try:
                        replayed_bridge.start()
                        await replayed_bridge._settings_push_task
                        replayed_set.assert_any_call("rtx.integrateIndirectMode", "1")
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

    async def test_startup_preserves_runtime_dlss_settings(self):
        """Startup should not replay stale persisted DLSS values into the runtime."""
        # Arrange
        settings = MagicMock()
        settings.get.side_effect = {
            _SETTINGS_LEGACY_MIGRATION_DONE: True,
            SETTINGS_OVERRIDE_CAPTURE_INTEGRATOR: False,
        }.get
        event_manager = MagicMock()
        app = MagicMock()
        app.next_update_async = AsyncMock()
        with (
            patch.object(_settings_bridge.carb.settings, "get_settings", return_value=settings),
            patch.object(_settings_bridge, "_get_event_manager_instance", return_value=event_manager),
            patch.object(HdRemixSettingsBridge, "_poll_dlss_neural_rendering_support", new=AsyncMock()),
            patch.object(_settings_bridge, "_read_captured_remix_config", return_value={}),
            patch.object(_settings_bridge, "_wait_for_remix_extern_async", new=AsyncMock(return_value=True)),
            patch.object(_settings_bridge.omni.kit.app, "get_app", return_value=app),
            patch.object(_settings_bridge, "_hdremix_set_configvar") as mock_set,
        ):
            bridge = HdRemixSettingsBridge()
            try:
                # Act
                bridge.start()
                await bridge._settings_push_task

                # Assert
                mock_set.assert_not_called()
            finally:
                bridge.destroy()

    def test_dlss_setting_change_when_extern_ready_pushes_value(self):
        """A DLSS control edit should reach the runtime immediately when the extern is ready."""
        # Arrange
        setting = DLSS_ENABLE
        with (
            _override_setting(setting.setting_path, False),
            patch.object(_settings_bridge, "is_remix_extern_ready", return_value=True),
            patch.object(_settings_bridge, "_hdremix_set_configvar") as mock_set,
        ):
            bridge = HdRemixSettingsBridge()
            bridge._is_running = True
            try:
                # Act
                bridge._on_dlss_setting_changed(setting)

                # Assert
                mock_set.assert_called_once_with(setting.runtime_key, "False")
            finally:
                bridge.destroy()

    def test_capture_import_syncs_dlss_controls_without_runtime_writes(self):
        """Captured runtime values should seed controls without being echoed back."""
        # Arrange
        captured_settings = (DLSS_ENABLE, DLSS_MODEL, DLSS_INTENSITY, DLSS_HIGHLIGHT_RECOVERY_THRESHOLDS)
        captured_config = {
            captured_settings[0].runtime_key: "False",
            captured_settings[1].runtime_key: "2",
            captured_settings[2].runtime_key: "0.25",
            captured_settings[3].runtime_key: "-1, 64, 0.75, 0.5",
        }
        expected_values = (False, 2, 0.25, [0.0, 32.0, 0.75, 0.5])
        settings = MagicMock()
        bridge = HdRemixSettingsBridge.__new__(HdRemixSettingsBridge)
        bridge._settings = settings
        bridge._pending_dlss_settings = set(DLSS_SETTINGS)
        bridge._syncing_dlss_settings = False
        setting_by_path = {setting.setting_path: setting for setting in captured_settings}
        settings.set.side_effect = lambda path, _value: bridge._on_dlss_setting_changed(setting_by_path[path])

        with (
            patch.object(_settings_bridge, "_read_captured_remix_config", return_value=captured_config),
            patch.object(bridge, "_push_config_value") as push_config,
        ):
            # Act
            bridge._sync_dlss_settings_from_capture()

        # Assert
        settings.set.assert_has_calls(
            [call(setting.setting_path, value) for setting, value in zip(captured_settings, expected_values)]
        )
        push_config.assert_not_called()
        self.assertFalse(bridge._syncing_dlss_settings)
        self.assertTrue(all(setting not in bridge._pending_dlss_settings for setting in captured_settings))

    def test_sync_dlss_settings_from_capture_when_schema_is_legacy_queues_current_defaults(self):
        """Pre-release capture settings should not override the release defaults."""
        # Arrange
        captured_config = {
            _settings_bridge._LEGACY_DLSS_MODEL_RUNTIME_KEY: "2",
            DLSS_TONE_INTENSITY.runtime_key: "1",
            DLSS_STRUCTURE_INTENSITY.runtime_key: "1",
        }
        settings = MagicMock()
        bridge = HdRemixSettingsBridge.__new__(HdRemixSettingsBridge)
        bridge._settings = settings
        bridge._pending_dlss_settings = set()
        bridge._syncing_dlss_settings = False

        with (
            patch.object(_settings_bridge, "_read_captured_remix_config", return_value=captured_config),
            patch.object(bridge, "_schedule_settings_push") as schedule_push,
        ):
            # Act
            bridge._sync_dlss_settings_from_capture()

        # Assert
        settings.set.assert_has_calls(
            [call(setting.setting_path, coerce_dlss_value(setting, None)) for setting in DLSS_SETTINGS]
        )
        self.assertEqual(bridge._pending_dlss_settings, set(DLSS_SETTINGS))
        self.assertFalse(bridge._syncing_dlss_settings)
        schedule_push.assert_called_once_with()

    def test_capture_import_ignores_malformed_dlss_values(self):
        """Malformed captured values should not replace controls or touch the runtime."""
        # Arrange
        captured_config = {
            DLSS_ENABLE.runtime_key: "maybe",
            DLSS_MODEL.runtime_key: "3",
            DLSS_INTENSITY.runtime_key: "nan",
            DLSS_HIGHLIGHT_RECOVERY_THRESHOLDS.runtime_key: "1, 2, 3",
        }
        settings = MagicMock()
        bridge = HdRemixSettingsBridge.__new__(HdRemixSettingsBridge)
        bridge._settings = settings
        bridge._pending_dlss_settings = set()
        bridge._syncing_dlss_settings = False

        with (
            patch.object(_settings_bridge, "_read_captured_remix_config", return_value=captured_config),
            patch.object(bridge, "_push_config_value") as push_config,
        ):
            # Act
            bridge._sync_dlss_settings_from_capture()

        # Assert
        settings.set.assert_not_called()
        push_config.assert_not_called()
        self.assertFalse(bridge._syncing_dlss_settings)

    async def test_dlss_change_before_readiness_pushes_latest_value_once(self):
        """Pre-readiness edits should coalesce per setting and apply the latest value."""
        # Arrange
        setting = DLSS_INTENSITY
        settings = MagicMock()
        settings.get.return_value = 0.25
        app = MagicMock()
        app.next_update_async = AsyncMock()
        bridge = HdRemixSettingsBridge.__new__(HdRemixSettingsBridge)
        bridge._settings = settings
        bridge._is_running = True
        bridge._syncing_dlss_settings = False
        bridge._pending_dlss_settings = set()
        bridge._settings_push_task = None
        bridge._initial_integrator_push_pending = False

        with (
            patch.object(_settings_bridge, "is_remix_extern_ready", return_value=False),
            patch.object(_settings_bridge, "_wait_for_remix_extern_async", new=AsyncMock(return_value=True)),
            patch.object(_settings_bridge.omni.kit.app, "get_app", return_value=app),
            patch.object(_settings_bridge, "_hdremix_set_configvar") as mock_set,
        ):
            # Act
            bridge._on_dlss_setting_changed(setting)
            settings.get.return_value = 0.75
            bridge._on_dlss_setting_changed(setting)
            calls_before_readiness = list(mock_set.call_args_list)
            await bridge._settings_push_task

        # Assert
        self.assertEqual(calls_before_readiness, [])
        mock_set.assert_called_once_with(setting.runtime_key, "0.75")
        self.assertEqual(bridge._pending_dlss_settings, set())

    def test_dlss_change_after_stop_does_not_schedule_or_push(self):
        """Changes received after stop should not schedule work or touch the runtime."""
        # Arrange
        setting = DLSS_ENABLE
        settings = MagicMock()
        settings.get.side_effect = {_SETTINGS_LEGACY_MIGRATION_DONE: True}.get
        with patch.object(_settings_bridge.carb.settings, "get_settings", return_value=settings):
            bridge = HdRemixSettingsBridge()
        bridge.stop()

        with (
            patch.object(_settings_bridge, "is_remix_extern_ready") as is_ready,
            patch.object(bridge, "_schedule_settings_push") as schedule_push,
            patch.object(bridge, "_push_dlss_setting") as push_setting,
        ):
            # Act
            bridge._on_dlss_setting_changed(setting)

        # Assert
        is_ready.assert_not_called()
        schedule_push.assert_not_called()
        push_setting.assert_not_called()
        self.assertEqual(bridge._pending_dlss_settings, set())
        bridge.destroy()

    async def test_stop_during_wait_prevents_runtime_push(self):
        """Stopping during extern discovery should cancel the deferred runtime write."""
        # Arrange
        wait_started = asyncio.Event()
        settings = MagicMock()
        settings.get.side_effect = {
            _SETTINGS_LEGACY_MIGRATION_DONE: True,
            SETTINGS_OVERRIDE_CAPTURE_INTEGRATOR: False,
        }.get
        event_manager = MagicMock()
        app = MagicMock()
        app.next_update_async = AsyncMock()

        async def wait_for_remix_extern():
            wait_started.set()
            await asyncio.Event().wait()

        with (
            patch.object(_settings_bridge.carb.settings, "get_settings", return_value=settings),
            patch.object(_settings_bridge, "_get_event_manager_instance", return_value=event_manager),
            patch.object(HdRemixSettingsBridge, "_poll_dlss_neural_rendering_support", new=AsyncMock()),
            patch.object(_settings_bridge, "_read_captured_remix_config", return_value={}),
            patch.object(
                _settings_bridge, "_wait_for_remix_extern_async", new=AsyncMock(side_effect=wait_for_remix_extern)
            ),
            patch.object(_settings_bridge.omni.kit.app, "get_app", return_value=app),
            patch.object(_settings_bridge, "_hdremix_set_configvar") as mock_set,
        ):
            bridge = HdRemixSettingsBridge()
            bridge.start()
            task = bridge._settings_push_task
            await wait_started.wait()

            # Act
            bridge.stop()
            await task

            # Assert
            mock_set.assert_not_called()
            bridge.destroy()

    async def test_passive_wait_uses_cached_support_state(self):
        """Passive readiness waiting should poll cached support without owning discovery."""
        # Arrange
        app = MagicMock()
        app.next_update_async = AsyncMock()
        with (
            patch.object(_settings_bridge, "is_remix_extern_ready", side_effect=[False, False, True]),
            patch.object(
                _settings_bridge, "is_remix_supported", return_value=(RemixSupport.WAITING_FOR_INIT, "waiting")
            ),
            patch.object(_settings_bridge, "is_remix_timeout", return_value=False),
            patch.object(_settings_bridge.omni.kit.app, "get_app", return_value=app),
        ):
            # Act
            result = await _wait_for_remix_extern_async()

            # Assert
            self.assertTrue(result)
            self.assertEqual(app.next_update_async.await_count, 2)

    async def test_passive_wait_returns_false_when_renderer_is_not_supported(self):
        """A definitive unsupported result should stop waiting without yielding a frame."""
        # Arrange
        app = MagicMock()
        app.next_update_async = AsyncMock()
        with (
            patch.object(_settings_bridge, "is_remix_extern_ready", return_value=False),
            patch.object(
                _settings_bridge, "is_remix_supported", return_value=(RemixSupport.NOT_SUPPORTED, "unsupported")
            ),
            patch.object(_settings_bridge, "is_remix_timeout", return_value=False),
            patch.object(_settings_bridge.omni.kit.app, "get_app", return_value=app),
        ):
            # Act
            result = await _wait_for_remix_extern_async()

        # Assert
        self.assertFalse(result)
        app.next_update_async.assert_not_awaited()

    async def test_poll_dlss_support_while_waiting_then_supported_publishes_available(self):
        """The capability poll should remain hidden until native discovery reports support."""
        # Arrange
        settings = MagicMock()
        writes_during_wait = []

        async def capture_writes_during_wait():
            """Capture visibility writes made before the next capability query."""
            writes_during_wait.extend(settings.set.call_args_list)

        app = MagicMock()
        app.next_update_async = AsyncMock(side_effect=capture_writes_during_wait)
        bridge = HdRemixSettingsBridge.__new__(HdRemixSettingsBridge)
        bridge._settings = settings
        bridge._is_running = True

        with (
            patch.object(_settings_bridge, "_wait_for_remix_extern_async", new=AsyncMock(return_value=True)),
            patch.object(
                _settings_bridge,
                "get_dlss_neural_rendering_support",
                side_effect=[RemixSupport.WAITING_FOR_INIT, RemixSupport.SUPPORTED],
            ) as get_support,
            patch.object(_settings_bridge.omni.kit.app, "get_app", return_value=app),
        ):
            # Act
            await bridge._poll_dlss_neural_rendering_support()

        # Assert
        self.assertEqual(writes_during_wait, [])
        self.assertEqual(get_support.call_count, 2)
        app.next_update_async.assert_awaited_once_with()
        settings.set.assert_called_once_with(_settings_bridge.SETTINGS_DLSS_NEURAL_RENDERING_AVAILABLE, True)

    async def test_poll_dlss_support_when_not_supported_publishes_unavailable(self):
        """A definitive native failure should keep DLSS Neural Rendering settings hidden."""
        # Arrange
        settings = MagicMock()
        app = MagicMock()
        app.next_update_async = AsyncMock()
        bridge = HdRemixSettingsBridge.__new__(HdRemixSettingsBridge)
        bridge._settings = settings
        bridge._is_running = True

        with (
            patch.object(_settings_bridge, "_wait_for_remix_extern_async", new=AsyncMock(return_value=True)),
            patch.object(
                _settings_bridge, "get_dlss_neural_rendering_support", return_value=RemixSupport.NOT_SUPPORTED
            ),
            patch.object(_settings_bridge.omni.kit.app, "get_app", return_value=app),
        ):
            # Act
            await bridge._poll_dlss_neural_rendering_support()

        # Assert
        settings.set.assert_called_once_with(_settings_bridge.SETTINGS_DLSS_NEURAL_RENDERING_AVAILABLE, False)
        app.next_update_async.assert_not_awaited()

    async def test_stop_with_pending_dlss_support_poll_cancels_task_and_hides_settings(self):
        """Stopping the bridge should cancel capability discovery and clear published availability."""
        # Arrange
        settings = MagicMock()
        support_task = MagicMock()
        support_task.done.return_value = False
        bridge = HdRemixSettingsBridge.__new__(HdRemixSettingsBridge)
        bridge._settings = settings
        bridge._is_running = True
        bridge._pending_dlss_settings = {DLSS_ENABLE}
        bridge._initial_integrator_push_pending = True
        bridge._syncing_dlss_settings = True
        bridge._dlss_neural_rendering_support_task = support_task
        bridge._settings_push_task = None
        bridge._capture_layer_imported_sub = None
        bridge._integrate_indirect_sub = None
        bridge._override_capture_sub = None
        bridge._dlss_subscriptions = []

        # Act
        bridge.stop()

        # Assert
        support_task.cancel.assert_called_once_with()
        self.assertIsNone(bridge._dlss_neural_rendering_support_task)
        self.assertFalse(bridge._is_running)
        self.assertEqual(bridge._pending_dlss_settings, set())
        self.assertFalse(bridge._initial_integrator_push_pending)
        self.assertFalse(bridge._syncing_dlss_settings)
        self.assertIsNone(bridge._settings_push_task)
        self.assertIsNone(bridge._capture_layer_imported_sub)
        settings.set.assert_called_once_with(_settings_bridge.SETTINGS_DLSS_NEURAL_RENDERING_AVAILABLE, False)

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

from pathlib import Path
from unittest.mock import patch

from lightspeed.aftermath.preload.core import (
    AFTERMATH_DLL_NAME,
    DXVK_CONFIG_FILE_ENV,
    DxvkConfigResult,
    PreloadResult,
    configure_dxvk_config,
    get_default_aftermath_dll_path,
    get_default_dxvk_config_path,
    get_configured_aftermath_dll_path,
    get_configured_dxvk_config_path,
    get_file_version,
    preload_aftermath,
)
from lightspeed.aftermath.preload.extension import (
    SETTING_CONFIGURE_DXVK,
    SETTING_ENABLED,
    SETTING_HDREMIX_AF_ENABLED,
    SETTING_KIT_AF_ENABLED,
    AftermathPreloadExtension,
    KIT_AF_ENABLED_SETTING,
)
from omni.kit.test import AsyncTestCase


class _FakeSettings(dict):
    def set(self, path, value):
        self[path] = value


class _FakeExtensionManager:
    def get_extension_path(self, _ext_id):
        return "C:/repo/exts/lightspeed.aftermath.preload"


class _FakeApp:
    def get_extension_manager(self):
        return _FakeExtensionManager()


class TestAftermathPreload(AsyncTestCase):
    async def test_default_path_uses_hydra_core_sibling(self):
        extension_path = Path("C:/repo/exts/lightspeed.aftermath.preload")

        result = get_default_aftermath_dll_path(extension_path)

        self.assertEqual(
            result,
            Path("C:/repo/exts/lightspeed.hydra.remix.core/deps/hdremix") / AFTERMATH_DLL_NAME,
        )

    async def test_default_dxvk_config_path_uses_extension_data(self):
        extension_path = Path("C:/repo/exts/lightspeed.aftermath.preload")

        result = get_default_dxvk_config_path(extension_path)

        self.assertEqual(result, extension_path / "data" / "dxvk.conf")

    async def test_configured_aftermath_dll_path_accepts_file_or_directory(self):
        file_path = f"C:/explicit/{AFTERMATH_DLL_NAME}"
        dir_path = "C:/explicit"

        self.assertEqual(get_configured_aftermath_dll_path(file_path), Path(file_path))
        self.assertEqual(get_configured_aftermath_dll_path(dir_path), Path(dir_path) / AFTERMATH_DLL_NAME)
        self.assertIsNone(get_configured_aftermath_dll_path(None))

    async def test_configured_dxvk_config_path_accepts_file_or_directory(self):
        self.assertEqual(get_configured_dxvk_config_path("C:/explicit/dxvk.conf"), Path("C:/explicit/dxvk.conf"))
        self.assertEqual(get_configured_dxvk_config_path("C:/explicit"), Path("C:/explicit/dxvk.conf"))
        self.assertIsNone(get_configured_dxvk_config_path(None))

    async def test_get_file_version_returns_none_when_not_windows(self):
        path = Path("C:/explicit/file.dll")
        with patch("lightspeed.aftermath.preload.core.os.name", "posix"):
            self.assertIsNone(get_file_version(path))

    async def test_preload_loads_existing_dll_and_keeps_handle_alive(self):
        handles = []
        handle = object()
        extension_path = Path("C:/repo/exts/lightspeed.aftermath.preload")
        expected_path = Path("C:/repo/exts/lightspeed.hydra.remix.core/deps/hdremix") / AFTERMATH_DLL_NAME

        with (
            patch.object(Path, "is_file", lambda path: path == expected_path),
            patch("lightspeed.aftermath.preload.core.ctypes.WinDLL", return_value=handle) as win_dll_mock,
            patch("lightspeed.aftermath.preload.core.get_file_version", return_value="2.18.0.0"),
            patch("lightspeed.aftermath.preload.core._LOADED_HANDLES", handles),
        ):
            result = preload_aftermath(extension_path)

        self.assertTrue(result.loaded)
        self.assertEqual(result.dll_path, expected_path)
        self.assertEqual(result.version, "2.18.0.0")
        win_dll_mock.assert_called_once_with(str(expected_path))
        self.assertEqual(handles, [handle])

    async def test_preload_reports_missing_dll(self):
        with patch.object(Path, "is_file", return_value=False):
            result = preload_aftermath(Path("C:/repo/exts/lightspeed.aftermath.preload"))

        self.assertFalse(result.loaded)
        self.assertEqual(result.reason, "missing")

    async def test_preload_reports_loader_failure(self):
        expected_path = Path("C:/explicit") / AFTERMATH_DLL_NAME

        with (
            patch.object(Path, "is_file", lambda path: path == expected_path),
            patch("lightspeed.aftermath.preload.core.ctypes.WinDLL", side_effect=OSError("boom")),
        ):
            result = preload_aftermath(
                Path("C:/repo/exts/lightspeed.aftermath.preload"),
                configured_dll_path="C:/explicit",
            )

        self.assertFalse(result.loaded)
        self.assertEqual(result.dll_path, expected_path)
        self.assertTrue(result.reason.startswith("load-failed: boom"))

    async def test_configure_dxvk_config_preserves_existing_env_value(self):
        with patch.dict(
            "lightspeed.aftermath.preload.core.os.environ",
            {DXVK_CONFIG_FILE_ENV: "C:/game/dxvk.conf"},
            clear=True,
        ) as env:
            result = configure_dxvk_config(Path("C:/repo/exts/lightspeed.aftermath.preload"))
            env_value = env[DXVK_CONFIG_FILE_ENV]

        self.assertEqual(
            result,
            DxvkConfigResult(
                config_path=Path("C:/game/dxvk.conf"),
                set_env=False,
                reason="existing-env",
            ),
        )
        self.assertEqual(env_value, "C:/game/dxvk.conf")

    async def test_configure_dxvk_config_uses_configured_path_before_cwd(self):
        configured_path = "C:/explicit/dxvk.conf"

        with (
            patch.dict("lightspeed.aftermath.preload.core.os.environ", {}, clear=True) as env,
            patch.object(Path, "is_file", return_value=True),
        ):
            result = configure_dxvk_config(
                Path("C:/repo/exts/lightspeed.aftermath.preload"),
                configured_config_path=configured_path,
            )
            env_value = env[DXVK_CONFIG_FILE_ENV]

        self.assertEqual(result.reason, "configured-path")
        self.assertEqual(result.config_path, Path(configured_path))
        self.assertTrue(result.set_env)
        self.assertEqual(env_value, str(Path(configured_path)))

    async def test_configure_dxvk_config_reports_missing_configured_path(self):
        configured_path = "C:/explicit/dxvk.conf"

        with (
            patch.dict("lightspeed.aftermath.preload.core.os.environ", {}, clear=True) as env,
            patch.object(Path, "is_file", return_value=False),
        ):
            result = configure_dxvk_config(
                Path("C:/repo/exts/lightspeed.aftermath.preload"),
                configured_config_path=configured_path,
            )
            env_has_dxvk_config = DXVK_CONFIG_FILE_ENV in env

        self.assertEqual(result.reason, "configured-missing")
        self.assertEqual(result.config_path, Path(configured_path))
        self.assertFalse(result.set_env)
        self.assertFalse(env_has_dxvk_config)

    async def test_configure_dxvk_config_uses_cwd_config_before_fallback(self):
        cwd = Path("C:/game")
        extension_path = Path("C:/repo/exts/lightspeed.aftermath.preload")

        with (
            patch.dict("lightspeed.aftermath.preload.core.os.environ", {}, clear=True) as env,
            patch("lightspeed.aftermath.preload.core.Path.cwd", return_value=cwd),
            patch.object(Path, "is_file", lambda path: path == cwd / "dxvk.conf"),
        ):
            result = configure_dxvk_config(extension_path)
            env_value = env[DXVK_CONFIG_FILE_ENV]

        self.assertEqual(result.reason, "cwd")
        self.assertEqual(result.config_path, cwd / "dxvk.conf")
        self.assertTrue(result.set_env)
        self.assertEqual(env_value, str(cwd / "dxvk.conf"))

    async def test_configure_dxvk_config_uses_fallback_when_no_env_or_cwd_config_exists(self):
        extension_path = Path("C:/repo/exts/lightspeed.aftermath.preload")
        fallback_path = extension_path / "data" / "dxvk.conf"

        with (
            patch.dict("lightspeed.aftermath.preload.core.os.environ", {}, clear=True) as env,
            patch("lightspeed.aftermath.preload.core.Path.cwd", return_value=Path("C:/other")),
            patch.object(Path, "is_file", lambda path: path == fallback_path),
        ):
            result = configure_dxvk_config(extension_path)
            env_value = env[DXVK_CONFIG_FILE_ENV]

        self.assertEqual(result.reason, "fallback")
        self.assertEqual(result.config_path, fallback_path)
        self.assertTrue(result.set_env)
        self.assertEqual(env_value, str(fallback_path))

    async def test_configure_dxvk_config_reports_missing_when_no_candidate_exists(self):
        with (
            patch.dict("lightspeed.aftermath.preload.core.os.environ", {}, clear=True) as env,
            patch("lightspeed.aftermath.preload.core.Path.cwd", return_value=Path("C:/game")),
            patch.object(Path, "is_file", return_value=False),
        ):
            result = configure_dxvk_config(Path("C:/repo/exts/lightspeed.aftermath.preload"))
            env_has_dxvk_config = DXVK_CONFIG_FILE_ENV in env

        self.assertEqual(result, DxvkConfigResult(config_path=None, set_env=False, reason="missing"))
        self.assertFalse(env_has_dxvk_config)


class TestAftermathPreloadExtension(AsyncTestCase):
    async def test_extension_disabled_leaves_settings_unchanged(self):
        # Arrange
        settings = _FakeSettings({SETTING_ENABLED: False})

        # Act
        with (
            patch("lightspeed.aftermath.preload.extension.carb.settings.get_settings", return_value=settings),
            patch("lightspeed.aftermath.preload.extension.carb.log_info"),
        ):
            AftermathPreloadExtension().on_startup("lightspeed.aftermath.preload")

        # Assert
        self.assertNotIn(KIT_AF_ENABLED_SETTING, settings)

    async def test_extension_allows_kit_aftermath_without_hdremix_setup(self):
        # Arrange
        settings = _FakeSettings(
            {
                SETTING_KIT_AF_ENABLED: True,
                SETTING_HDREMIX_AF_ENABLED: False,
            }
        )

        # Act
        with (
            patch("lightspeed.aftermath.preload.extension.carb.settings.get_settings", return_value=settings),
            patch("lightspeed.aftermath.preload.extension.configure_dxvk_config") as configure_dxvk_config_mock,
            patch("lightspeed.aftermath.preload.extension.preload_aftermath") as preload_aftermath_mock,
            patch("lightspeed.aftermath.preload.extension.carb.log_info"),
        ):
            AftermathPreloadExtension().on_startup("lightspeed.aftermath.preload")

        # Assert
        self.assertTrue(settings[KIT_AF_ENABLED_SETTING])
        configure_dxvk_config_mock.assert_not_called()
        preload_aftermath_mock.assert_not_called()

    async def test_extension_disables_kit_aftermath_without_hdremix_setup(self):
        # Arrange
        settings = _FakeSettings(
            {
                SETTING_KIT_AF_ENABLED: False,
                SETTING_HDREMIX_AF_ENABLED: False,
            }
        )

        # Act
        with (
            patch("lightspeed.aftermath.preload.extension.carb.settings.get_settings", return_value=settings),
            patch("lightspeed.aftermath.preload.extension.configure_dxvk_config") as configure_dxvk_config_mock,
            patch("lightspeed.aftermath.preload.extension.preload_aftermath") as preload_aftermath_mock,
            patch("lightspeed.aftermath.preload.extension.carb.log_info"),
        ):
            AftermathPreloadExtension().on_startup("lightspeed.aftermath.preload")

        # Assert
        self.assertFalse(settings[KIT_AF_ENABLED_SETTING])
        configure_dxvk_config_mock.assert_not_called()
        preload_aftermath_mock.assert_not_called()

    async def test_extension_disables_kit_aftermath_and_runs_hdremix_setup(self):
        # Arrange
        settings = _FakeSettings(
            {
                SETTING_KIT_AF_ENABLED: False,
                SETTING_HDREMIX_AF_ENABLED: True,
            }
        )
        dxvk_result = DxvkConfigResult(
            config_path=Path("C:/repo/exts/lightspeed.aftermath.preload/data/dxvk.conf"),
            set_env=True,
            reason="fallback",
        )
        preload_result = PreloadResult(
            dll_path=Path("C:/repo/exts/lightspeed.hydra.remix.core/deps/hdremix") / AFTERMATH_DLL_NAME,
            loaded=True,
            reason="loaded",
            version="2.18.0.0",
        )

        # Act
        with (
            patch("lightspeed.aftermath.preload.extension.carb.settings.get_settings", return_value=settings),
            patch("lightspeed.aftermath.preload.extension.omni.kit.app.get_app", return_value=_FakeApp()),
            patch(
                "lightspeed.aftermath.preload.extension.configure_dxvk_config", return_value=dxvk_result
            ) as configure_dxvk_config_mock,
            patch(
                "lightspeed.aftermath.preload.extension.preload_aftermath", return_value=preload_result
            ) as preload_aftermath_mock,
            patch("lightspeed.aftermath.preload.extension.carb.log_info"),
        ):
            AftermathPreloadExtension().on_startup("lightspeed.aftermath.preload")

        # Assert
        self.assertFalse(settings[KIT_AF_ENABLED_SETTING])
        configure_dxvk_config_mock.assert_called_once_with(Path("C:/repo/exts/lightspeed.aftermath.preload"), None)
        preload_aftermath_mock.assert_called_once_with(Path("C:/repo/exts/lightspeed.aftermath.preload"), None)

    async def test_extension_handles_existing_dxvk_config_and_successful_preload(self):
        # Arrange
        settings = _FakeSettings(
            {
                SETTING_KIT_AF_ENABLED: False,
                SETTING_HDREMIX_AF_ENABLED: True,
            }
        )
        dxvk_result = DxvkConfigResult(
            config_path=Path("C:/game/dxvk.conf"),
            set_env=False,
            reason="existing-env",
        )
        preload_result = PreloadResult(
            dll_path=Path("C:/repo/exts/lightspeed.hydra.remix.core/deps/hdremix") / AFTERMATH_DLL_NAME,
            loaded=True,
            reason="loaded",
        )

        # Act
        with (
            patch("lightspeed.aftermath.preload.extension.carb.settings.get_settings", return_value=settings),
            patch("lightspeed.aftermath.preload.extension.omni.kit.app.get_app", return_value=_FakeApp()),
            patch("lightspeed.aftermath.preload.extension.configure_dxvk_config", return_value=dxvk_result),
            patch("lightspeed.aftermath.preload.extension.preload_aftermath", return_value=preload_result),
            patch("lightspeed.aftermath.preload.extension.carb.log_info") as log_info_mock,
        ):
            AftermathPreloadExtension().on_startup("lightspeed.aftermath.preload")

        # Assert
        self.assertTrue(any("Preserving DXVK_CONFIG_FILE" in call.args[0] for call in log_info_mock.call_args_list))
        self.assertTrue(any("Preloaded" in call.args[0] for call in log_info_mock.call_args_list))

    async def test_extension_logs_disabled_dxvk_config_and_missing_preload(self):
        # Arrange
        settings = _FakeSettings(
            {
                SETTING_KIT_AF_ENABLED: False,
                SETTING_HDREMIX_AF_ENABLED: True,
                SETTING_CONFIGURE_DXVK: False,
            }
        )
        preload_result = PreloadResult(
            dll_path=Path("C:/repo/exts/lightspeed.hydra.remix.core/deps/hdremix") / AFTERMATH_DLL_NAME,
            loaded=False,
            reason="missing",
        )

        # Act
        with (
            patch("lightspeed.aftermath.preload.extension.carb.settings.get_settings", return_value=settings),
            patch("lightspeed.aftermath.preload.extension.omni.kit.app.get_app", return_value=_FakeApp()),
            patch("lightspeed.aftermath.preload.extension.configure_dxvk_config") as configure_dxvk_config_mock,
            patch("lightspeed.aftermath.preload.extension.preload_aftermath", return_value=preload_result),
            patch("lightspeed.aftermath.preload.extension.carb.log_info") as log_info_mock,
            patch("lightspeed.aftermath.preload.extension.carb.log_warn") as log_warn_mock,
        ):
            AftermathPreloadExtension().on_startup("lightspeed.aftermath.preload")

        # Assert
        configure_dxvk_config_mock.assert_not_called()
        self.assertTrue(any("DXVK config setup disabled" in call.args[0] for call in log_info_mock.call_args_list))
        self.assertTrue(any("Failed to preload" in call.args[0] for call in log_warn_mock.call_args_list))

    async def test_extension_logs_dxvk_config_setup_warning(self):
        # Arrange
        settings = _FakeSettings(
            {
                SETTING_KIT_AF_ENABLED: False,
                SETTING_HDREMIX_AF_ENABLED: True,
            }
        )
        dxvk_result = DxvkConfigResult(config_path=None, set_env=False, reason="missing")
        preload_result = PreloadResult(
            dll_path=Path("C:/repo/exts/lightspeed.hydra.remix.core/deps/hdremix") / AFTERMATH_DLL_NAME,
            loaded=False,
            reason="missing",
        )

        # Act
        with (
            patch("lightspeed.aftermath.preload.extension.carb.settings.get_settings", return_value=settings),
            patch("lightspeed.aftermath.preload.extension.omni.kit.app.get_app", return_value=_FakeApp()),
            patch("lightspeed.aftermath.preload.extension.configure_dxvk_config", return_value=dxvk_result),
            patch("lightspeed.aftermath.preload.extension.preload_aftermath", return_value=preload_result),
            patch("lightspeed.aftermath.preload.extension.carb.log_info"),
            patch("lightspeed.aftermath.preload.extension.carb.log_warn") as log_warn_mock,
        ):
            AftermathPreloadExtension().on_startup("lightspeed.aftermath.preload")

        # Assert
        self.assertTrue(any("DXVK config setup did not set" in call.args[0] for call in log_warn_mock.call_args_list))

    async def test_extension_shutdown_logs(self):
        with patch("lightspeed.aftermath.preload.extension.carb.log_info") as log_info_mock:
            AftermathPreloadExtension().on_shutdown()

        log_info_mock.assert_called_once_with("[lightspeed.aftermath.preload] shutdown")

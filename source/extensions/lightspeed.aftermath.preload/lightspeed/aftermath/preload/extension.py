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

import carb
import carb.settings
import omni.ext
import omni.kit.app

from .core import configure_dxvk_config, preload_aftermath


SETTING_PREFIX = "/exts/lightspeed.aftermath.preload"
SETTING_ENABLED = f"{SETTING_PREFIX}/enabled"
SETTING_KIT_AF_ENABLED = f"{SETTING_PREFIX}/kitAftermathEnabled"
SETTING_HDREMIX_AF_ENABLED = f"{SETTING_PREFIX}/hdremixAftermathEnabled"
SETTING_CONFIGURE_DXVK = f"{SETTING_PREFIX}/configureDxvk"
SETTING_DXVK_CONFIG_PATH = f"{SETTING_PREFIX}/dxvkConfigPath"
SETTING_DLL_PATH = f"{SETTING_PREFIX}/dllPath"
KIT_AF_ENABLED_SETTING = "/renderer/debug/aftermath/enabled"


def _get_bool(settings, path: str, default: bool) -> bool:
    value = settings.get(path)
    return default if value is None else bool(value)


class AftermathPreloadExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        settings = carb.settings.get_settings()
        enabled = _get_bool(settings, SETTING_ENABLED, True)
        if not enabled:
            carb.log_info(
                "[lightspeed.aftermath.preload] Extension disabled; leaving Kit and DXVK/HdRemix Aftermath settings "
                "unchanged"
            )
            return

        kit_af_enabled = _get_bool(settings, SETTING_KIT_AF_ENABLED, False)
        settings.set(KIT_AF_ENABLED_SETTING, kit_af_enabled)
        carb.log_info(
            f"[lightspeed.aftermath.preload] {'Enabled' if kit_af_enabled else 'Disabled'} Kit-owned NVIDIA Aftermath"
        )

        if not _get_bool(settings, SETTING_HDREMIX_AF_ENABLED, True):
            carb.log_info("[lightspeed.aftermath.preload] Skipped DXVK/HdRemix Aftermath setup")
            return

        ext_manager = omni.kit.app.get_app().get_extension_manager()
        extension_path = Path(ext_manager.get_extension_path(ext_id))

        if _get_bool(settings, SETTING_CONFIGURE_DXVK, True):
            dxvk_config_result = configure_dxvk_config(extension_path, settings.get(SETTING_DXVK_CONFIG_PATH))
            if dxvk_config_result.reason in {"configured-path", "cwd", "fallback"}:
                carb.log_info(
                    f"[lightspeed.aftermath.preload] Set DXVK_CONFIG_FILE={dxvk_config_result.config_path} "
                    f"reason={dxvk_config_result.reason}"
                )
            elif dxvk_config_result.reason == "existing-env":
                carb.log_info(
                    f"[lightspeed.aftermath.preload] Preserving DXVK_CONFIG_FILE={dxvk_config_result.config_path}"
                )
            else:
                carb.log_warn(
                    f"[lightspeed.aftermath.preload] DXVK config setup did not set DXVK_CONFIG_FILE: "
                    f"{dxvk_config_result.reason}"
                )
        else:
            carb.log_info("[lightspeed.aftermath.preload] DXVK config setup disabled")

        result = preload_aftermath(extension_path, settings.get(SETTING_DLL_PATH))

        if result.loaded:
            version = f" version={result.version}" if result.version else ""
            carb.log_info(f"[lightspeed.aftermath.preload] Preloaded {result.dll_path}{version}")
        else:
            carb.log_warn(f"[lightspeed.aftermath.preload] Failed to preload {result.dll_path}: {result.reason}")

    def on_shutdown(self):
        carb.log_info("[lightspeed.aftermath.preload] shutdown")

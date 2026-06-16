"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

import os
import sys

import carb
import lightspeed.hydra.remix.core.extern as extern
import omni.ext
import omni.kit.app
import omni.usd
from pxr import Plug


class HdRemixFinalizer(omni.ext.IExt):
    """Loads HdRemix.dll early and shows whether Remix is supported"""

    def __init__(self):
        super().__init__()
        self._hdremix_dll_dir_tokens = None

    def on_startup(self, ext_id):
        carb.log_info("[lightspeed.hydra.remix.core] Startup")
        self._preload_hdremix_dll(ext_id)
        carb.log_info(
            "[lightspeed.hydra.remix.core] Deferring HdRemix support polling until a real viewport requests it."
        )

    def _preload_hdremix_dll(self, ext_id):
        """Register HdRemix.dll's directory for Python ctypes DLL resolution.

        HdRemix.dll imports RemixParticleSystem.dll from a nested plugin folder.
        PATH is pre-populated with both HdRemix package DLL directories via extension.toml [[env]] so that
        USD's LoadLibraryW calls can resolve the renderer plugin before Python on_startup runs.

        os.add_dll_directory registers the directory for LOAD_LIBRARY_SEARCH_DEFAULT_DIRS,
        which is the search mode used by Python 3.8+ ctypes calls (e.g. check_support).
        The token is kept alive for the extension's lifetime; closing it removes the dir.
        """
        if sys.platform != "win32":
            carb.log_info(f"[lightspeed.hydra.remix.core] Skipping Windows HdRemix DLL registration on {sys.platform}.")
            return
        ext_path = omni.kit.app.get_app().get_extension_manager().get_extension_path(ext_id)
        hdremix_dir = os.path.normpath(os.path.join(ext_path, "deps", "hdremix"))
        particle_system_dir = os.path.normpath(os.path.join(hdremix_dir, "usd", "plugins", "RemixParticleSystem"))
        hdremix_dll_path = os.path.normpath(os.path.join(hdremix_dir, "HdRemix.dll"))
        if not os.path.isdir(hdremix_dir):
            message = f"HdRemix DLL directory not found: {hdremix_dir}"
            carb.log_error(f"[lightspeed.hydra.remix.core] {message}")
            extern.mark_remix_not_supported(message)
            return

        dll_search_paths = [hdremix_dir]
        self._hdremix_dll_dir_tokens = [os.add_dll_directory(hdremix_dir)]
        if os.path.isdir(particle_system_dir):
            self._hdremix_dll_dir_tokens.append(os.add_dll_directory(particle_system_dir))
            dll_search_paths.append(particle_system_dir)
            carb.log_info(f"[lightspeed.hydra.remix.core] Registered particle DLL search path: {particle_system_dir}")
        else:
            carb.log_warn(
                f"[lightspeed.hydra.remix.core] Remix particle DLL directory not found: {particle_system_dir}"
            )
        os.environ["PATH"] = os.pathsep.join([*dll_search_paths, os.environ.get("PATH", "")])
        carb.log_info(f"[lightspeed.hydra.remix.core] Registered DLL search path: {hdremix_dir}")

        preload_ok, preload_message = extern.RemixExtern.preload_hdremix_dll(hdremix_dll_path)
        if preload_ok:
            carb.log_info(f"[lightspeed.hydra.remix.core] {preload_message}")
        else:
            carb.log_error(f"[lightspeed.hydra.remix.core] {preload_message}")
            extern.mark_remix_not_supported(preload_message)
            return

        # Kit 110 no longer appears to discover HdRemix reliably via PXR_PLUGINPATH_NAME alone during startup.
        # Register the plugin directory explicitly so the HdRemix render delegate is visible before viewport init.
        plugins = Plug.Registry().RegisterPlugins(hdremix_dir)
        if plugins:
            carb.log_info(
                f"[lightspeed.hydra.remix.core] Registered USD plugins from {hdremix_dir}: "
                f"{', '.join(plugin.name for plugin in plugins)}"
            )
        else:
            message = (
                f"No USD plugins were registered from {hdremix_dir}. HdRemixRendererPlugin may remain undiscoverable."
            )
            carb.log_error(f"[lightspeed.hydra.remix.core] {message}")
            extern.mark_remix_not_supported(message)

    def on_shutdown(self):
        carb.log_info("[lightspeed.hydra.remix.core] Shutdown")
        extern.remix_extern_destroy()
        if self._hdremix_dll_dir_tokens:
            for token in self._hdremix_dll_dir_tokens:
                token.close()
            self._hdremix_dll_dir_tokens = None

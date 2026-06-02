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

import ctypes
import os
from dataclasses import dataclass
from pathlib import Path


AFTERMATH_DLL_NAME = "GFSDK_Aftermath_Lib.x64.dll"
HYDRA_REMIX_CORE_EXTENSION = "lightspeed.hydra.remix.core"
DXVK_CONFIG_FILE_ENV = "DXVK_CONFIG_FILE"
DXVK_CONFIG_FILE_NAME = "dxvk.conf"

_LOADED_HANDLES = []


@dataclass(frozen=True)
class DxvkConfigResult:
    config_path: Path | None
    set_env: bool
    reason: str


@dataclass(frozen=True)
class PreloadResult:
    dll_path: Path
    loaded: bool
    reason: str
    version: str | None = None


def get_default_aftermath_dll_path(extension_path: Path) -> Path:
    return extension_path.parent / HYDRA_REMIX_CORE_EXTENSION / "deps" / "hdremix" / AFTERMATH_DLL_NAME


def get_default_dxvk_config_path(extension_path: Path) -> Path:
    return extension_path / "data" / DXVK_CONFIG_FILE_NAME


def get_configured_aftermath_dll_path(configured_path: str | None) -> Path | None:
    if not configured_path:
        return None

    path = Path(os.path.expandvars(configured_path))
    if path.name.lower() != AFTERMATH_DLL_NAME.lower():
        path = path / AFTERMATH_DLL_NAME
    return path


def get_configured_dxvk_config_path(configured_path: str | None) -> Path | None:
    if not configured_path:
        return None

    path = Path(os.path.expandvars(configured_path))
    if path.name.lower() != DXVK_CONFIG_FILE_NAME:
        path = path / DXVK_CONFIG_FILE_NAME
    return path


def get_file_version(path: Path) -> str | None:
    if os.name != "nt":
        return None

    try:
        size = ctypes.windll.version.GetFileVersionInfoSizeW(str(path), None)
        if not size:
            return None

        buffer = ctypes.create_string_buffer(size)
        if not ctypes.windll.version.GetFileVersionInfoW(str(path), 0, size, buffer):
            return None

        value = ctypes.c_void_p()
        value_size = ctypes.c_uint()
        if not ctypes.windll.version.VerQueryValueW(
            buffer,
            "\\",
            ctypes.byref(value),
            ctypes.byref(value_size),
        ):
            return None

        words = ctypes.cast(value, ctypes.POINTER(ctypes.c_uint32))
        ms = words[2]
        ls = words[3]
        return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"
    except (AttributeError, OSError, ValueError):
        return None


def configure_dxvk_config(
    extension_path: Path,
    configured_config_path: str | None = None,
) -> DxvkConfigResult:
    existing_config = os.environ.get(DXVK_CONFIG_FILE_ENV)
    if existing_config:
        return DxvkConfigResult(
            config_path=Path(os.path.expandvars(existing_config)),
            set_env=False,
            reason="existing-env",
        )

    configured_path = get_configured_dxvk_config_path(configured_config_path)
    if configured_path:
        if configured_path.is_file():
            os.environ[DXVK_CONFIG_FILE_ENV] = str(configured_path)
            return DxvkConfigResult(config_path=configured_path, set_env=True, reason="configured-path")
        return DxvkConfigResult(config_path=configured_path, set_env=False, reason="configured-missing")

    cwd_config_path = Path.cwd() / DXVK_CONFIG_FILE_NAME
    if cwd_config_path.is_file():
        os.environ[DXVK_CONFIG_FILE_ENV] = str(cwd_config_path)
        return DxvkConfigResult(config_path=cwd_config_path, set_env=True, reason="cwd")

    fallback_path = get_default_dxvk_config_path(extension_path)
    if fallback_path.is_file():
        os.environ[DXVK_CONFIG_FILE_ENV] = str(fallback_path)
        return DxvkConfigResult(config_path=fallback_path, set_env=True, reason="fallback")

    return DxvkConfigResult(config_path=None, set_env=False, reason="missing")


def preload_aftermath(
    extension_path: Path,
    configured_dll_path: str | None = None,
) -> PreloadResult:
    dll_path = get_configured_aftermath_dll_path(configured_dll_path) or get_default_aftermath_dll_path(extension_path)

    if not dll_path.is_file():
        return PreloadResult(dll_path=dll_path, loaded=False, reason="missing")

    try:
        handle = ctypes.WinDLL(str(dll_path))
    except OSError as exc:
        return PreloadResult(dll_path=dll_path, loaded=False, reason=f"load-failed: {exc}")

    _LOADED_HANDLES.append(handle)
    return PreloadResult(
        dll_path=dll_path,
        loaded=True,
        reason="loaded",
        version=get_file_version(dll_path),
    )

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

__all__ = ["RecentProjectsCore"]


import asyncio
import json
import math
import os
import shutil
from enum import Enum
from pathlib import Path

import carb
import carb.tokens
import omni.client
import omni.usd
from lightspeed.layer_manager.core import (
    LSS_LAYER_GAME_NAME,
    LSS_LAYER_MOD_NAME,
    LSS_LAYER_MOD_VERSION,
    LayerType,
    LayerTypeKeys,
)
from omni.flux.utils.common.omni_url import OmniUrl
from pxr import Sdf, Tf


class UsdFileSignature(Enum):
    """Supported USD file extensions and their valid binary header signatures."""

    USDA = (".usda", (b"#usda 1.",))
    USDC = (".usdc", (b"PXR-USDC",))
    USDZ = (".usdz", (b"PK\x03\x04",))
    USD = (".usd", (b"#usda 1.", b"PXR-USDC"))

    @property
    def extension(self) -> str:
        return self.value[0]

    @property
    def signatures(self) -> tuple[bytes, ...]:
        return self.value[1]

    @classmethod
    def for_extension(cls, ext: str) -> "UsdFileSignature | None":
        for member in cls:
            if member.extension == ext:
                return member
        return None


class RecentProjectsCore:
    def __get_recent_dir(self) -> str:
        """Return the file"""
        token = carb.tokens.get_tokens_interface()
        directory = token.resolve("${app_documents}")
        # FilePickerDialog needs the capital drive. In case it's linux, the
        # first letter will be / and it's still OK.
        return str(Path(directory[:1].upper() + directory[1:]).resolve())

    def __get_recent_file(self) -> str:
        """Return the file"""
        directory = self.__get_recent_dir()
        return f"{directory}/recent_saved_file.json"

    def save_recent_file(self, data):
        """Save the recent work files to the file"""
        file_path = self.__get_recent_file()
        try:
            Path(file_path).parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, "w", encoding="utf8") as json_file:
                json.dump(data, json_file, indent=2)
        except OSError as exc:
            carb.log_warn(f"[RecentProjectsCore] Could not save recent file '{file_path}': {exc}")
            return
        carb.log_info(f"Recent saved file tracker saved to {file_path}")

    def append_path_to_recent_file(self, path: str, game: str, capture: str, save: bool = True):
        """Append a work file path to file"""
        current_data = self.get_recent_file_data()

        if path in current_data:
            del current_data[path]
        current_data[path] = {"game": game, "capture": capture}
        result = {}
        for i, (item_path, item_data) in enumerate(current_data.items()):
            result[item_path] = item_data
            if i == 40:
                break
        if save:
            self.save_recent_file(result)
        return result

    def remove_path_from_recent_file(self, path: str, save: bool = True):
        """Remove a work file path from file"""
        current_data = self.get_recent_file_data()

        if path not in current_data:
            return current_data

        del current_data[path]

        if save:
            self.save_recent_file(current_data)

        return current_data

    def is_recent_file_exist(self):
        file_path = self.__get_recent_file()
        if not Path(file_path).exists():
            carb.log_info(f"Recent saved file tracker doesn't exist: {file_path}")
            return False
        return True

    def get_recent_file_data(self):
        """Load the recent work files from the file"""
        if not self.is_recent_file_exist():
            return {}
        file_path = self.__get_recent_file()
        carb.log_info(f"Get recent saved file(s) from {file_path}")
        try:
            with open(file_path, encoding="utf8") as json_file:
                raw = json.load(json_file)
        except json.JSONDecodeError:
            carb.log_warn(f"[RecentProjectsCore] {file_path} is corrupted! Attempting backup.")
            try:
                shutil.copyfile(file_path, f"{file_path}.bak")
                Path(file_path).unlink()
                carb.log_warn(f"[RecentProjectsCore] Corrupt file backed up to {file_path}.bak")
            except OSError as exc:
                carb.log_warn(f"[RecentProjectsCore] Could not back up corrupt file: {exc}")
            return {}
        except OSError as exc:
            carb.log_warn(f"[RecentProjectsCore] Could not read recent file '{file_path}': {exc}")
            return {}

        if not isinstance(raw, dict):
            carb.log_warn(f"[RecentProjectsCore] Recent file is not a dict (got {type(raw).__name__})")
            return {}

        result = {}
        for path, entry in raw.items():
            ok, reason = self._validate_json_entry(path, entry)
            if not ok:
                carb.log_warn(f"[RecentProjectsCore] Skipping malformed entry: {reason}")
                continue
            result[path] = entry
        return result

    def get_path_detail(
        self, path, recent_file_data: dict[str, dict[str, str]] | None = None
    ) -> dict[str, str | list[tuple[str, str]]]:
        """Get details from the given path"""

        if recent_file_data is None:
            recent_file_data = self.get_recent_file_data()

        ok, reason = self._validate_path(path)
        if not ok:
            carb.log_warn(f"[RecentProjectsCore] get_path_detail skipped: {reason}")
            return {
                "Invalid": [(path, reason)],
                "Game": recent_file_data.get("game", None),
                "Capture": recent_file_data.get("capture", None),
            }

        ok, reason = self._validate_usd_file(path)
        if not ok:
            carb.log_warn(f"[RecentProjectsCore] get_path_detail skipped: {reason}")
            return {
                "Invalid": [(path, reason)],
                "Game": recent_file_data.get("game", None),
                "Capture": recent_file_data.get("capture", None),
            }

        result = {}
        recent_url = OmniUrl(path)
        if not recent_url.exists:
            return result

        if path in recent_file_data:
            result["Game"] = recent_file_data[path].get("game", "")
            result["Capture"] = recent_file_data[path].get("capture", "")
            result["Invalid"] = []

            try:
                project_layer = Sdf.Layer.FindOrOpen(path)
            except (Tf.ErrorException, RuntimeError) as exc:
                carb.log_warn(f"[RecentProjectsCore] Could not open project layer '{path}': {exc}")
                result["Invalid"].append((path, str(exc)))
                project_layer = None

            if project_layer:
                for sublayer_path in project_layer.subLayerPaths:
                    resolved = Sdf.ComputeAssetPathRelativeToLayer(project_layer, sublayer_path)
                    ok, reason = self._validate_usd_layer(resolved)
                    if not ok:
                        carb.log_warn(f"[RecentProjectsCore] Skipping sublayer '{sublayer_path}': {reason}")
                        result["Invalid"].append((sublayer_path, reason))
                        continue

                    try:
                        sublayer = Sdf.Layer.FindOrOpenRelativeToLayer(project_layer, sublayer_path)
                    except (Tf.ErrorException, RuntimeError) as exc:
                        carb.log_warn(f"[RecentProjectsCore] Could not open sublayer '{sublayer_path}': {exc}")
                        result["Invalid"].append((sublayer_path, str(exc)))
                        continue
                    if not sublayer:
                        continue
                    metadata = sublayer.customLayerData
                    match metadata.get(LayerTypeKeys.layer_type.value):
                        case LayerType.replacement.value:
                            if "Name" not in result:
                                result["Name"] = metadata.get(LSS_LAYER_MOD_NAME)
                            if "Version" not in result:
                                result["Version"] = metadata.get(LSS_LAYER_MOD_VERSION)
                        case LayerType.capture.value:
                            result["Capture"] = sublayer.realPath
                            result["Game"] = metadata.get(LSS_LAYER_GAME_NAME)
                        case _:
                            pass

        if not recent_url.entry:
            carb.log_warn(f"[RecentProjectsCore] No entry metadata available for '{path}'")
            return result

        result["Published"] = recent_url.entry.modified_time.strftime("%m/%d/%Y, %H:%M:%S")
        result["Size"] = self.convert_size(recent_url.entry.size)
        return result

    @staticmethod
    @omni.usd.handle_exception
    async def find_thumbnail_async(path: str, auto=False):
        if not path.strip() or ".thumbs" in path:
            return None, None
        parent_dir = os.path.dirname(path)
        item_name = os.path.basename(path)
        if auto:
            thumbnail = f"{parent_dir}/.thumbs/256x256/{item_name}.auto.png"
        else:
            thumbnail = f"{parent_dir}/.thumbs/256x256/{item_name}.png"

        try:
            result, _ = await asyncio.wait_for(omni.client.stat_async(thumbnail), timeout=10.0)
        except (Exception, asyncio.TimeoutError):  # noqa: BLE001
            result = omni.client.Result.ERROR_NOT_FOUND
        if result == omni.client.Result.OK:
            return path, thumbnail
        if not auto:
            return await RecentProjectsCore.find_thumbnail_async(path, auto=True)
        return None, None

    @staticmethod
    def convert_size(size_bytes):
        if size_bytes <= 0:
            return "0B"
        size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
        i = int(math.floor(math.log(size_bytes, 1024)))
        i = min(i, len(size_name) - 1)
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        return f"{s} {size_name[i]}"

    @staticmethod
    def _validate_path(path: str) -> tuple[bool, str]:
        if not path or not path.strip():
            return False, "path is empty"
        p = Path(path)
        if not p.exists():
            return False, f"path does not exist: {path}"
        if not p.is_file():
            return False, f"path is not a file: {path}"
        return True, ""

    @staticmethod
    def _validate_json_entry(path: str, entry: object) -> tuple[bool, str]:
        if not isinstance(entry, dict):
            return False, f"entry for '{path}' is not a dict (got {type(entry).__name__})"
        for key in ("game", "capture"):
            if key not in entry:
                return False, f"entry for '{path}' is missing required key '{key}'"
        return True, ""

    @staticmethod
    def _validate_usd_file(path: str) -> tuple[bool, str]:
        suffix = Path(path).suffix.lower()
        sig_entry = UsdFileSignature.for_extension(suffix)
        if sig_entry is None:
            return False, f"'{path}' has unsupported extension '{suffix}'"
        if not os.access(path, os.R_OK):
            return False, f"'{path}' is not readable (permission denied)"

        try:
            with open(path, "rb") as f:
                header = f.read(8)
        except OSError as exc:
            return False, f"'{path}' could not be read: {exc}"

        if not header:
            return False, f"'{path}' is empty"

        if not any(header.startswith(sig) for sig in sig_entry.signatures):
            readable = header.hex()
            return False, (
                f"'{path}' has an unrecognised header (got 0x{readable}, "
                f"expected one of {[s.hex() for s in sig_entry.signatures]})"
            )

        return True, ""

    @staticmethod
    def _validate_usd_layer(path: str) -> tuple[bool, str]:
        ok, reason = RecentProjectsCore._validate_path(path)
        if not ok:
            return False, reason
        return RecentProjectsCore._validate_usd_file(path)

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
import copy
import json
import math
import os
import shutil
import stat
import tempfile
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
from lightspeed.trex.utils.common.asset_utils import is_layer_from_capture
from omni.flux.utils.common.omni_url import OmniUrl
from pxr import Sdf, Tf

VALIDATION_CACHE_KEY = "validation"
VALIDATION_CACHE_SCHEMA = 2


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
        """Save the recent work files to the file."""
        file_path = self.__get_recent_file()
        file_directory = Path(file_path).parent
        temporary_path = None
        try:
            file_directory.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf8", dir=file_directory, delete=False) as json_file:
                temporary_path = json_file.name
                json.dump(data, json_file, indent=2)
            os.replace(temporary_path, file_path)
            temporary_path = None
        except OSError as exc:
            carb.log_warn(f"[RecentProjectsCore] Could not save recent file '{file_path}': {exc}")
            return
        finally:
            if temporary_path:
                try:
                    Path(temporary_path).unlink(missing_ok=True)
                except OSError as exc:
                    carb.log_warn(f"[RecentProjectsCore] Could not remove temporary file '{temporary_path}': {exc}")
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

    def get_path_detail(self, path, recent_file_data: dict[str, dict[str, object]] | None = None) -> dict[str, object]:
        """Return cached or validated details for a recent project path.

        Args:
            path: The project layer path to inspect.
            recent_file_data: Optional caller-owned recent-project data to update in memory.

        Returns:
            Project details, including validation failures when present.
        """

        owns_recent_file_data = recent_file_data is None
        if recent_file_data is None:
            recent_file_data = self.get_recent_file_data()

        entry = recent_file_data.get(path)
        recent_entry = entry if isinstance(entry, dict) else None
        if recent_entry is not None:
            cached_details = self._get_cached_validation_details(recent_entry, path)
            if cached_details is not None:
                return cached_details

        fingerprints = {path: self._get_path_fingerprint(path)}
        result = self.__get_uncached_path_detail(path, recent_entry, fingerprints)
        if recent_entry is not None and result.get("Invalid") == []:
            self._cache_validation_details(recent_entry, fingerprints, result)
            if owns_recent_file_data:
                self.save_recent_file(recent_file_data)
        return result

    def __get_uncached_path_detail(
        self,
        path: str,
        recent_entry: dict[str, object] | None,
        fingerprints: dict[str, dict[str, bool | int]],
    ) -> dict[str, object]:
        """Return uncached project details and collect dependency fingerprints."""
        recent_entry = recent_entry or {}

        ok, reason = self._validate_path(path)
        if not ok:
            carb.log_warn(f"[RecentProjectsCore] get_path_detail skipped: {reason}")
            return {
                "Invalid": [(path, reason)],
                "Game": recent_entry.get("game", None),
                "Capture": recent_entry.get("capture", None),
            }

        ok, reason = self._validate_usd_file(path)
        if not ok:
            carb.log_warn(f"[RecentProjectsCore] get_path_detail skipped: {reason}")
            return {
                "Invalid": [(path, reason)],
                "Game": recent_entry.get("game", None),
                "Capture": recent_entry.get("capture", None),
            }

        result = {}
        recent_url = OmniUrl(path)
        if not recent_url.exists:
            return result

        if recent_entry:
            result["Game"] = recent_entry.get("game", "")
            result["Capture"] = recent_entry.get("capture", "")
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
                    if is_layer_from_capture(resolved):
                        continue

                    fingerprints[resolved] = self._get_path_fingerprint(resolved)
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
    def _get_path_fingerprint(path: str) -> dict[str, bool | int]:
        """Return a cheap file fingerprint used to invalidate cached validation results."""
        if not path or not path.strip():
            return {"exists": False, "is_file": False}

        try:
            path_stat = Path(path).stat()
        except OSError:
            return {"exists": False, "is_file": False}

        is_file = stat.S_ISREG(path_stat.st_mode)
        fingerprint = {
            "exists": True,
            "is_file": is_file,
        }
        if is_file:
            fingerprint["size"] = path_stat.st_size
            fingerprint["mtime_ns"] = path_stat.st_mtime_ns
        return fingerprint

    @staticmethod
    def _get_cached_validation_details(entry: dict[str, object], root_path: str) -> dict[str, object] | None:
        """Return cached details when every recorded layer fingerprint still matches.

        Args:
            entry: A recent-project entry that may contain cached validation data.
            root_path: The project layer path required in the fingerprint set.

        Returns:
            A detached details mapping for a cache hit, or ``None`` for a cache miss.
        """
        validation = entry.get(VALIDATION_CACHE_KEY)
        if not isinstance(validation, dict):
            return None
        if validation.get("schema") != VALIDATION_CACHE_SCHEMA:
            return None
        if validation.get("inputs") != {"game": entry.get("game"), "capture": entry.get("capture")}:
            return None

        fingerprints = validation.get("fingerprints")
        if not isinstance(fingerprints, dict) or root_path not in fingerprints:
            return None
        for fingerprint_path, fingerprint in fingerprints.items():
            if not isinstance(fingerprint_path, str) or not isinstance(fingerprint, dict):
                return None
            if RecentProjectsCore._get_path_fingerprint(fingerprint_path) != fingerprint:
                return None

        details = validation.get("details")
        if not isinstance(details, dict) or details.get("Invalid") != []:
            return None
        return copy.deepcopy(details)

    @staticmethod
    def _cache_validation_details(
        entry: dict[str, object],
        fingerprints: dict[str, dict[str, bool | int]],
        details: dict[str, object],
    ) -> None:
        """Store validation details and layer fingerprints on a recent-project entry.

        Args:
            entry: The recent-project entry to mutate.
            fingerprints: Fingerprints for the root and checked non-capture sublayers.
            details: The project details produced by validation.
        """
        entry[VALIDATION_CACHE_KEY] = {
            "schema": VALIDATION_CACHE_SCHEMA,
            "inputs": {"game": entry.get("game"), "capture": entry.get("capture")},
            "fingerprints": fingerprints,
            "details": copy.deepcopy(details),
        }

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
        except (TimeoutError, Exception):  # noqa: BLE001
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

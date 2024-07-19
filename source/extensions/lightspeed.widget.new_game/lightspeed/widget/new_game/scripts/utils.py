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

import json
from pathlib import Path
from typing import Optional

import carb
import carb.tokens
import omni.client
from lightspeed.upscale.core import UpscaleModels, UpscalerCore
from PIL import Image


class GameCaptureFolderJson:
    def __get_dir(self) -> str:
        """Return the file"""
        token = carb.tokens.get_tokens_interface()
        directory = token.resolve("${app_documents}")
        # FilePickerDialog needs the capital drive. In case it's linux, the
        # first letter will be / and it's still OK.
        return str(Path(directory[:1].upper() + directory[1:]).resolve())

    def __get_file(self) -> str:
        """Return the file"""
        directory = self.__get_dir()
        return f"{directory}/lss_games.json"

    def append_path_to_file(self, path: str, name: str, save: bool = True):
        current_data = self.get_file_data()

        if path in current_data:
            del current_data[path]
        current_data[name] = {"path": path}

        if save:
            write_file(self.__get_file(), json.dumps(current_data, indent=4, sort_keys=True).encode("utf8"))
        return current_data

    def delete_names(self, names):
        current_data = self.get_file_data()
        for name in names:
            if name in current_data:
                del current_data[name]
        write_file(self.__get_file(), json.dumps(current_data, indent=4, sort_keys=True).encode("utf8"))

    def override_data_with(self, data):
        write_file(self.__get_file(), json.dumps(data, indent=4, sort_keys=True).encode("utf8"))

    def does_file_exist(self):
        file_path = self.__get_file()
        result, entry = omni.client.stat(file_path)
        if result != omni.client.Result.OK or not entry.flags & omni.client.ItemFlags.READABLE_FILE:
            carb.log_warn(f"Lightspeed game file doesn't exist: {file_path}")
            return False
        return True

    def get_file_data(self):
        if not self.does_file_exist():
            return {}
        file_path = self.__get_file()
        carb.log_info(f"Get Lightspeed game file from {file_path}")
        file_data = read_file(file_path)
        if file_data is None:
            return {}
        return json.loads(file_data)


_INSTANCE = None


def get_game_icon_from_capture_folder(capture_folder_path: str) -> Optional[str]:
    icons = list(Path(capture_folder_path).glob("*_icon.bmp"))
    return str(icons[0]) if icons else None


def get_upscaled_game_icon_from_capture_folder(capture_folder_path: str) -> Optional[str]:
    default_icon = get_game_icon_from_capture_folder(capture_folder_path)
    if not default_icon:
        return None
    # look for the upscaled icon
    upscaled = default_icon.replace("_icon.bmp", "_upscaled_icon.png")
    upscaled_path = Path(upscaled)
    if not upscaled_path.exists():
        # first we convert the bmp to png without alpha
        png_file = default_icon.replace("_icon.bmp", "_icon.png")
        with Image.open(default_icon) as im1:
            im1 = im1.convert("RGB")
            im1.save(png_file)
        # we upscale
        UpscalerCore.perform_upscale(UpscaleModels.ESRGAN.value, png_file, str(upscaled_path))
    return str(upscaled_path)


def get_instance():
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = GameCaptureFolderJson()
    return _INSTANCE  # noqa R504


def read_file(file_path) -> Optional[bytes]:
    """Read a file on the disk"""
    result, _, content = omni.client.read_file(file_path)
    if result == omni.client.Result.OK:
        data = memoryview(content).tobytes()
    else:
        try:  # try local
            with open(file_path, "rb") as in_file:
                data = in_file.read()
        except IOError:
            carb.log_error(f"Cannot read {file_path}, error code: {result}.")
            return None
    return data  # noqa R504


def write_file(file_path, data, comment=None) -> bool:
    """Write a file on the disk"""
    json_bytes = bytes(data)
    result = omni.client.write_file(file_path, json_bytes)
    if result != omni.client.Result.OK:
        carb.log_error(f"Cannot write {file_path}, error code: {result}.")
        return False
    result, entry = omni.client.stat(file_path)
    if result == omni.client.Result.OK and entry.flags & omni.client.ItemFlags.IS_CHECKPOINTED:
        result, _ = omni.client.create_checkpoint(file_path, "" if comment is None else comment, force=True)
        if result != omni.client.Result.OK:
            carb.log_error(f"Can't create a checkpoint for file {file_path}")
    carb.log_info(f"File saved to {file_path}")
    return True

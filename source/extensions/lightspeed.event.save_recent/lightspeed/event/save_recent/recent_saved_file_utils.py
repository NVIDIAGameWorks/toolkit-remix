"""
* Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import asyncio
import json
import math
import os
import shutil
from pathlib import Path
from typing import Dict

import carb
import carb.tokens
import omni.client


class RecentSavedFile:
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
        with open(file_path, "w", encoding="utf8") as json_file:
            json.dump(data, json_file, indent=2)

        carb.log_info(f"Recent saved file tracker saved to {file_path}")

    def append_path_to_recent_file(self, path: str, game: str, capture: str, save: bool = True):
        """Append a work file path to file"""
        current_data = self.get_recent_file_data()

        if path in current_data:
            del current_data[path]
        current_data[path] = {"game": game, "capture": capture}

        current_data_max = list(current_data.keys())[:40]

        result = {}
        for current_path, current_data in current_data.items():  # noqa B020
            if current_path in current_data_max:
                result[current_path] = current_data  # noqa B020
        if save:
            self.save_recent_file(result)
        return result

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
                return json.load(json_file)
        except json.JSONDecodeError:
            carb.log_warn(f"{file_path} is corrupted! Deleting it.")
            shutil.copyfile(file_path, f"{file_path}.bak")
            Path(file_path).unlink()
        return {}

    def get_path_detail(self, path) -> Dict[str, str]:
        """Get details from the given path"""
        result, entry = omni.client.stat(path)
        if result == omni.client.Result.OK:
            data = self.get_recent_file_data()
            result = {}
            if path in data:
                result["Game"] = data[path]["game"]
                result["Capture"] = data[path]["capture"]
            result_list, entries = omni.client.list_checkpoints(path)
            if result_list == omni.client.Result.OK:
                result["Version"] = entries[-1].relative_path[1:]
            result.update(
                {"Published": entry.created_time.strftime("%m/%d/%Y, %H:%M:%S"), "Size": self.convert_size(entry.size)}
            )
            return result
        return {}

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
        except (Exception, asyncio.TimeoutError):  # noqa PLW0703
            result = omni.client.Result.ERROR_NOT_FOUND
        if result == omni.client.Result.OK:
            return path, thumbnail
        if not auto:
            return await RecentSavedFile.find_thumbnail_async(path, auto=True)
        return None, None

    @staticmethod
    def convert_size(size_bytes):
        if size_bytes == 0:
            return "0B"
        size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        return f"{s} {size_name[i]}"


_INSTANCE = None


def get_instance():
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = RecentSavedFile()
    return _INSTANCE  # noqa R504

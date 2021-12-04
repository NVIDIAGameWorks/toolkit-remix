"""
* Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import json
from pathlib import Path
from typing import Optional

import carb
import carb.tokens
import omni.client


class GameJson:
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


def get_instance():
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = GameJson()
    return _INSTANCE  # noqa R504


def read_file(file_path) -> Optional[bytes]:
    """Read a file on the disk"""
    result, version, content = omni.client.read_file(file_path)
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
        result, query = omni.client.create_checkpoint(file_path, "" if comment is None else comment, force=True)
        if result != omni.client.Result.OK:
            carb.log_error(f"Can't create a checkpoint for file {file_path}")
    carb.log_info(f"File saved to {file_path}")
    return True

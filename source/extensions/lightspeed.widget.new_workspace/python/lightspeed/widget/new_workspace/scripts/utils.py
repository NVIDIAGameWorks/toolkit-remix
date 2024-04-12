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

import carb
import carb.tokens


class ReplacementPathUtils:
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
        return f"{directory}/recent_replacement_paths.json"

    def save_recent_file(self, data):
        """Save the recent work files to the file"""
        file_path = self.__get_recent_file()
        with open(file_path, "w", encoding="utf-8") as json_file:
            json.dump(data, json_file, indent=2)

        carb.log_info(f"Recent replacement paths file tracker saved to {file_path}")

    def append_path_to_recent_file(self, last_path: str, game: str, save: bool = True):
        """Append a work file path to file"""
        current_data = self.get_recent_file_data()

        if game in current_data:
            del current_data[game]
        current_data[game] = {"last_path": last_path}
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
            carb.log_info(f"Recent replacement paths file tracker doesn't exist: {file_path}")
            return False
        return True

    def get_recent_file_data(self):
        """Load the recent work files from the file"""
        if not self.is_recent_file_exist():
            return {}
        file_path = self.__get_recent_file()
        carb.log_info(f"Get recent replacement paths file(s) from {file_path}")
        with open(file_path, encoding="utf-8") as json_file:
            return json.load(json_file)

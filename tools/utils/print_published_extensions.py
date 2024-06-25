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
import omni.kit.app
import sys


def get_last_published_extension_version(ext_names):
    manager = omni.kit.app.get_app().get_extension_manager()
    manager.sync_registry()
    for ext_name in ext_names.split(","):
        for ext in manager.fetch_extension_versions(ext_name):
            package_id = ext["package_id"]
            print(f"Last version: {package_id}")
            break


if __name__ == "__main__":
    get_last_published_extension_version(sys.argv[1])

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

__all__ = ["get_app_distribution", "get_app_version"]

from pathlib import Path

import carb
import omni.kit.app


def get_app_version() -> str:
    """
    Get the complete app version number, including the distribution.
    """
    version_file = Path(carb.tokens.get_tokens_interface().resolve("${kit}")).parent / "VERSION"
    if version_file.exists():
        try:
            with open(version_file, encoding="utf-8") as f:
                return f.read().strip()
        except OSError as e:
            carb.log_error(f"Error reading version file: {e}")

    return omni.kit.app.get_app().get_app_version()


def get_app_distribution() -> str | None:
    """
    Get the app distribution.

    Example:
        If the app version is 1.0.0+dev.1234567890, this function will return dev.1234567890
        If the app version is 1.0.0, this function will return None
    """
    version = get_app_version()
    return version.split("+", maxsplit=1)[1] if "+" in version else None

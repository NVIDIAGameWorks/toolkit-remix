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

__all__ = ["AssetType", "DefaultAssetDirectory"]

from enum import Enum

from lightspeed.common import constants


class DefaultAssetDirectory(Enum):
    INGESTED = constants.REMIX_INGESTED_ASSETS_FOLDER
    TEXTURES = constants.REMIX_TEXTURES_ASSETS_FOLDER
    MODELS = constants.REMIX_MODELS_ASSETS_FOLDER


class AssetType(Enum):
    ANY = None
    TEXTURES = "textures"
    MODELS = "models"

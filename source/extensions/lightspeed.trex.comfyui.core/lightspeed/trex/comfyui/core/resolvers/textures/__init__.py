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

# Texture-path getters. Add a new one by dropping a module beside this file with a
# TextureResolverBase subclass, then appending it to TEXTURE_RESOLVER_PLUGINS below.

__all__ = [
    "TEXTURE_RESOLVER_PLUGINS",
    "AllStageTexturesResolver",
    "SelectedTextureResolver",
    "TextureResolverBase",
]

from .all_stage import AllStageTexturesResolver
from .base import TextureResolverBase
from .selected import SelectedTextureResolver

# Registration order controls getter dropdown order and the semantic default (first entry).
TEXTURE_RESOLVER_PLUGINS = [
    SelectedTextureResolver,
    AllStageTexturesResolver,
]

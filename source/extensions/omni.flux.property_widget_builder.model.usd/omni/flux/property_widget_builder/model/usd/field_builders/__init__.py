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

__all__ = (
    "USDBuilderList",
    "ALL_FIELD_BUILDERS",
    "MATERIAL_FIELD_BUILDERS",
    "DEFAULT_FIELD_BUILDERS",
    "LIGHT_FIELD_BUILDERS",
)


from .aperture_pbr import MATERIAL_FIELD_BUILDERS
from .base import DEFAULT_FIELD_BUILDERS, USDBuilderList
from .lights import LIGHT_FIELD_BUILDERS

# Note these are added in a specific order.
ALL_FIELD_BUILDERS = []
ALL_FIELD_BUILDERS.extend(DEFAULT_FIELD_BUILDERS)
ALL_FIELD_BUILDERS.extend(LIGHT_FIELD_BUILDERS)
ALL_FIELD_BUILDERS.extend(MATERIAL_FIELD_BUILDERS)

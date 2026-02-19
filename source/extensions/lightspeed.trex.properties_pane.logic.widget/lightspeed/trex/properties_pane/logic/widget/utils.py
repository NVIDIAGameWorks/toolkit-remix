"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = ["UiMetaKeys", "get_ogn_ui_metadata"]

from enum import Enum
import omni.graph.core as og
from lightspeed.trex.logic.core import ogn_read_metadata_key


class UiMetaKeys(Enum):
    """OGN metadata key names for UI bounds and step (camelCase as in .ogn files)."""

    soft_min = "softMin"
    soft_max = "softMax"
    hard_min = "hardMin"
    hard_max = "hardMax"
    ui_step = "uiStep"


def get_ogn_ui_metadata(attr: og.Attribute) -> dict:
    """
    Get soft/hard bounds and UI step from OGN attribute metadata.

    Reads OGN metadata keys softMin, softMax, hardMin, hardMax, and uiStep,
    converts each via ogn_read_metadata_key, and returns a dict with
    snake_case keys suitable for use as USDAttributeItem kwargs.

    Args:
        attr: The OmniGraph attribute to get UI metadata for.

    Returns:
        Dict keyed by "soft_min", "soft_max", "hard_min", "hard_max", "ui_step"
        with converted values (float or int). Keys with no metadata
        are None.
    """
    return {key.name: ogn_read_metadata_key(attr, key.value) for key in UiMetaKeys}

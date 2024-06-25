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

__all__ = [
    "is_remix_supported",
    "RemixSupport",
    "RemixRequestQueryType",
    "hdremix_findworldposition_request",
    "hdremix_objectpicking_request",
    "hdremix_highlight_paths",
    "hdremix_uselegacyselecthighlight",
    "viewport_api_request_query_hdremix",
    "hdremix_set_configvar",
]

# Export extension class
from .extension import HdRemixFinalizer  # noqa F401
from .extension import RemixSupport, is_remix_supported
from .extern import (
    RemixRequestQueryType,
    hdremix_findworldposition_request,
    hdremix_highlight_paths,
    hdremix_objectpicking_request,
    hdremix_set_configvar,
    viewport_api_request_query_hdremix,
)
from .select_highlight_setting import hdremix_uselegacyselecthighlight

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

import omni.client
import omni.usd


@omni.usd.handle_exception
async def is_path_readable(path: str):
    """
    Check is a path is readable

    Args:
        path: the path to check
    """
    _, entry = await omni.client.stat_async(path)
    if (entry.flags & omni.client.ItemFlags.READABLE_FILE) or (entry.flags & omni.client.ItemFlags.CAN_HAVE_CHILDREN):
        return True
    return False

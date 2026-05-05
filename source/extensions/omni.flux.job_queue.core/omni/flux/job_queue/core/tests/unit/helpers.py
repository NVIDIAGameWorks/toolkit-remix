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

import contextlib
import os
import tempfile
import time


@contextlib.asynccontextmanager
async def temp_db_path():
    temp_dir = tempfile.TemporaryDirectory(prefix="omni-flux-job_queue")
    temp_path = os.path.join(temp_dir.name, "db.sqlite")
    try:
        yield temp_path
    finally:
        tries = 0
        while tries < 3:
            tries += 1
            try:
                temp_dir.cleanup()
                break
            except PermissionError:
                time.sleep(0.1 * tries)
        else:
            raise RuntimeError(f"Failed to clean up temporary directory: {temp_dir.name}")

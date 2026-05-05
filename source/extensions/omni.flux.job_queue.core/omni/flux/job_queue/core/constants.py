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

import dataclasses
import os
import tempfile


@dataclasses.dataclass
class JobQueueConfig:
    """
    Configuration for the job queue system.

    Attributes:
        db_path: Path to the SQLite database file. Defaults to a temp directory,
                 can be overridden via FLUX_JOB_QUEUE_DEFAULT_FILEPATH environment variable.
    """

    # NOTE: This path can be configured by higher level extensions using settings, but here we're avoiding that to
    # avoid the need to pull in extra extension(s) as dependencies.
    db_path: str = dataclasses.field(
        default_factory=lambda: os.environ.get(
            "FLUX_JOB_QUEUE_DEFAULT_FILEPATH",
            os.path.join(tempfile.gettempdir(), "job_queue.db"),
        )
    )


# Singleton instance used by default when no explicit path is provided
job_queue_config = JobQueueConfig()

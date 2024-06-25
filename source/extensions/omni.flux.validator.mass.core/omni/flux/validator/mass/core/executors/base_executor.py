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

import abc
import asyncio
import os
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from omni.flux.validator.manager.core import ManagerCore as _ManagerCore


class BaseExecutor:
    def __init__(self, max_concurrent=None):
        """
        Executor that will run job in async locally.

        Args:
            max_concurrent: number of job(s) we would want to run concurrently
        """
        if max_concurrent and not isinstance(max_concurrent, int):
            raise ValueError("max_concurrent must type int")
        if max_concurrent and max_concurrent < 0:
            raise ValueError("max_concurrent must be greater than 0")
        self._max_concurrent = max_concurrent or os.cpu_count()

    @abc.abstractmethod
    def submit(
        self,
        core: "_ManagerCore",
        print_result: bool = False,
        silent: bool = False,
        timeout: Optional[int] = None,
        standalone: Optional[bool] = False,
        queue_id: str | None = None,
    ) -> asyncio.Future:
        """
        Submit and execute a job

        Args:
            core: the manager core that holds the data
            print_result: print the resulting schema or not
            silent: print the stdout or not
            timeout: timeout for each job
            standalone: does the process run in a standalone mode or not (like a CLI)
            queue_id: the queue ID to use. Needed if you have multiple widgets that shows different queues

        Returns:
            The future of the job (that will hold the result)
        """
        pass

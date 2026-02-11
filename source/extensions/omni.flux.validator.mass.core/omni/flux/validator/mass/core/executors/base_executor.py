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

from __future__ import annotations

import abc
import asyncio
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omni.flux.validator.manager.core import ManagerCore as _ManagerCore


class BaseExecutor:
    def __init__(self):
        """Executor that will run jobs locally."""
        self._cpu_count = os.cpu_count()

    @abc.abstractmethod
    def submit(
        self,
        core: _ManagerCore,
        print_result: bool = False,
        silent: bool = False,
        timeout: int | None = None,
        standalone: bool | None = False,
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

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

import asyncio
import functools
import os
from typing import TYPE_CHECKING, Optional

import carb

from .base_executor import BaseExecutor as _BaseExecutor

if TYPE_CHECKING:
    from omni.flux.validator.manager.core import ManagerCore as _ManagerCore


class AsyncExecutor(_BaseExecutor):
    def __init__(self, max_concurrent=None):
        """
        Executor that will run job in async locally.

        Args:
            max_concurrent: number of job(s) we would want to run concurrently
        """
        super().__init__(max_concurrent=max_concurrent)
        self._sem = asyncio.Semaphore(max_concurrent or os.cpu_count())
        self._sub_run_finished = {}

    async def _clear_sub(self, future: asyncio.Future):
        del self._sub_run_finished[future]

    def _set_result(self, future: asyncio.Future, result: bool, message: Optional[str] = None):
        future.set_result((result, message))
        asyncio.ensure_future(self._clear_sub(future))

    def submit(
        self,
        core: "_ManagerCore",
        print_result: bool = False,
        silent: bool = False,
        timeout: Optional[int] = None,
        standalone: Optional[bool] = False,
        queue_id: str | None = None,
    ) -> asyncio.Future:
        future = asyncio.Future()
        asyncio.ensure_future(
            self._submit(
                core.deferred_run_with_exception, future, timeout=timeout, print_result=print_result, silent=silent
            )
        )
        self._sub_run_finished[future] = core.subscribe_run_finished(functools.partial(self._set_result, future))
        return future

    async def _submit(self, func, future: asyncio.Future, *args, timeout: Optional[int] = None, **kwargs):
        try:
            if timeout is None:
                await self._run(func, *args, **kwargs)
            else:
                await asyncio.wait_for(asyncio.shield(self._run(func, *args, **kwargs)), timeout=timeout)
            # await self._run(func, *args, **kwargs)
        except asyncio.TimeoutError:
            message = f"Time out expired ({timeout}sc)"
            carb.log_error(message)
            future.set_result((False, message))

    async def _run(self, func, *args, **kwargs):
        async with self._sem:
            return await func(*args, **kwargs)

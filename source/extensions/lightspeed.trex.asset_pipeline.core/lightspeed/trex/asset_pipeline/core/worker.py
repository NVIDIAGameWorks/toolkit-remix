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

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable


async def await_settled[AwaitedResultT](operation: Awaitable[AwaitedResultT]) -> AwaitedResultT:
    """Settle asynchronous work before propagating cancellation.

    Args:
        operation: Awaitable work that must finish before caller teardown.

    Returns:
        Result returned by ``operation``.

    Raises:
        asyncio.CancelledError: If the awaiting caller is cancelled.
    """
    task = asyncio.ensure_future(operation)
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        while not task.done():
            try:
                await asyncio.wait({task})
            except asyncio.CancelledError:
                continue
        if not task.cancelled():
            task.exception()
        raise


async def run_in_worker_thread[**BlockingCallParameters, BlockingCallResultT](
    function: Callable[BlockingCallParameters, BlockingCallResultT],
    /,
    *args: BlockingCallParameters.args,
    **kwargs: BlockingCallParameters.kwargs,
) -> BlockingCallResultT:
    """Run blocking work off the event loop and settle it before propagating cancellation.

    The blocking call's result or exception is propagated after it completes. Cancellation waits for the worker
    thread to settle before re-raising ``CancelledError`` so file writes cannot continue after pipeline teardown.

    Args:
        function: Blocking callable to execute in a worker thread.
        *args: Positional arguments forwarded to ``function``.
        **kwargs: Keyword arguments forwarded to ``function``.

    Returns:
        Result returned by ``function``.

    Raises:
        asyncio.CancelledError: If the awaiting caller is cancelled.
    """
    return await await_settled(asyncio.to_thread(function, *args, **kwargs))

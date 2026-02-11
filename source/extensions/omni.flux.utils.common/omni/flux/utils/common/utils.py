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
from collections.abc import Callable

import omni.kit.app
import omni.usd
from carb import log_warn as _log_warn
from pxr import Sdf


def get_omni_prims() -> set[Sdf.Path]:
    """
    Get default reserved prims used by Omniverse Kit

    Returns:
        The default prims
    """
    return {
        Sdf.Path("/OmniverseKit_Persp"),
        Sdf.Path("/OmniverseKit_Front"),
        Sdf.Path("/OmniverseKit_Top"),
        Sdf.Path("/OmniverseKit_Right"),
        Sdf.Path("/OmniKit_Viewport_LightRig"),
        Sdf.Path("/Render"),
    }


def async_wrap(func) -> Callable:
    """Wrap a function into an async executor"""

    @asyncio.coroutine
    @functools.wraps(func)
    def run(*args, loop=None, executor=None, **kwargs):
        if loop is None:
            loop = asyncio.get_event_loop()
        pfunc = functools.partial(func, *args, **kwargs)
        return loop.run_in_executor(executor, pfunc)

    return run


@omni.usd.handle_exception
async def deferred_destroy_tasks(tasks: list[asyncio.Task]):
    """
    Wait for a task to be done and destroy it

    Args:
        tasks: list of async task

    Returns:

    """
    for task in tasks:
        if task:
            task.cancel()
        if task:
            while not task.done():
                await omni.kit.app.get_app().next_update_async()
                if not task:
                    break
        task = None


def reset_default_attrs(obj):
    default_attr = getattr(obj, "_default_attr", None)
    if not default_attr:
        default_attr = getattr(obj, "default_attr", None)
    if not default_attr:
        default_attr = getattr(obj, "_default_attrs", None)

    if default_attr is None:
        _log_warn(f"reset_default_attrs: given object must have a `_default_attr` or `default_attr` field. obj={obj}")
        return

    for attr, value in default_attr.items():
        m_attr = getattr(obj, attr)
        if isinstance(m_attr, list):
            m_attrs = m_attr
        elif isinstance(m_attr, dict):
            m_attrs = list(m_attr.values())
        elif isinstance(m_attr, tuple):
            m_attrs = list(m_attr)
        else:
            m_attrs = [m_attr]
        for m_attr in m_attrs:
            destroy = getattr(m_attr, "destroy", None)
            if callable(destroy):
                destroy()
            del m_attr
        setattr(obj, attr, value)

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

import carb.settings
from omni.kit.app import SettingChangeSubscription

from .apply_executor import ApplyExecutor
from .apply_handler_base import ApplyHandler
from .apply_handler_registry import ApplyHandlerRegistry
from .execute import JobScheduler
from .interface import QueueInterface
from .settings import AUTO_APPLY_SETTING_PATH, SCHEDULER_ENABLED_SETTING_PATH, JobQueueSettings

__all__ = (
    "get_apply_executor",
    "get_registry",
    "register_plugins",
    "shutdown",
    "startup",
    "unregister_plugins",
)

_registry: ApplyHandlerRegistry | None = None
_apply_executor: ApplyExecutor | None = None
_scheduler: JobScheduler | None = None
_queue: QueueInterface | None = None
_settings: JobQueueSettings | None = None
_auto_apply_subscription: SettingChangeSubscription | None = None
_scheduler_subscription: SettingChangeSubscription | None = None
_background_tasks: set[asyncio.Task[None]] = set()
_scheduler_reconcile_task: asyncio.Task[None] | None = None
_main_loop: asyncio.AbstractEventLoop | None = None
_last_auto_apply = False


def get_registry() -> ApplyHandlerRegistry:
    """Return the process-wide explicit Apply handler registry.

    Returns:
        Active handler registry.

    Raises:
        RuntimeError: If the extension is not started.
    """
    if _registry is None:
        raise RuntimeError("Job queue core extension is not started")
    return _registry


def get_apply_executor() -> ApplyExecutor:
    """Return the process-wide typed Apply executor.

    Returns:
        Active Apply executor.

    Raises:
        RuntimeError: If the extension is not started.
    """
    if _apply_executor is None:
        raise RuntimeError("Job queue core extension is not started")
    return _apply_executor


def register_plugins(plugins: list[type[ApplyHandler]]) -> None:
    """Register exact handler types and reconcile pending automatic outputs.

    Args:
        plugins: Exact handler classes to register.
    """
    get_registry().register_plugins(plugins)


def unregister_plugins(plugins: list[type[ApplyHandler]]) -> None:
    """Unregister exact handler types.

    Args:
        plugins: Exact registered handler classes.
    """
    get_registry().unregister_plugins(plugins)


def startup(queue: QueueInterface) -> None:
    """Start the extension-owned scheduler and Apply runtime.

    Args:
        queue: Process-wide persistent queue.
    """
    global _apply_executor, _auto_apply_subscription, _last_auto_apply, _main_loop, _queue, _registry, _scheduler
    global _scheduler_reconcile_task, _scheduler_subscription, _settings
    _main_loop = asyncio.get_event_loop()
    _queue = queue
    _settings = JobQueueSettings()
    _registry = ApplyHandlerRegistry()
    settings = _settings
    _apply_executor = ApplyExecutor(queue, _registry, lambda: settings.auto_apply)
    _registry.set_changed_callback(_on_apply_handlers_changed)
    _scheduler = JobScheduler(queue)
    _last_auto_apply = _settings.auto_apply
    _scheduler_reconcile_task = None
    _auto_apply_subscription = SettingChangeSubscription(AUTO_APPLY_SETTING_PATH, _on_auto_apply_changed)
    _scheduler_subscription = SettingChangeSubscription(SCHEDULER_ENABLED_SETTING_PATH, _on_scheduler_enabled_changed)
    _main_loop.call_soon(_schedule_scheduler_reconcile)


def shutdown() -> asyncio.Task[None] | None:
    """Detach settings and begin asynchronous runtime shutdown.

    Returns:
        Retained cleanup task, or ``None`` if no runtime exists or cleanup settled inline.
    """
    global _apply_executor, _auto_apply_subscription, _main_loop, _queue, _registry, _scheduler
    global _scheduler_reconcile_task
    global _scheduler_subscription, _settings
    _auto_apply_subscription = None
    _scheduler_subscription = None
    scheduler = _scheduler
    executor = _apply_executor
    registry = _registry
    main_loop = _main_loop
    if registry is not None:
        registry.set_changed_callback(None)
    _queue = None
    _settings = None
    _scheduler = None
    _apply_executor = None
    _registry = None
    _scheduler_reconcile_task = None
    _main_loop = None
    if registry is None:
        return None
    if scheduler is None or executor is None:
        registry.destroy()
        return None

    async def cleanup() -> None:
        """Wait for active execution and Apply work before destroying the registry."""
        await scheduler.stop()
        await executor.shutdown()
        if _background_tasks:
            await asyncio.gather(*tuple(_background_tasks))
        registry.destroy()

    if main_loop is None or main_loop.is_closed():
        raise RuntimeError("The job queue owning event loop is unavailable during shutdown")
    try:
        running_loop = asyncio.get_running_loop()
    except RuntimeError:
        main_loop.run_until_complete(cleanup())
        return None
    if running_loop is not main_loop:
        raise RuntimeError("Job queue shutdown must run on its owning event loop")
    return main_loop.create_task(cleanup())


def _on_apply_handlers_changed() -> None:
    """Refresh live consumers and reconcile pending work after registry changes."""
    queue = _queue
    executor = _apply_executor
    if queue is None or executor is None:
        return
    queue.notify_schedule_conditions_changed()
    for snapshot in queue.iter_snapshot():
        executor.request_reconcile(snapshot.job_id)


def _on_auto_apply_changed(_item, _event_type: carb.settings.ChangeEventType) -> None:
    """Reconcile pending outputs after a global automatic setting change.

    Args:
        _item: Changed settings item.
        _event_type: Settings change kind.
    """
    global _last_auto_apply
    queue = _queue
    executor = _apply_executor
    settings = _settings
    if queue is None or executor is None or settings is None:
        return
    enabled = settings.auto_apply
    should_reconcile = enabled and not _last_auto_apply
    _last_auto_apply = enabled
    if should_reconcile:
        for snapshot in queue.iter_snapshot():
            executor.request_reconcile(snapshot.job_id)


def _on_scheduler_enabled_changed(_item, _event_type: carb.settings.ChangeEventType) -> None:
    """Marshal scheduler-setting reconciliation onto the owning Kit loop.

    Args:
        _item: Changed settings item.
        _event_type: Settings change kind.
    """
    loop = _main_loop
    if _scheduler is None or _settings is None or loop is None or loop.is_closed():
        return
    try:
        loop.call_soon_threadsafe(_schedule_scheduler_reconcile)
    except RuntimeError as error:
        carb.log_error(f"Could not reconcile the job scheduler setting: {error}")


def _schedule_scheduler_reconcile() -> None:
    """Create at most one scheduler reconciliation task on the Kit loop."""
    global _scheduler_reconcile_task
    if _scheduler is None or _settings is None:
        return
    if _scheduler_reconcile_task is None or _scheduler_reconcile_task.done():
        _scheduler_reconcile_task = asyncio.create_task(_reconcile_scheduler_setting())
        _retain(_scheduler_reconcile_task)


async def _reconcile_scheduler_setting() -> None:
    """Serialize scheduler stop/start changes and honor the latest desired value."""
    while True:
        scheduler = _scheduler
        settings = _settings
        if scheduler is None or settings is None:
            return
        desired = settings.scheduler_enabled
        if desired:
            scheduler.start()
        else:
            await scheduler.stop()
        if scheduler is not _scheduler or settings is not _settings or desired == settings.scheduler_enabled:
            return


def _retain(task: asyncio.Task[None]) -> None:
    """Retain one background task and consume completion.

    Args:
        task: Owned background task.
    """

    def completed(done_task: asyncio.Task[None]) -> None:
        """Release one retained task and report unexpected failure.

        Args:
            done_task: Completed background task retained by the runtime.
        """
        _background_tasks.discard(done_task)
        if done_task.cancelled():
            return
        error = done_task.exception()
        if error is not None:
            carb.log_error(f"Job queue background task failed: {error}")

    _background_tasks.add(task)
    task.add_done_callback(completed)

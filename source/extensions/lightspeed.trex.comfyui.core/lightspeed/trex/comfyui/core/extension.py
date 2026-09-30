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

__all__ = ["ComfyUICoreExtension", "get_comfyui_core_instance"]

import contextlib
from functools import partial

import carb
import omni.kit.commands
from lightspeed.events_manager import get_instance as _get_event_manager_instance
from omni import usd
from omni.ext import IExt
from omni.flux.job_queue.core import handlers
from omni.flux.job_queue.core.extension import get_job_queue
from omni.flux.job_queue.core.persistence import get_registry

from . import commands
from .apply_handler import ComfyUIAssetApplyHandler, ComfyUIJobApplyHandler, ComfyUITextureApplyHandler
from .core import ComfyUICore
from .events import COMFYUI_EVENT_NAME
from .persistence_codecs import COMFYUI_CODECS
from .models import ComfyUIApplyTarget, ComfyUIAssetApplyTarget
from .resolvers import RESOLVER_PLUGINS, get_resolver_factory

_instances: dict[str, ComfyUICore] = {}
_shutting_down = True
_started = False


def _broadcast_settings_changed(key: str, value: object) -> None:
    """Notify every cached context of a process-wide ComfyUI setting change.

    Args:
        key: Short settings key name that changed.
        value: New value for the setting.
    """
    for instance in _instances.copy().values():
        instance.handle_settings_changed(key, value)


def get_comfyui_core_instance(context_name: str) -> ComfyUICore:
    """Get or create the ComfyUI core for a USD context.

    Args:
        context_name: USD context name.

    Returns:
        Cached or newly created core for the context.

    Raises:
        RuntimeError: If extension shutdown is in progress.
    """
    if _shutting_down:
        raise RuntimeError("ComfyUI core extension is shutting down")
    if context_name not in _instances:
        _instances[context_name] = ComfyUICore(
            context_name=context_name,
            settings_changed_callback=_broadcast_settings_changed,
            stage_event_callback=partial(ComfyUICoreExtension.on_stage_event, context_name),
        )
    return _instances[context_name]


class ComfyUICoreExtension(IExt):
    """Register ComfyUI persistence and job handlers with the Kit lifecycle."""

    _PLUGINS = [ComfyUITextureApplyHandler, ComfyUIAssetApplyHandler, ComfyUIJobApplyHandler]

    def on_startup(self, ext_id: str) -> None:
        """Register ComfyUI persisted types and apply handlers.

        Args:
            ext_id: Extension identifier supplied by Kit.
        """
        carb.log_info("[lightspeed.trex.comfyui.core] Startup")
        global _shutting_down, _started
        if _started:
            return
        _shutting_down = True
        resolver_factory = get_resolver_factory()
        registry = get_registry()
        event_manager = _get_event_manager_instance()
        with contextlib.ExitStack() as rollback:
            omni.kit.commands.register_all_commands_in_module(commands)
            rollback.callback(omni.kit.commands.unregister_module_commands, commands)
            resolver_factory.register_plugins(RESOLVER_PLUGINS)
            rollback.callback(resolver_factory.unregister_plugins, RESOLVER_PLUGINS)
            registry.register_codecs(COMFYUI_CODECS)
            rollback.callback(registry.unregister_codecs, COMFYUI_CODECS)
            handlers.register_plugins(self._PLUGINS)
            rollback.callback(handlers.unregister_plugins, self._PLUGINS)
            event_manager.register_global_custom_event(COMFYUI_EVENT_NAME)
            rollback.callback(event_manager.unregister_global_custom_event, COMFYUI_EVENT_NAME)
            rollback.pop_all()
        _started = True
        _shutting_down = False

    def on_shutdown(self) -> None:
        """Unregister handlers and invalidate every cached context core."""
        carb.log_info("[lightspeed.trex.comfyui.core] Shutdown")
        global _shutting_down, _started
        if not _started:
            return
        _shutting_down = True
        cleanup = contextlib.ExitStack()
        cleanup.callback(omni.kit.commands.unregister_module_commands, commands)
        cleanup.callback(get_resolver_factory().unregister_plugins, RESOLVER_PLUGINS)
        cleanup.callback(_get_event_manager_instance().unregister_global_custom_event, COMFYUI_EVENT_NAME)
        for instance in reversed(tuple(_instances.copy().values())):
            cleanup.callback(instance.destroy)
        cleanup.callback(handlers.unregister_plugins, self._PLUGINS)
        cleanup.close()
        _instances.clear()
        _started = False

    @staticmethod
    def on_stage_event(context_name: str, event) -> None:
        """Refresh only jobs that target the USD context whose stage changed.

        Args:
            context_name: USD context that emitted the stage event.
            event: USD stage lifecycle event.
        """
        if event.type not in {int(usd.StageEventType.CLOSED), int(usd.StageEventType.OPENED)}:
            return
        queue = get_job_queue()
        queue.notify_schedule_conditions_changed()
        if event.type != int(usd.StageEventType.OPENED):
            return
        executor = handlers.get_apply_executor()
        handler_ids = {handler.name for handler in ComfyUICoreExtension._PLUGINS}
        for snapshot in queue.iter_snapshot():
            if snapshot.apply_handler_id not in handler_ids:
                continue
            try:
                job = queue.get_job(snapshot.job_id)
            except (KeyError, RuntimeError, TypeError, ValueError) as error:
                carb.log_warn(f"Could not inspect ComfyUI Apply target for {snapshot.job_id}: {error}")
                continue
            binding = job.apply_binding
            if binding is None:
                continue
            target = binding.target
            if type(target) not in {ComfyUIApplyTarget, ComfyUIAssetApplyTarget}:
                continue
            if target.context_name == context_name:
                executor.request_reconcile(snapshot.job_id)

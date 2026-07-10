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

import carb
import omni.ext
import omni.kit.commands

from . import commands
from .listener import USDListener as _USDListener

_USD_LISTENER_INSTANCE: _USDListener | None = None


def get_usd_listener_instance() -> _USDListener | None:
    """Return the extension-owned USD listener, if the extension is started.

    Returns:
        Shared USD listener singleton, or ``None`` during extension startup/shutdown.
    """
    return _USD_LISTENER_INSTANCE


class USDPropertyWidgetExtension(omni.ext.IExt):
    """Register USD property-widget commands and own the shared listener singleton."""

    def on_startup(self, ext_id: str) -> None:
        """Register generic USD commands and create the shared listener.

        Args:
            ext_id: Kit extension id supplied by the extension manager.
        """
        global _USD_LISTENER_INSTANCE
        carb.log_info("[omni.flux.property_widget_builder.model.usd] Startup")
        omni.kit.commands.register_all_commands_in_module(commands)
        _USD_LISTENER_INSTANCE = _USDListener()

    def on_shutdown(self) -> None:
        """Unregister generic USD commands and destroy the shared listener."""
        global _USD_LISTENER_INSTANCE
        carb.log_info("[omni.flux.property_widget_builder.model.usd] Shutdown")
        omni.kit.commands.unregister_module_commands(commands)
        if _USD_LISTENER_INSTANCE is not None:
            _USD_LISTENER_INSTANCE.destroy()
        _USD_LISTENER_INSTANCE = None

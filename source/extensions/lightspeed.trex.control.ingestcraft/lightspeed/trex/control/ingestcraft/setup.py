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

import carb.settings
from lightspeed.common.constants import LayoutFiles as _LayoutFiles
from lightspeed.trex.contexts import get_instance as _trex_contexts_instance
from lightspeed.trex.contexts.setup import Contexts as _TrexContexts
from lightspeed.trex.utils.widget.quicklayout import load_layout
from omni.flux.utils.widget.resources import get_quicklayout_config as _get_quicklayout_config

_DEFAULT_LAYOUT = "/app/trex/default_layout"


class Setup:
    """Create the IngestCraft stage."""

    def __init__(self) -> None:
        """Initialize IngestCraft stage creation."""
        self._context = _trex_contexts_instance().get_usd_context(_TrexContexts.INGEST_CRAFT)
        self._context.new_stage_with_callback(self._on_new_stage_created)

        settings = carb.settings.get_settings()
        default_layout = settings.get(_DEFAULT_LAYOUT) or ""
        if default_layout == "ingestcraft":
            load_layout(_get_quicklayout_config(_LayoutFiles.INGESTCRAFT))

    def _on_new_stage_created(self, result: bool, error: str) -> None:
        """Report failure when the initial IngestCraft stage cannot be created."""
        if not result:
            carb.log_error(f"[lightspeed.trex.control.ingestcraft] Failed to create IngestCraft stage: {error}")

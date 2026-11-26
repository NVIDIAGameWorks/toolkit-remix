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

__all__ = ["AlphaCutoutModifierExtension"]

from lightspeed.trex.asset_modifiers.factory import get_instance
from omni.ext import IExt
from omni.flux.job_queue.core.persistence import get_registry

from .modifier import AlphaCardToMesh
from .report import REPORT_CODECS


class AlphaCutoutModifierExtension(IExt):
    """Register the Alpha Card to Mesh modifier and the persistence of its report for the extension lifetime."""

    def on_startup(self, ext_id: str) -> None:
        """Register the report codecs with the job queue and the modifier with the asset modifier factory.

        Args:
            ext_id: Extension id, unused.
        """
        get_registry().register_codecs(REPORT_CODECS)
        get_instance().register_plugins([AlphaCardToMesh])

    def on_shutdown(self) -> None:
        """Unregister the modifier; the report codecs stay until the queue core drains its jobs."""
        factory = get_instance()
        if factory is not None:
            factory.unregister_plugins([AlphaCardToMesh])

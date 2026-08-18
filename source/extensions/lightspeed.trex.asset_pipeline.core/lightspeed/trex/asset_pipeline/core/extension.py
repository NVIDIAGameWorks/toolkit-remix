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

__all__ = ["AssetPipelineCoreExtension"]

import omni.ext
from omni.flux.job_queue.core.persistence import get_registry

from .persistence_codecs import TEXTURE_PROCESSING_CODECS


class AssetPipelineCoreExtension(omni.ext.IExt):
    """Register process-owned texture-processing persistence codecs."""

    def on_startup(self, _ext_id: str) -> None:
        """Register the texture-processing persistence codecs.

        Args:
            _ext_id: Extension identifier supplied by Kit.
        """
        get_registry().register_codecs(TEXTURE_PROCESSING_CODECS)

    def on_shutdown(self) -> None:
        """Keep codecs available until the queue core drains active jobs and destroys its registry."""
